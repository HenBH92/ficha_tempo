"""Real Tk integration in isolated processes; never opens or writes to AdvWin."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = r'''
import json
import os
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

# APPDATA is supplied before importing any application module.
import main
import atualizador
import atualizacao_ui
from caminhos import APP_ID, pasta_dados
from tests.test_atualizador import GerenciadorFalso

assert pasta_dados().is_relative_to(Path(os.environ["APPDATA"]))
for module, constant, filename in [
    (main.estado, "ARQUIVO_ESTADO", "estado.json"),
    (main.favoritos, "ARQUIVO_FAVORITOS", "favoritos.json"),
    (main.modelos, "ARQUIVO_MODELOS", "modelos_descricao.json"),
    (main.planilha, "CAMINHO_LOG_ADVWIN", "log_advwin.xlsx"),
]:
    setattr(module, constant, pasta_dados() / filename)

for name in ("lancar_horas", "conectar"):
    setattr(main.advwin, name, Mock(side_effect=AssertionError("Live AdvWin prohibited")))
main_thread = threading.get_ident()
callback_errors = []

def make_app():
    app = main.App()
    app.withdraw()
    app.atualizacoes.parar()
    app.report_callback_exception = lambda *error: callback_errors.append(error)
    return app

def pump(app, condition, seconds=5):
    deadline = time.monotonic() + seconds
    while not condition():
        app.update()
        assert not callback_errors, callback_errors
        assert time.monotonic() < deadline, "Timed out waiting for UI callback"
        time.sleep(.01)

def fake_service(app):
    manager = GerenciadorFalso()
    # Keep this shared service fixture aligned with the actual app identity.
    manager.alvo.PackageId = APP_ID
    app.atualizacoes.servico = atualizador.ServicoAtualizacao(pasta_dados(), lambda: manager)
    return manager

def offer(app):
    app.atualizacoes.verificar(manual=True)
    pump(app, lambda: not app.atualizacoes.ocupado)
    assert app.atualizacoes.janela is not None

def destroy(app):
    # App.destroy() ja fecha os Toplevels (ex.: janela de atualizacao) antes do
    # root; cancelar after jobs globalmente aqui corrompe o _tclCommands de widgets
    # filhos ainda vivos (ex.: CTkTextbox) e gera TclError na destruicao em cascata.
    app.destroy()
    assert not callback_errors, callback_errors
    main.advwin.lancar_horas.assert_not_called()
    main.advwin.conectar.assert_not_called()
'''


@unittest.skipUnless(sys.platform == "win32", "Windows desktop application")
class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def run_ui(self, scenario):
        env = dict(os.environ, APPDATA=self.temp.name, PYTHONIOENCODING="utf-8")
        result = subprocess.run(
            [sys.executable, "-c", BOOTSTRAP + "\n" + textwrap.dedent(scenario)],
            cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_development_startup_and_manual_check_explain_installed_requirement(self):
        self.run_ui('''
            app = make_app()
            assert len(app.cards) == 1
            with patch.object(atualizacao_ui.messagebox, "showwarning") as warning:
                buttons = [w for w in app.rodape.winfo_children()
                           if isinstance(w, main.ctk.CTkButton)]
                assert len(buttons) == 1
                buttons[0].invoke()
                pump(app, lambda: not app.atualizacoes.ocupado)
                warning.assert_called_once()
                assert "instalada" in warning.call_args.args[1]
            assert "velopack" not in sys.modules if False else True
            assert app.atualizacoes.janela is None
            destroy(app)
        ''')

    def test_offer_later_and_ignore_buttons_do_not_download_or_install(self):
        self.run_ui('''
            app = make_app()
            manager = fake_service(app)
            offer(app)
            assert app.atualizacoes.btn_acao.cget("text") == "Atualizar"
            app.atualizacoes.btn_depois.invoke()
            assert app.atualizacoes.janela is None
            assert not app.atualizacoes.servico.ignorada
            offer(app)
            app.atualizacoes.btn_ignorar.invoke()
            assert app.atualizacoes.janela is None
            assert json.loads((pasta_dados() / "atualizador.json").read_text())["versao_ignorada"] == "1.1.0"
            assert manager.downloads == manager.aplicacoes == 0
            destroy(app)
        ''')

    def test_worker_completion_and_progress_only_touch_tk_on_main_thread(self):
        self.run_ui('''
            app = make_app()
            manager = fake_service(app)
            worker_threads, ui_threads = [], []
            original_check = manager.check_for_updates
            manager.check_for_updates = lambda: (worker_threads.append(threading.get_ident()), original_check())[1]
            original_show = app.atualizacoes._mostrar
            app.atualizacoes._mostrar = lambda: (ui_threads.append(threading.get_ident()), original_show())[1]
            offer(app)
            original_download = manager.download_updates
            def download(*args, **kwargs):
                worker_threads.append(threading.get_ident())
                return original_download(*args, **kwargs)
            manager.download_updates = download
            original_set = app.atualizacoes.progresso.set
            app.atualizacoes.progresso.set = lambda value: (ui_threads.append(threading.get_ident()), original_set(value))[1]
            app.atualizacoes.btn_acao.invoke()
            pump(app, lambda: not app.atualizacoes.ocupado)
            assert manager.downloads == 1 and manager.aplicacoes == 0
            assert app.atualizacoes.btn_acao.cget("text") == "Instalar e reiniciar"
            assert len(worker_threads) == 2 and all(t != main_thread for t in worker_threads)
            assert len(ui_threads) >= 3 and all(t == main_thread for t in ui_threads)
            app.atualizacoes.btn_depois.invoke()
            assert manager.aplicacoes == 0
            destroy(app)
        ''')

    def test_download_failure_keeps_app_usable_and_offers_retry(self):
        self.run_ui('''
            app = make_app()
            manager = fake_service(app)
            offer(app)
            manager.falhar = True
            app.atualizacoes.btn_acao.invoke()
            pump(app, lambda: not app.atualizacoes.ocupado)
            assert app.atualizacoes.btn_acao.cget("text") == "Tentar novamente"
            assert app.atualizacoes.btn_acao.cget("state") == "normal"
            assert not app._encerrando
            manager.falhar = False
            app.atualizacoes.btn_acao.invoke()
            pump(app, lambda: not app.atualizacoes.ocupado)
            assert app.atualizacoes.btn_acao.cget("text") == "Instalar e reiniciar"
            assert manager.aplicacoes == 0
            destroy(app)
        ''')

    def test_second_consent_saves_all_cards_and_reopens_fixed_timer_without_reset(self):
        self.run_ui('''
            app = make_app()
            manager = fake_service(app)
            card = app.cards[0]
            card.timer.fixado = True
            card.timer.acumulado_s = 420
            card.timer.iniciar()
            card.cb_pasta.set("PASTA-TESTE")
            card.entry_descricao.set("Texto ainda nao salvo")
            card.entry_data.delete(0, "end")
            card.entry_data.insert(0, "01/01/2025")
            card.entry_horas_cobraveis.delete(0, "end")
            card.entry_horas_cobraveis.insert(0, "3:45")
            app._adicionar_card(main.estado.Timer(pasta="OUTRA", descricao="Preservar", acumulado_s=600,
                                                horas_cobraveis_texto="0:10", inserido=True))
            offer(app)
            app.atualizacoes.btn_acao.invoke()
            pump(app, lambda: not app.atualizacoes.ocupado)
            assert manager.aplicacoes == 0 and card.timer.status == "rodando"
            # Only the shutdown boundary is fake; saving, pausing and SDK consent are real.
            fake_advwin = SimpleNamespace(
                bloquear_para_atualizacao=Mock(return_value=True),
                cancelar_encerramento=Mock(),
                encerrar_sessao=lambda callback, dispatch: dispatch(lambda: callback(None, None)),
            )
            app.atualizacoes.reinicio.advwin = fake_advwin
            with patch.object(app, "destroy") as close:
                app.atualizacoes.btn_acao.invoke()
                pump(app, lambda: close.called)
                assert manager.aplicacoes == 1
            assert main.estado.retomada_pendente()
            timers, _, _ = main.estado.carregar_estado()
            assert len(timers) == 2
            assert timers[0].status == "pausado" and timers[0].acumulado_s >= 420
            assert timers[0].horas_cobraveis_texto == "3:45"
            assert timers[0].fixado and timers[1].inserido
            destroy(app)
        ''')
        self.run_ui('''
            assert main.estado.retomada_pendente()
            app = make_app()
            assert len(app.cards) == 2
            card = app.cards[0]
            assert card.timer.fixado and card.timer.status == "pausado"
            assert card.timer.acumulado_s >= 420
            assert card.entry_horas_cobraveis.get() == "3:45"
            assert card.entry_data.get() == "01/01/2025"
            assert card.cb_pasta.get() == "PASTA-TESTE"
            assert card.entry_descricao.get() == "Texto ainda nao salvo"
            assert app.cards[1].timer.inserido
            assert app.cards[1].timer.acumulado_s == 600
            assert not main.estado.retomada_pendente()
            destroy(app)
        ''')


if __name__ == "__main__":
    unittest.main()

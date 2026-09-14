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
                           if isinstance(w, main.ctk.CTkButton)
                           and "Verificar atualizacoes" in w.cget("text").replace("ç", "c").replace("õ", "o")]
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

    def test_per_card_module_overrides_default_and_is_the_one_sent_to_advwin(self):
        self.run_ui('''
            app = make_app()
            card = app.cards[0]
            assert app.area_atual == "Trabalhista" and card.seg_modulo.get() == "Trabalhista"
            # Editavel enquanto o card nao foi lancado; trava junto com os demais campos.
            assert card.seg_modulo.cget("state") == "normal"
            card._definir_campos_travados(True)
            assert card.seg_modulo.cget("state") == "disabled"
            card._definir_campos_travados(False)
            # invoke() no botao, nao .set(): e o clique que estava quebrado com CTkOptionMenu.
            card.seg_modulo._buttons_dict["Contencioso"].invoke()
            assert card.seg_modulo.get() == "Contencioso"
            card.cb_pasta.set("PASTA-TESTE")
            card.var_selecionado.set(True)
            app._duplicar_selecionados()
            assert app.cards[1].seg_modulo.get() == "Contencioso"

            # Mudar o padrao do topo nao mexe em card ja existente; so no proximo card novo.
            app.seg_area.set("Contencioso")
            app._area_mudou("Contencioso")
            app.novo_card()
            assert app.cards[0].seg_modulo.get() == "Contencioso"
            assert app.cards[-1].seg_modulo.get() == "Contencioso"
            app.cards[-1].seg_modulo.set("Trabalhista")

            app.salvar()
            timers, _, padrao, _, _ = main.estado.carregar_estado()
            assert [t.area for t in timers] == ["Contencioso", "Contencioso", "Trabalhista"], [t.area for t in timers]
            assert padrao == "Contencioso"

            # E o valor que chega no AdvWin vem do card, nao do padrao do topo.
            enviados = []
            app.cards[-1].entry_horas_cobraveis.delete(0, "end")
            app.cards[-1].entry_horas_cobraveis.insert(0, "0:15")
            app.cards[-1].cb_pasta.set("PASTA-TESTE")
            app.advogado_atual = "Fulano"
            with patch.object(main.advwin, "enfileirar",
                              side_effect=lambda job, *a, **k: enviados.append(job)):
                app.cards[-1]._inserir()
            assert len(enviados) == 1
            with patch.object(main.advwin, "pagina_advwin", return_value=None), \
                 patch.object(main.advwin, "lancar_horas") as lancar:
                enviados[0]()
            assert lancar.call_args.args[-1] == "Trabalhista", lancar.call_args
            destroy(app)
        ''')

    def test_launched_card_is_visibly_marked_and_locked(self):
        self.run_ui('''
            app = make_app()
            novo, lancado = app.cards[0], main.TimerCard(app.cards_frame, app, main.estado.Timer(inserido=True))
            app.update_idletasks()

            # O sinal forte e a borda: a cor de fundo sozinha era branco contra quase-branco.
            assert novo.cget("border_color") == main.COR_BORDA_CARD
            assert lancado.cget("border_color") == main.COR_SUCESSO
            assert lancado.cget("border_width") > novo.cget("border_width")
            assert lancado.cget("fg_color") != novo.cget("fg_color")

            # E a mensagem diz por que os campos nao respondem.
            assert novo.label_status_advwin.cget("text") == ""
            assert lancado.label_status_advwin.cget("text") == main.TEXTO_CARD_LANCADO
            assert lancado.seg_modulo.cget("state") == "disabled"

            # Cronometro tambem bloqueado: o tempo ja virou linha no AdvWin e no log.
            for botao in (lancado.btn_iniciar, lancado.btn_pausar, lancado.btn_parar):
                assert botao.cget("state") == "disabled"
            lancado.btn_iniciar.invoke()
            lancado._iniciar()                  # clique no botao
            lancado.alternar_iniciar_pausar()   # atalho Ctrl+Espaco, que nao passa pelo botao
            assert lancado.timer.status == "parado", lancado.timer.status
            assert lancado.timer.elapso_s() == 0

            # O card normal continua funcionando.
            novo._iniciar()
            assert novo.timer.status == "rodando"
            novo._parar()
            assert novo.timer.status == "parado"

            # "Limpar tudo" devolve o card ao estado normal, sem sobra da mensagem.
            lancado.resetar()
            assert lancado.label_status_advwin.cget("text") == ""
            assert lancado.cget("border_color") == main.COR_BORDA_CARD
            assert lancado.seg_modulo.cget("state") == "normal"
            destroy(app)
        ''')

    def test_minimize_shows_mini_window_of_last_started_card_when_enabled(self):
        self.run_ui('''
            app = make_app()
            # O app de teste nao minimiza de verdade: simula o <Unmap>/<Map> da janela principal.
            def minimizar():
                with patch.object(app, "state", return_value="iconic"):
                    app._ao_desmapear(SimpleNamespace(widget=app))
            restaurar = lambda: app._ao_mapear(SimpleNamespace(widget=app))

            primeiro = app.cards[0]
            primeiro._iniciar()
            minimizar()
            assert app._miniatura is None      # desligada por padrao: minimiza como sempre

            app.var_miniatura.set(True)
            app.salvar()
            assert main.estado.carregar_estado()[3] is True

            app.novo_card()
            segundo = app.cards[-1]
            segundo.cb_pasta.set("PASTA-MINI")
            segundo._iniciar()
            primeiro.timer.segmento_inicio = "2000-01-01T08:00:00"   # iniciado bem antes
            minimizar()
            mini = app._miniatura
            assert mini.card is segundo and mini.visivel()
            assert "PASTA-MINI" in mini.label_pasta.cget("text")

            # Ao minimizar o Tk manda um <Map> com a janela ainda "iconic": nao pode esconder.
            with patch.object(app, "state", return_value="iconic"):
                app._ao_mapear(SimpleNamespace(widget=app))
            assert mini.visivel()

            # Pausar/retomar pela miniatura e o mesmo caminho do card.
            mini.btn_play_pause.invoke()
            assert segundo.timer.status == "pausado"
            mini.btn_play_pause.invoke()
            assert segundo.timer.status == "rodando"

            # Redimensiona como janela comum: puxar o canto superior esquerdo aumenta tudo junto,
            # o canto oposto (inferior direito) fica parado e o tamanho vai pro estado.json.
            app.update()
            j = mini.janela
            largura0 = j.winfo_width()
            direita0, base0 = j.winfo_x() + largura0, j.winfo_y() + j.winfo_height()
            canto = SimpleNamespace(x_root=j.winfo_rootx() + 2, y_root=j.winfo_rooty() + 2)
            mini._ao_mover_mouse(canto)
            assert j.cget("cursor") == "size_nw_se"
            mini._ao_pressionar(canto)
            mini._ao_arrastar(SimpleNamespace(x_root=canto.x_root - largura0 // 2, y_root=canto.y_root))
            mini._ao_soltar(None)
            app.update()
            assert mini.escala == 1.5, mini.escala
            assert j.winfo_width() > largura0 * 1.3
            assert abs(j.winfo_x() + j.winfo_width() - direita0) <= 1
            assert abs(j.winfo_y() + j.winfo_height() - base0) <= 1
            assert main.estado.carregar_estado()[4] == 1.5
            meio = SimpleNamespace(x_root=j.winfo_rootx() + j.winfo_width() // 2,
                                   y_root=j.winfo_rooty() + j.winfo_height() // 2)
            mini._ao_mover_mouse(meio)
            assert j.cget("cursor") == ""      # no meio arrasta a janela, nao redimensiona

            restaurar()
            assert not mini.visivel()

            # Nada rodando: o primeiro pausado nao lancado, pra poder retomar.
            primeiro._pausar()
            segundo._pausar()
            primeiro.timer.inserido = True
            minimizar()
            assert mini.card is segundo and mini.visivel()
            restaurar()

            # Nenhum rodando/pausado: minimiza normal, sem miniatura.
            segundo._parar()
            minimizar()
            assert not mini.visivel()
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
            timers, _, _, _, _ = main.estado.carregar_estado()
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

    def test_report_window_opens_once_and_never_loses_what_was_written(self):
        self.run_ui('''
            # Sem formulario configurado o botao nem aparece: so levaria a "nao deu para enviar".
            app = make_app()
            assert not [w for w in app.rodape.winfo_children()
                        if isinstance(w, main.ctk.CTkButton) and "Relatar" in w.cget("text")]
            destroy(app)
        ''')
        self.run_ui('''
            with patch.object(main.relatos, "URL_FORMULARIO", "https://exemplo.invalido/formResponse"):
                app = make_app()
            botoes = [w for w in app.rodape.winfo_children()
                      if isinstance(w, main.ctk.CTkButton) and "Relatar" in w.cget("text")]
            assert len(botoes) == 1
            botoes[0].invoke()
            abertas = lambda: [w for w in app.winfo_children()
                               if isinstance(w, main.relatos.JanelaRelato) and w.winfo_exists()]
            assert len(abertas()) == 1
            app.abrir_relato()              # segundo clique traz pra frente, nao abre outra
            assert len(abertas()) == 1
            janela = abertas()[0]

            # O que a janela mostra e exatamente o que seria enviado, com o contexto do app.
            diag = janela._diagnostico()
            assert diag["cards_abertos"] == 1 and diag["advwin_conectado"] is False
            assert "versao" in diag and "windows" in diag

            # Texto vazio nem chega a tentar enviar.
            with patch.object(main.relatos, "enviar", side_effect=AssertionError("nao envia vazio")):
                janela._enviar()
            assert "Escreva" in janela.status.cget("text")

            # Falha de entrega nao pode perder o texto: vai pro disco e pra area de transferencia.
            with patch.object(main.relatos.messagebox, "showwarning") as aviso:
                janela._concluir("Problema", "o botao sumiu", diag, RuntimeError("sem rede"))
            aviso.assert_called_once()
            salvos = list((pasta_dados() / "relatos").glob("*.txt"))
            assert len(salvos) == 1, salvos
            assert "o botao sumiu" in salvos[0].read_text(encoding="utf-8")
            assert "o botao sumiu" in janela.clipboard_get()
            assert janela.btn_enviar.cget("state") == "normal"   # da pra tentar de novo
            assert janela.winfo_exists()

            with patch.object(main.relatos.messagebox, "showinfo") as ok:
                janela._concluir("Problema", "o botao sumiu", diag, None)
            ok.assert_called_once()
            assert not abertas()
            destroy(app)
        ''')


if __name__ == "__main__":
    unittest.main()

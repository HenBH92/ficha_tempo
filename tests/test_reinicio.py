import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


class ReinicioTest(unittest.TestCase):
    def setUp(self):
        from reinicio import ReinicioSeguro
        self.ordem = []
        self.app = SimpleNamespace(_encerrando=False, cards=[], tem_previa_aberta=lambda: False,
                                   salvar=lambda **kw: self.ordem.append("salvar"))
        self.fila = SimpleNamespace(bloquear_para_atualizacao=lambda: True,
                                    cancelar_encerramento=lambda: self.ordem.append("liberar"),
                                    encerrar_sessao=self.encerrar)
        self.app.agendar_ui = lambda callback: callback()
        self.reinicio = ReinicioSeguro(self.app, self.fila)

    def encerrar(self, retorno, despachar):
        self.ordem.append("fechar_browser")
        despachar(lambda: retorno(None, None))

    def test_salva_antes_de_fechar_browser_e_aplicar(self):
        self.reinicio.iniciar(lambda: self.ordem.append("aplicar"), self.fail)
        self.assertEqual(self.ordem, ["salvar", "fechar_browser", "aplicar"])

    def test_ocupado_nao_salva_nem_fecha(self):
        self.fila.bloquear_para_atualizacao = lambda: False
        with self.assertRaisesRegex(RuntimeError, "AdvWin"):
            self.reinicio.iniciar(lambda: self.fail(), self.fail)
        self.assertEqual(self.ordem, [])
        self.assertFalse(self.app._encerrando)

    def test_previa_aberta_nao_fecha(self):
        self.app.tem_previa_aberta = lambda: True
        with self.assertRaisesRegex(RuntimeError, "prévia"):
            self.reinicio.iniciar(lambda: self.fail(), self.fail)
        self.assertEqual(self.ordem, [])

    def test_falha_salvamento_aborta_e_restaura_timer(self):
        timer = SimpleNamespace(status="rodando", acumulado_s=10, segmento_inicio="original")
        def pausar():
            timer.status, timer.acumulado_s, timer.segmento_inicio = "pausado", 15, None
        timer.pausar = pausar
        self.app.cards = [SimpleNamespace(timer=timer)]
        def falha(**kwargs):
            raise OSError("disco cheio")
        self.app.salvar = falha
        with self.assertRaises(OSError):
            self.reinicio.iniciar(lambda: self.fail(), self.fail)
        self.assertEqual(self.ordem, ["liberar"])
        self.assertEqual(timer.status, "rodando")
        self.assertEqual(timer.acumulado_s, 10)
        self.assertEqual(timer.segmento_inicio, "original")
        self.assertFalse(self.app._encerrando)

    def test_erro_encerramento_nao_aplica(self):
        erros = []
        self.fila.encerrar_sessao = lambda retorno, despachar: retorno(None, OSError("Chrome"))
        self.reinicio.iniciar(lambda: self.fail(), erros.append)
        self.assertEqual(len(erros), 1)
        self.assertFalse(self.app._encerrando)


class PersistenciaTest(unittest.TestCase):
    def test_falha_antes_substituicao_preserva_ultimo_arquivo(self):
        from persistencia import gravar_json_atomico
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "estado.json"
            destino.write_text('{"anterior":true}', encoding="utf-8")
            with patch("persistencia.os.replace", side_effect=OSError("disco indisponível")):
                with self.assertRaises(OSError):
                    gravar_json_atomico(destino, {"novo": True})
            self.assertEqual(destino.read_text(encoding="utf-8"), '{"anterior":true}')


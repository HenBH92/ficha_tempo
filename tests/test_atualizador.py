import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import atualizador


class GerenciadorFalso:
    def __init__(self):
        self.alvo = SimpleNamespace(Version="1.1.0", NotesMarkdown="Correções", PackageId="VLFAdvogados.FichaTempo")
        self.info = SimpleNamespace(TargetFullRelease=self.alvo, IsDowngrade=False)
        self.pendente = None
        self.downloads = 0
        self.aplicacoes = 0
        self.falhar = False

    def get_current_version(self):
        return "1.0.0"

    def get_update_pending_restart(self):
        return self.pendente

    def check_for_updates(self):
        if self.falhar:
            raise OSError("sem rede")
        return self.info

    def download_updates(self, info, progress_callback=None):
        self.downloads += 1
        if self.falhar:
            raise OSError("interrompido")
        self.pendente = info.TargetFullRelease
        if progress_callback:
            progress_callback(100)

    def wait_exit_then_apply_updates(self, update, **kwargs):
        self.aplicacoes += 1


class AtualizadorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pasta = Path(self.tmp.name)
        self.mgr = GerenciadorFalso()
        self.servico = atualizador.ServicoAtualizacao(self.pasta, lambda: self.mgr)

    def test_consultar_nao_baixa_nem_instala(self):
        nova = self.servico.verificar()
        self.assertEqual(nova.versao, "1.1.0")
        self.assertEqual(self.mgr.downloads, 0)
        self.assertEqual(self.mgr.aplicacoes, 0)

    def test_ignorar_persiste_apenas_versao_e_manual_contorna(self):
        self.servico.ignorar("1.1.0")
        outro = atualizador.ServicoAtualizacao(self.pasta, lambda: self.mgr)
        self.assertIsNone(outro.verificar())
        self.assertEqual(outro.verificar(manual=True).versao, "1.1.0")
        self.mgr.alvo.Version = "1.2.0"
        self.assertEqual(outro.verificar().versao, "1.2.0")

    def test_download_precisa_de_confirmacao_separada_para_instalar(self):
        nova = self.servico.verificar()
        self.servico.baixar(nova)
        self.assertEqual(self.mgr.downloads, 1)
        self.assertEqual(self.mgr.aplicacoes, 0)
        self.servico.preparar_instalacao(nova)
        self.assertEqual(self.mgr.aplicacoes, 1)

    def test_pacote_pendente_apos_reabrir_nao_instala_sozinho(self):
        self.mgr.pendente = self.mgr.alvo
        self.mgr.falhar = True
        nova = self.servico.verificar()
        self.assertTrue(nova.baixada)
        self.assertEqual(self.mgr.aplicacoes, 0)

    def test_download_interrompido_nao_permite_instalar(self):
        nova = self.servico.verificar()
        self.mgr.falhar = True
        with self.assertRaises(OSError):
            self.servico.baixar(nova)
        with self.assertRaises(RuntimeError):
            self.servico.preparar_instalacao(nova)
        self.assertEqual(self.mgr.aplicacoes, 0)

    def test_recusa_downgrade_e_pre_release(self):
        for versao in ["1.0.0", "0.9.0", "1.2.0-beta.1"]:
            self.mgr.alvo.Version = versao
            self.assertIsNone(self.servico.verificar())

    def test_preferencias_corrompidas_nao_impedem_consulta(self):
        (self.pasta / "atualizador.json").write_text("[", encoding="utf-8")
        outro = atualizador.ServicoAtualizacao(self.pasta, lambda: self.mgr)
        self.assertIsNotNone(outro.verificar())


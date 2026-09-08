import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_metadata import gerar_metadados, validar_versao


class VersaoBuildTests(unittest.TestCase):
    def test_versoes_estaveis(self):
        self.assertEqual(validar_versao('1.2.3'), (1, 2, 3))
        self.assertEqual(validar_versao('0.0.1'), (0, 0, 1))
        self.assertEqual(validar_versao('65535.1.0'), (65535, 1, 0))

    def test_rejeita_versoes_ambiguas_ou_incompativeis(self):
        for versao in ('v1.2.3', '1.2', '1.2.3.4', '01.2.3', '1.2.3-beta',
                       '1.2.3+build', '1.2.3\n', '1.2.3;whoami', '0.0.0', '65536.0.0'):
            with self.subTest(versao=versao), self.assertRaises(ValueError):
                validar_versao(versao)

    def test_metadados_preservam_mesma_versao_em_json_e_recurso_windows(self):
        with tempfile.TemporaryDirectory() as pasta:
            destino = Path(pasta)
            gerar_metadados('1.2.3', 'A' * 40, destino)
            self.assertEqual(json.loads((destino / 'build-info.json').read_text()),
                             {'versao': '1.2.3', 'commit': 'a' * 40})
            recurso = (destino / 'version-resource.txt').read_text()
            self.assertIn('filevers=(1, 2, 3, 0)', recurso)
            self.assertIn("StringStruct('ProductVersion', '1.2.3')", recurso)

    def test_metadados_invalidos_nao_criam_arquivos(self):
        with tempfile.TemporaryDirectory() as pasta:
            destino = Path(pasta) / 'metadata'
            with self.assertRaises(ValueError):
                gerar_metadados('1.2.3', 'commit-invalido', destino)
            self.assertFalse(destino.exists())


if __name__ == '__main__':
    unittest.main()

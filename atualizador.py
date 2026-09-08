"""Atualizações opcionais: consulta, download e aplicação são ações separadas."""
import json
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from caminhos import APP_ID, pasta_dados
from persistencia import gravar_json_atomico

REPO_URL = "https://github.com/HenBH92/ficha_tempo-releases"
INTERVALO_MS = 4 * 60 * 60 * 1000
log = logging.getLogger(__name__)


class NaoInstalado(RuntimeError):
    pass


def criar_gerenciador():
    if not getattr(sys, "frozen", False):
        raise NaoInstalado("As atualizações estão disponíveis na versão instalada do programa.")
    import velopack
    try:
        gerente = velopack.UpdateManager(
            velopack.GithubSource(REPO_URL, prerelease=False),
            velopack.UpdateOptions(AllowVersionDowngrade=False, MaximumDeltasBeforeFallback=-1),
        )
        if gerente.get_is_portable() or gerente.get_app_id() != APP_ID:
            raise NaoInstalado("Instale o programa pelo instalador para receber atualizações.")
        return gerente
    except NaoInstalado:
        raise
    except Exception as erro:
        raise NaoInstalado("Não foi possível identificar a instalação do programa.") from erro


def _versao_estavel(texto):
    if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", texto):
        return None
    return tuple(map(int, texto.split(".")))


@dataclass
class NovaVersao:
    versao: str
    notas: str
    pacote: object
    baixada: bool = False


class ServicoAtualizacao:
    """Chamadas de rede são síncronas; o controlador as executa fora do Tkinter."""

    def __init__(self, pasta: Path | None = None, fabrica=criar_gerenciador):
        self.pasta = pasta if pasta is not None else pasta_dados()
        self.arquivo = self.pasta / "atualizador.json"
        self.fabrica = fabrica
        self._gerente = None
        self.ignorada = ""
        try:
            dados = json.loads(self.arquivo.read_text(encoding="utf-8"))
            if isinstance(dados, dict):
                self.ignorada = dados.get("versao_ignorada", "")
        except (OSError, ValueError):
            pass

    @property
    def gerente(self):
        if self._gerente is None:
            self._gerente = self.fabrica()
        return self._gerente

    def _nova(self, pacote, baixada=False):
        alvo = pacote if baixada else pacote.TargetFullRelease
        versao = _versao_estavel(alvo.Version)
        atual = _versao_estavel(self.gerente.get_current_version())
        if (not versao or not atual or versao <= atual or alvo.PackageId != APP_ID
                or (not baixada and pacote.IsDowngrade)):
            return None
        return NovaVersao(alvo.Version, alvo.NotesMarkdown or "Melhorias e correções.", pacote, baixada)

    def verificar(self, manual=False):
        pendente = self.gerente.get_update_pending_restart()
        nova_pendente = self._nova(pendente, True) if pendente else None
        try:
            info = self.gerente.check_for_updates()
        except Exception:
            if nova_pendente is None:
                raise
            log.info("Consulta indisponível; oferecendo pacote já baixado.", exc_info=True)
            info = None
        nova = self._nova(info) if info else None
        if nova_pendente and (nova is None or _versao_estavel(nova_pendente.versao) >= _versao_estavel(nova.versao)):
            nova = nova_pendente
        if nova and not manual and nova.versao == self.ignorada:
            return None
        return nova

    def ignorar(self, versao):
        gravar_json_atomico(self.arquivo, {"versao_ignorada": versao})
        self.ignorada = versao

    def baixar(self, nova, progresso=None):
        if not nova.baixada:
            self.gerente.download_updates(nova.pacote, progress_callback=progresso)
            nova.baixada = True

    def preparar_instalacao(self, nova):
        if not nova.baixada:
            raise RuntimeError("A atualização ainda não terminou de baixar.")
        self.gerente.wait_exit_then_apply_updates(nova.pacote, silent=False, restart=True)

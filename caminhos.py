"""Caminhos de recursos (empacotados no exe, somente leitura) e de dados (graváveis, por usuário)."""
import os
import json
import sys
from pathlib import Path

NOME_APP = "VLF Ficha de Tempo"
APP_ID = "VLFAdvogados.FichaTempo"


def pasta_recursos() -> Path:
    """Onde ficam modelo/logo/ícone empacotados junto com o app."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent


def pasta_dados() -> Path:
    """Onde ficam estado.json e as planilhas do dia — por usuário, fora da pasta do exe."""
    base = Path(os.getenv("APPDATA", Path.home())) / NOME_APP
    base.mkdir(parents=True, exist_ok=True)
    return base


def informacoes_build() -> dict:
    arquivo = pasta_recursos() / "build-info.json"
    if arquivo.exists():
        return json.loads(arquivo.read_text(encoding="utf-8-sig"))
    return {"versao": "1.0.0", "commit": "desenvolvimento"}


VERSAO = informacoes_build()["versao"]

"""Valida a versao unica e registra a origem do executavel distribuido."""

import argparse
import importlib.metadata
import json
import platform
import re
from pathlib import Path


def validar_versao(versao: str) -> tuple[int, int, int]:
    if not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", versao):
        raise ValueError("Use uma versao estavel X.Y.Z, sem prefixo v, zeros extras ou sufixos.")
    partes = tuple(map(int, versao.split(".")))
    if partes == (0, 0, 0) or any(parte > 65535 for parte in partes):
        raise ValueError("A versao deve ser maior que 0.0.0 e cada parte deve caber em 16 bits.")
    return partes


def validar_ambiente(raiz: Path) -> None:
    if platform.python_version() != "3.14.0" or platform.architecture()[0] != "64bit":
        raise ValueError("O build requer Python 3.14.0 x64.")
    for nome in ("requirements.txt", "requirements-build.txt"):
        for linha in (raiz / nome).read_text(encoding="utf-8").splitlines():
            if not linha or linha.startswith(("#", "-r ")):
                continue
            pacote, esperado = linha.split("==", 1)
            instalado = importlib.metadata.version(pacote)
            if instalado != esperado:
                raise ValueError(f"Dependencia {pacote}: esperado {esperado}, instalado {instalado}.")


def gerar_metadados(versao: str, commit: str, destino: Path) -> None:
    partes = validar_versao(versao)
    if not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
        raise ValueError("Commit deve ser o SHA Git completo de 40 caracteres.")
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "build-info.json").write_text(
        json.dumps({"versao": versao, "commit": commit.lower()}, indent=2) + "\n",
        encoding="utf-8",
    )
    recurso = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={(*partes, 0)!r}, prodvers={(*partes, 0)!r},
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('041604B0', [
    StringStruct('CompanyName', 'VLF Advogados'),
    StringStruct('FileDescription', 'Ficha Tempo VLF'),
    StringStruct('FileVersion', '{versao}'),
    StringStruct('ProductName', 'Ficha Tempo VLF'),
    StringStruct('ProductVersion', '{versao}'),
    StringStruct('OriginalFilename', 'FichaTempo_VLF.exe')])]),
    VarFileInfo([VarStruct('Translation', [1046, 1200])])])
"""
    (destino / "version-resource.txt").write_text(recurso, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--check-environment", action="store_true")
    args = parser.parse_args()
    try:
        validar_versao(args.version)
        if args.check_environment:
            validar_ambiente(Path(__file__).resolve().parents[1])
        gerar_metadados(args.version, args.commit, args.output)
    except (ValueError, importlib.metadata.PackageNotFoundError) as erro:
        parser.error(str(erro))

"""Modelos de descrição reutilizáveis, sugeridos ao digitar "/" no campo Descrição."""
import json

from caminhos import pasta_dados

ARQUIVO_MODELOS = pasta_dados() / "modelos_descricao.json"


def carregar_modelos() -> list[str]:
    if not ARQUIVO_MODELOS.exists():
        return []
    return json.loads(ARQUIVO_MODELOS.read_text(encoding="utf-8"))


def salvar_modelos(modelos: list[str]) -> None:
    ARQUIVO_MODELOS.write_text(
        json.dumps(modelos, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def adicionar_modelo(texto: str) -> list[str]:
    modelos = carregar_modelos()
    if texto and texto not in modelos:
        modelos.append(texto)
        salvar_modelos(modelos)
    return modelos


def remover_modelo(texto: str) -> list[str]:
    modelos = carregar_modelos()
    if texto in modelos:
        modelos.remove(texto)
        salvar_modelos(modelos)
    return modelos


def _demo():
    import os

    if ARQUIVO_MODELOS.exists():
        os.remove(ARQUIVO_MODELOS)

    assert carregar_modelos() == []
    adicionar_modelo("Elaboração de contestação")
    modelos = adicionar_modelo("Elaboração de contestação")  # duplicado, não deve repetir
    assert modelos == ["Elaboração de contestação"]
    modelos = remover_modelo("Elaboração de contestação")
    assert modelos == []

    os.remove(ARQUIVO_MODELOS)
    print("modelos.py OK")


if __name__ == "__main__":
    _demo()

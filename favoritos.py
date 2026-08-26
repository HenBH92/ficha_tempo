"""Pastas e clientes favoritos: aparecem primeiro/nas listas de sugestão."""
import json

from caminhos import pasta_dados

ARQUIVO_FAVORITOS = pasta_dados() / "favoritos.json"


def _carregar() -> dict[str, list[str]]:
    if not ARQUIVO_FAVORITOS.exists():
        return {"pastas": [], "clientes": []}
    dados = json.loads(ARQUIVO_FAVORITOS.read_text(encoding="utf-8"))
    return {"pastas": dados.get("pastas", []), "clientes": dados.get("clientes", [])}


def _salvar(dados: dict[str, list[str]]) -> None:
    ARQUIVO_FAVORITOS.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def carregar_pastas() -> list[str]:
    return _carregar()["pastas"]


def carregar_clientes() -> list[str]:
    return _carregar()["clientes"]


def alternar_pasta(valor: str) -> list[str]:
    dados = _carregar()
    if valor in dados["pastas"]:
        dados["pastas"].remove(valor)
    else:
        dados["pastas"].append(valor)
    _salvar(dados)
    return dados["pastas"]


def alternar_cliente(valor: str) -> list[str]:
    dados = _carregar()
    if valor in dados["clientes"]:
        dados["clientes"].remove(valor)
    else:
        dados["clientes"].append(valor)
    _salvar(dados)
    return dados["clientes"]


def _demo():
    import os

    if ARQUIVO_FAVORITOS.exists():
        os.remove(ARQUIVO_FAVORITOS)

    assert carregar_pastas() == [] and carregar_clientes() == []
    alternar_pasta("123VT-CIV-0001.01")
    assert carregar_pastas() == ["123VT-CIV-0001.01"]
    alternar_cliente("Cliente Teste")
    assert carregar_clientes() == ["Cliente Teste"]
    alternar_pasta("123VT-CIV-0001.01")  # alterna de volta (remove)
    assert carregar_pastas() == []

    os.remove(ARQUIVO_FAVORITOS)
    print("favoritos.py OK")


if __name__ == "__main__":
    _demo()

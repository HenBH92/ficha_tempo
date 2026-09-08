"""Gravação atômica: uma falha não trunca o último estado salvo."""
import json
import os
from pathlib import Path
import tempfile


def gravar_json_atomico(destino: Path, conteudo) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destino.parent,
                                         prefix=f".{destino.name}.", suffix=".tmp", delete=False) as arquivo:
            temporario = Path(arquivo.name)
            json.dump(conteudo, arquivo, ensure_ascii=False, indent=2)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, destino)
    finally:
        if temporario is not None:
            temporario.unlink(missing_ok=True)

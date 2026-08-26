"""Checagem e instalação silenciosa de atualizações via GitHub Releases."""
import json
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from caminhos import VERSAO

REPO = "SEU-USUARIO/ficha-tempo"  # troque pelo "dono/nome" do repositório no GitHub
URL_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"


def _versao_para_tupla(versao: str) -> tuple[int, ...]:
    partes = []
    for parte in versao.strip().lstrip("vV").split("."):
        try:
            partes.append(int(parte))
        except ValueError:
            break
    return tuple(partes)


def verificar_nova_versao() -> dict | None:
    """Consulta a última release no GitHub. Retorna {"versao", "url"} se houver algo mais novo, senão None.
    Qualquer falha (sem internet, repo ainda não existe, GitHub fora do ar) é silenciosa: apenas não atualiza."""
    try:
        with urllib.request.urlopen(URL_LATEST, timeout=6) as resp:
            dados = json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None

    tag = dados.get("tag_name", "")
    if _versao_para_tupla(tag) <= _versao_para_tupla(VERSAO):
        return None

    asset = next((a for a in dados.get("assets", []) if a["name"].lower().endswith(".exe")), None)
    if not asset:
        return None
    return {"versao": tag, "url": asset["browser_download_url"]}


def baixar_instalador(url: str) -> Path:
    destino = Path(tempfile.gettempdir()) / "VLF-FichaDeTempo-Update.exe"
    urllib.request.urlretrieve(url, destino)
    return destino


def instalar_silenciosamente(caminho_instalador: Path) -> None:
    """Roda o instalador em segundo plano: ele fecha o app, atualiza os arquivos e reabre sozinho."""
    subprocess.Popen(
        [str(caminho_instalador), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
         "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"],
        close_fds=True,
    )


def _demo():
    assert _versao_para_tupla("v1.2.10") == (1, 2, 10)
    assert _versao_para_tupla("1.2.10") > _versao_para_tupla("1.2.9")
    assert _versao_para_tupla("1.10.0") > _versao_para_tupla("1.9.0")
    assert _versao_para_tupla("lixo") == ()
    assert verificar_nova_versao() is None  # repo placeholder não existe -> falha silenciosa
    print("atualizador.py OK")


if __name__ == "__main__":
    _demo()

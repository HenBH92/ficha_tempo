"""Timer com máquina de estado start/pause/stop e persistência em JSON."""
import json
import time
import uuid
from dataclasses import dataclass, field, asdict, fields
from datetime import datetime

from caminhos import pasta_dados
from persistencia import gravar_json_atomico

ARQUIVO_ESTADO = pasta_dados() / "estado.json"


@dataclass
class Timer:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    status: str = "parado"  # parado | rodando | pausado
    segmento_inicio: str | None = None
    acumulado_s: float = 0.0
    data: str = ""
    advogado: str = ""
    cliente: str = ""
    pasta: str = ""
    descricao: str = ""
    horas_cobraveis_texto: str = ""
    inserido: bool = False  # já lançado no AdvWin e registrado no log local
    fixado: bool = False

    def elapso_s(self) -> float:
        extra = 0.0
        if self.status == "rodando" and self.segmento_inicio:
            extra = (datetime.now() - datetime.fromisoformat(self.segmento_inicio)).total_seconds()
        return self.acumulado_s + extra

    def elapso_fmt(self) -> str:
        s = int(self.elapso_s())
        return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"

    def iniciar(self) -> None:
        self.segmento_inicio = datetime.now().isoformat()
        self.status = "rodando"

    def pausar(self) -> None:
        if self.status == "rodando":
            self.acumulado_s = self.elapso_s()
            self.segmento_inicio = None
        self.status = "pausado"

    def parar(self) -> None:
        self.acumulado_s = self.elapso_s()
        self.segmento_inicio = None
        self.status = "parado"


def salvar_estado(timers: list[Timer], advogado_atual: str = "", area_atual: str = "Trabalhista",
                  retomada_atualizacao: bool = False) -> None:
    conteudo = {
        "advogado_atual": advogado_atual,
        "area_atual": area_atual,
        "timers": [asdict(t) for t in timers],
        "retomada_atualizacao": retomada_atualizacao,
    }
    gravar_json_atomico(ARQUIVO_ESTADO, conteudo)


def retomada_pendente() -> bool:
    if not ARQUIVO_ESTADO.exists():
        return False
    return json.loads(ARQUIVO_ESTADO.read_text(encoding="utf-8")).get("retomada_atualizacao", False) is True


def carregar_estado() -> tuple[list[Timer], str, str]:
    if not ARQUIVO_ESTADO.exists():
        return [], "", "Trabalhista"
    conteudo = json.loads(ARQUIVO_ESTADO.read_text(encoding="utf-8"))
    campos_validos = {f.name for f in fields(Timer)}
    timers = [Timer(**{k: v for k, v in d.items() if k in campos_validos}) for d in conteudo["timers"]]
    for t in timers:
        if t.status == "rodando":
            t.pausar()
    return timers, conteudo.get("advogado_atual", ""), conteudo.get("area_atual", "Trabalhista")


def _demo():
    t = Timer()
    t.iniciar()
    time.sleep(1.1)
    t.pausar()
    assert 1.0 < t.elapso_s() < 1.3, t.elapso_s()
    t.iniciar()
    time.sleep(0.5)
    t.parar()
    assert t.status == "parado"
    assert t.elapso_s() > 1.5
    print("estado.py OK")


if __name__ == "__main__":
    _demo()

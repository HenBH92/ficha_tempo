"""Ícones desenhados via PIL (não dependem do emoji do Windows, que varia entre máquinas
e não respeita a cor do botão). Cada ícone é desenhado numa resolução maior e reduzido
(antialiasing), e o resultado fica em cache por (nome, tamanho, cor)."""
import math
from functools import lru_cache

import customtkinter as ctk
from PIL import Image, ImageDraw

TAMANHO_PADRAO = 18
_ESCALA = 4  # resolução de desenho = tamanho final * _ESCALA, depois reduz


def _tela(tamanho: int) -> tuple[Image.Image, ImageDraw.ImageDraw, int]:
    lado = tamanho * _ESCALA
    img = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img), lado


def _reduzir(img: Image.Image, tamanho: int) -> Image.Image:
    return img.resize((tamanho, tamanho), Image.LANCZOS)


def _play(tamanho: int, cor: str) -> Image.Image:
    img, d, w = _tela(tamanho)
    d.polygon([(0.30 * w, 0.20 * w), (0.30 * w, 0.80 * w), (0.82 * w, 0.50 * w)], fill=cor)
    return _reduzir(img, tamanho)


def _pause(tamanho: int, cor: str) -> Image.Image:
    img, d, w = _tela(tamanho)
    d.rounded_rectangle((0.26 * w, 0.20 * w, 0.44 * w, 0.80 * w), radius=0.04 * w, fill=cor)
    d.rounded_rectangle((0.56 * w, 0.20 * w, 0.74 * w, 0.80 * w), radius=0.04 * w, fill=cor)
    return _reduzir(img, tamanho)


def _stop(tamanho: int, cor: str) -> Image.Image:
    img, d, w = _tela(tamanho)
    d.rounded_rectangle((0.24 * w, 0.24 * w, 0.76 * w, 0.76 * w), radius=0.08 * w, fill=cor)
    return _reduzir(img, tamanho)


def _inserir(tamanho: int, cor: str) -> Image.Image:
    img, d, w = _tela(tamanho)
    espessura = max(1, round(0.07 * w))
    d.line((0.5 * w, 0.14 * w, 0.5 * w, 0.52 * w), fill=cor, width=espessura)
    d.polygon([(0.32 * w, 0.44 * w), (0.68 * w, 0.44 * w), (0.5 * w, 0.66 * w)], fill=cor)
    d.line((0.2 * w, 0.80 * w, 0.2 * w, 0.88 * w), fill=cor, width=espessura)
    d.line((0.2 * w, 0.88 * w, 0.8 * w, 0.88 * w), fill=cor, width=espessura)
    d.line((0.8 * w, 0.88 * w, 0.8 * w, 0.80 * w), fill=cor, width=espessura)
    return _reduzir(img, tamanho)


def _remover(tamanho: int, cor: str) -> Image.Image:
    img, d, w = _tela(tamanho)
    espessura = max(1, round(0.06 * w))
    d.line((0.20 * w, 0.28 * w, 0.80 * w, 0.28 * w), fill=cor, width=espessura)
    d.rounded_rectangle((0.40 * w, 0.15 * w, 0.60 * w, 0.24 * w), radius=0.02 * w, outline=cor, width=espessura)
    d.rounded_rectangle((0.27 * w, 0.28 * w, 0.73 * w, 0.85 * w), radius=0.05 * w, outline=cor, width=espessura)
    d.line((0.41 * w, 0.40 * w, 0.41 * w, 0.74 * w), fill=cor, width=espessura)
    d.line((0.59 * w, 0.40 * w, 0.59 * w, 0.74 * w), fill=cor, width=espessura)
    return _reduzir(img, tamanho)


def _fixar(tamanho: int, cor: str) -> Image.Image:
    img, d, w = _tela(tamanho)
    d.ellipse((0.28 * w, 0.14 * w, 0.72 * w, 0.58 * w), fill=cor)
    d.polygon([(0.36 * w, 0.50 * w), (0.64 * w, 0.50 * w), (0.5 * w, 0.86 * w)], fill=cor)
    return _reduzir(img, tamanho)


def _salvar(tamanho: int, cor: str) -> Image.Image:
    img, d, w = _tela(tamanho)
    espessura = max(1, round(0.06 * w))
    d.rounded_rectangle((0.16 * w, 0.16 * w, 0.84 * w, 0.84 * w), radius=0.06 * w, outline=cor, width=espessura)
    d.rectangle((0.30 * w, 0.16 * w, 0.70 * w, 0.38 * w), fill=cor)
    d.rectangle((0.30 * w, 0.56 * w, 0.70 * w, 0.76 * w), outline=cor, width=espessura)
    return _reduzir(img, tamanho)


def _estrela(tamanho: int, cor: str) -> Image.Image:
    img, d, w = _tela(tamanho)
    cx = cy = w / 2
    r_ext, r_int = w * 0.40, w * 0.16
    pontos = []
    for i in range(10):
        r = r_ext if i % 2 == 0 else r_int
        ang = -math.pi / 2 + i * math.pi / 5
        pontos.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    d.polygon(pontos, fill=cor)
    return _reduzir(img, tamanho)


def _sol(tamanho: int, cor: str) -> Image.Image:
    img, d, w = _tela(tamanho)
    cx = cy = w / 2
    r = w * 0.20
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=cor)
    espessura = max(1, round(0.05 * w))
    for i in range(8):
        ang = i * math.pi / 4
        x0, y0 = cx + math.cos(ang) * r * 1.5, cy + math.sin(ang) * r * 1.5
        x1, y1 = cx + math.cos(ang) * r * 2.0, cy + math.sin(ang) * r * 2.0
        d.line((x0, y0, x1, y1), fill=cor, width=espessura)
    return _reduzir(img, tamanho)


def _lua(tamanho: int, cor: str) -> Image.Image:
    img, d, w = _tela(tamanho)
    d.ellipse((0.16 * w, 0.16 * w, 0.84 * w, 0.84 * w), fill=cor)
    d.ellipse((0.34 * w, 0.08 * w, 1.02 * w, 0.76 * w), fill=(0, 0, 0, 0))
    return _reduzir(img, tamanho)


_DESENHOS = {
    "play": _play, "pause": _pause, "stop": _stop, "inserir": _inserir,
    "remover": _remover, "fixar": _fixar, "salvar": _salvar,
    "estrela": _estrela, "sol": _sol, "lua": _lua,
}


@lru_cache(maxsize=None)
def icone(nome: str, tamanho: int = TAMANHO_PADRAO, cor: str = "#000000") -> ctk.CTkImage:
    img = _DESENHOS[nome](tamanho, cor)
    return ctk.CTkImage(light_image=img, dark_image=img, size=(tamanho, tamanho))


def _demo():
    for nome in _DESENHOS:
        img = icone(nome, 20, "#201747")
        assert isinstance(img, ctk.CTkImage)
        assert img.cget("size") == (20, 20)
    assert icone("play", 20, "#201747") is icone("play", 20, "#201747")  # cache
    print("icones.py OK")


if __name__ == "__main__":
    _demo()

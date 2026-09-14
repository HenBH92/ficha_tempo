"""Selo com a quantidade de cronômetros rodando sobre o botão do app na barra de tarefas,
estilo contador de não lidas do Teams (ITaskbarList3::SetOverlayIcon via ctypes puro, sem
pywin32/comtypes)."""
import ctypes
import io
import uuid
from ctypes import wintypes

from PIL import Image, ImageDraw, ImageFont

from cores import COR_PERIGO

_CLSID_TASKBARLIST = "56FDF344-FD6D-11d0-958A-006097C9A090"
_IID_ITASKBARLIST3 = "EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF"
# Índices na vtable de ITaskbarList3 (IUnknown 0-2, ITaskbarList 3-7, ITaskbarList2 8, ...).
_HR_INIT = 3
_SET_OVERLAY_ICON = 18
_SM_CXSMICON = 49
_ESCALA = 10  # desenha a 10x e reduz: número nítido no ícone de 16px

# Instância própria da DLL: os argtypes/restype abaixo não vazam pro ctypes.windll global.
_user32 = ctypes.WinDLL("user32")
_user32.CreateIconFromResourceEx.restype = wintypes.HICON  # sem isso o handle trunca em 64 bits
_user32.CreateIconFromResourceEx.argtypes = [ctypes.c_char_p, wintypes.DWORD, wintypes.BOOL,
                                             wintypes.DWORD, ctypes.c_int, ctypes.c_int, wintypes.UINT]
_user32.DestroyIcon.argtypes = [wintypes.HICON]

_taskbar = None
_ultimo = 0  # 0 = sem selo, que é como a janela nasce


def _guid(texto: str):
    return (ctypes.c_char * 16).from_buffer_copy(uuid.UUID(texto).bytes_le)


def _chamar(obj, indice: int, argtypes: tuple, *args) -> None:
    """Chama o método `indice` da vtable de um objeto COM; HRESULT de erro vira OSError."""
    vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, *argtypes)(vtbl[indice])(obj, *args)


def _desenhar_selo(n: int, lado: int) -> Image.Image:
    texto = str(n) if n < 10 else "9+"
    w = lado * _ESCALA
    img = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((0, 0, w - 1, w - 1), fill=COR_PERIGO)
    fonte = ImageFont.truetype("segoeuib.ttf", round(w * (0.8 if len(texto) == 1 else 0.58)))
    # Centraliza pela tinta do texto (bbox), não pela linha de base da fonte.
    esq, topo, dir_, base = d.textbbox((0, 0), texto, font=fonte)
    d.text(((w - (dir_ - esq)) / 2 - esq, (w - (base - topo)) / 2 - topo), texto, font=fonte, fill="white")
    return img.resize((lado, lado), Image.LANCZOS)


def _hicon(img: Image.Image) -> int:
    buf = io.BytesIO()
    img.save(buf, "PNG")  # CreateIconFromResourceEx aceita PNG direto (Vista+)
    dados = buf.getvalue()
    hicon = _user32.CreateIconFromResourceEx(dados, len(dados), True, 0x00030000, 0, 0, 0)
    if not hicon:
        raise ctypes.WinError()
    return hicon


def definir_contador(janela, n: int) -> None:
    """Mostra `n` no selo do botão da `janela` na barra de tarefas (0 remove o selo).
    Só chama a API quando o número muda; falha vira log, nunca derruba o app."""
    global _taskbar, _ultimo
    if n == _ultimo:
        return
    _ultimo = n  # mesmo se falhar: tenta de novo na próxima mudança, sem log a cada tick
    hicon = None
    try:
        if _taskbar is None:
            ctypes.oledll.ole32.CoInitialize(None)  # STA, o mesmo que o Tk usa nos diálogos
            taskbar = ctypes.c_void_p()
            ctypes.oledll.ole32.CoCreateInstance(_guid(_CLSID_TASKBARLIST), None, 1,  # CLSCTX_INPROC_SERVER
                                                 _guid(_IID_ITASKBARLIST3), ctypes.byref(taskbar))
            _chamar(taskbar, _HR_INIT, ())
            _taskbar = taskbar
        if n:
            hicon = _hicon(_desenhar_selo(n, _user32.GetSystemMetrics(_SM_CXSMICON)))
        descricao = f"{n} cronômetro{'s' if n > 1 else ''} rodando" if n else None
        _chamar(_taskbar, _SET_OVERLAY_ICON, (wintypes.HWND, wintypes.HICON, wintypes.LPCWSTR),
                int(janela.wm_frame(), 16), hicon, descricao)
    except OSError as erro:
        print(f"[barra_tarefas] selo não atualizado: {erro}")
    finally:
        if hicon:
            _user32.DestroyIcon(hicon)  # a barra de tarefas guarda uma cópia própria


def _demo():
    for n in (1, 9, 12):
        img = _desenhar_selo(n, 16)
        assert img.size == (16, 16)
        hicon = _hicon(img)
        assert hicon
        _user32.DestroyIcon(hicon)
    print("barra_tarefas.py OK")


if __name__ == "__main__":
    _demo()

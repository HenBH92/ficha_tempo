"""Bootstrap leve: hooks do instalador precedem imports da interface e dados."""
import sys

_mutex = None


def garantir_instancia_unica():
    """Evita duas instâncias alterarem o mesmo estado durante uma atualização."""
    import ctypes
    import hashlib
    from caminhos import pasta_dados
    global _mutex
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    nome = hashlib.sha256(str(pasta_dados()).lower().encode()).hexdigest()[:24]
    _mutex = kernel.CreateMutexW(None, False, f"Local\\VLFAdvogados.FichaTempo.{nome}")
    if not _mutex:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        ctypes.windll.user32.MessageBoxW(None, "O Ficha de Tempo já está aberto.", "Ficha de Tempo", 0x40)
        raise SystemExit(0)


def iniciar_velopack():
    if getattr(sys, "frozen", False):
        import velopack
        velopack.App().set_auto_apply_on_startup(False).run()


def configurar_logs():
    import logging
    from logging.handlers import RotatingFileHandler
    from caminhos import pasta_dados
    handler = RotatingFileHandler(pasta_dados() / "atualizador.log", maxBytes=1_000_000,
                                  backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    for nome in ("atualizador", "atualizacao_ui", "fila_trabalho"):
        logger = logging.getLogger(nome)
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)


def diagnosticar_se_solicitado():
    if len(sys.argv) != 3 or sys.argv[1] != "--diagnostico":
        return
    import importlib
    import json
    from pathlib import Path
    from caminhos import pasta_recursos, informacoes_build
    resultado = informacoes_build()
    for modulo in ("customtkinter", "PIL.Image", "openpyxl", "playwright.sync_api", "velopack"):
        importlib.import_module(modulo)
    from PIL import Image
    import openpyxl
    recursos = pasta_recursos()
    with Image.open(recursos / "assets" / "vlf_icon.ico") as icone:
        icone.load()
    planilha = openpyxl.load_workbook(recursos / "aquivo_modelo.xlsx", read_only=True)
    resultado["abas"] = planilha.sheetnames
    planilha.close()
    resultado["recursos_ok"] = True
    resultado["empacotado"] = bool(getattr(sys, "frozen", False))
    Path(sys.argv[2]).write_text(json.dumps(resultado, ensure_ascii=False), encoding="utf-8")
    raise SystemExit(0)

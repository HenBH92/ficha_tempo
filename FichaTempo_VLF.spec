# -*- mode: python ; coding: utf-8 -*-
import json
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files

raiz = Path(SPECPATH)
metadados = Path(os.environ.get('FICHA_BUILD_METADATA', ''))
if not os.environ.get('FICHA_BUILD_METADATA') or not (metadados / 'build-info.json').is_file():
    raise SystemExit('Use scripts/build.ps1 para gerar a versao e os metadados do build.')

# Playwright inclui seu driver Node; o Chrome instalado continua sendo externo.
pw_datas, pw_binaries, pw_imports = collect_all('playwright')
velo_datas, velo_binaries, velo_imports = collect_all('velopack')


a = Analysis(
    [str(raiz / 'main.py')],
    pathex=[str(raiz)],
    binaries=pw_binaries + velo_binaries,
    datas=[(str(raiz / 'assets'), 'assets'),
           (str(raiz / 'aquivo_modelo.xlsx'), '.'),
           (str(metadados / 'build-info.json'), '.')]
          + collect_data_files('customtkinter') + pw_datas + velo_datas,
    hiddenimports=pw_imports + velo_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='FichaTempo_VLF',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[str(raiz / 'assets' / 'vlf_icon.ico')],
    version=str(metadados / 'version-resource.txt'),
)

coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False,
               name='FichaTempo_VLF')

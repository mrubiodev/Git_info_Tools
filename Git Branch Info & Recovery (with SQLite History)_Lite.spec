# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

datas = [('S:\\GreenhouseProyect\\Git_info_Tools\\res\\app_icon.ico', 'res')]
datas += collect_data_files('TKinterModernThemes')


a = Analysis(
    ['S:\\GreenhouseProyect\\Git_info_Tools\\main_lite.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=['git', 'openpyxl'],
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
    a.binaries,
    a.datas,
    [],
    name='Git Branch Info & Recovery (with SQLite History)_Lite',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['S:\\GreenhouseProyect\\Git_info_Tools\\res\\app_icon.ico'],
)

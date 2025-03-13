# -*- mode: python ; coding: utf-8 -*-
import argparse
from PyInstaller.utils.hooks import collect_submodules

parser = argparse.ArgumentParser()
parser.add_argument("--installer", type=str, default="Quickstart")
options = parser.parse_args()

hiddenimports = ['flask', 'flask.cli', 'werkzeug', 'pyfiglet', 'pyfiglet.fonts']
hiddenimports += collect_submodules('flask')
hiddenimports += collect_submodules('werkzeug')


a = Analysis(
    ['quickstart.py'],
    pathex=[],
    binaries=[],
    datas=[('VERSION', '.'), ('static/fonts', 'pyfiglet/fonts'), ('static', 'static'), ('templates', 'templates'), ('modules', 'modules'), ('.env.example', '.')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['./modules/develop.py'],
    excludes=['.env'],
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
    name=options.installer,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['static\\favicon.ico'],
)

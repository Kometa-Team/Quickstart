# -*- mode: python ; coding: utf-8 -*-
import argparse
from PyInstaller.utils.hooks import collect_submodules

parser = argparse.ArgumentParser()
parser.add_argument("--installer", type=str, default="Quickstart")
parser.add_argument("--branch", type=str, default="master")
parser.add_argument("--build", type=str, default="windows")
options = parser.parse_args()

runtime_hooks = []
if options.branch == "develop":
    runtime_hooks.append('./modules/hooks/develop.py')
elif options.branch == "pull":
    runtime_hooks.append('./modules/hooks/pull.py')

if options.build == "ubuntu":
    runtime_hooks.append('./modules/hooks/linux.py')
elif options.build == "macos":
    runtime_hooks.append('./modules/hooks/macos.py')
else:
    runtime_hooks.append('./modules/hooks/windows.py')

hiddenimports = ['flask', 'flask.cli', 'werkzeug', 'pyfiglet', 'pyfiglet.fonts']
hiddenimports += collect_submodules('flask')
hiddenimports += collect_submodules('werkzeug')


a = Analysis(
    ['quickstart.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('VERSION', '.'),
        ('static/json', 'static/fonts', 'pyfiglet/fonts'),
        ('static', 'static'),
        ('templates', 'templates'),
        ('modules', 'modules'),
        ('.env.example', '.')
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=runtime_hooks,
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
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['static\\favicon.ico'],
)

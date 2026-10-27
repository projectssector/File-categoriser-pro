# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_all

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'src')

# ---------------------------------------------------------------------------
# Data files
# ---------------------------------------------------------------------------
datas = [
    ('config/config.example.yaml', 'config'),
    (os.path.join(HERE, 'app_icon.ico'), '.'),
]

# ---------------------------------------------------------------------------
# Hidden imports
# ---------------------------------------------------------------------------
hiddenimports = [
    # Core ML / vision stack
    'open_clip',
    'open_clip_torch',
    'torch',
    'torchvision',
    'cv2',
    'numpy',
    'numpy.libs',
    # Image / OCR / spreadsheet
    'imagehash',
    'pytesseract',
    'openpyxl',
    'openpyxl.styles',
    'openpyxl.utils',
    'PIL',
    'PIL.Image',
    'PIL.ImageFilter',
    # Gemini / Google AI
    'google.generativeai',
    'google.api_core',
    # PySide6 Qt modules used by the GUI
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PySide6.QtNetwork',
    'PySide6.QtWebEngine',
    # Application package
    'file_categorizer',
    'file_categorizer.core',
    'file_categorizer.models',
    'file_categorizer.utils',
]

binaries = []

# Collect package data (tokenizer vocab, Qt plugins, model files, etc.)
for _pkg in ('open_clip', 'open_clip_torch', 'transformers',
             'google.generativeai', 'PySide6', 'cv2', 'numpy'):
    try:
        _d, _b, _h = collect_all(_pkg)
        datas += _d
        binaries += _b
        hiddenimports += _h
    except Exception:
        # collect_all raises if the package is not importable in the build env;
        # that is fine -- the hiddenimports list above still covers it.
        pass

a = Analysis(
    ['run_gui.py'],
    pathex=[SRC, HERE],
    binaries=binaries,
    datas=datas,
    hiddenimports=sorted(set(hiddenimports)),
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
    name='FileCategorizer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[os.path.join(HERE, 'app_icon.ico')],
    version=os.path.join(HERE, 'version_info.txt'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='FileCategorizer',
)

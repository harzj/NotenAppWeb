# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec für NotenApp – Windows Distribution (nur lokaler Server)
# Erstellt mit: pyinstaller NotenApp.spec

import os
from pathlib import Path

ROOT = Path(SPECPATH)

block_cipher = None

a = Analysis(
    [str(ROOT / 'tray.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # Templates ins Bundle – Zielpfad 'templates/' damit Flask mit root_path=_MEIPASS
        # über den Default template_folder='templates' findet.
        (str(ROOT / 'app' / 'templates'), 'templates'),
        (str(ROOT / 'version.json'), '.'),
    ],
    hiddenimports=[
        # Flask und Extensions
        'flask',
        'flask_login',
        'flask_wtf',
        'flask_sqlalchemy',
        'flask_session',
        'flask_limiter',
        'flask_limiter.util',
        # Werkzeug
        'werkzeug',
        'werkzeug.routing',
        'werkzeug.middleware.proxy_fix',
        # WTForms
        'wtforms',
        'wtforms.validators',
        'email_validator',
        # SQLAlchemy
        'sqlalchemy',
        'sqlalchemy.dialects.sqlite',
        # Jinja2
        'jinja2',
        'jinja2.ext',
        # xhtml2pdf und Abhängigkeiten
        'xhtml2pdf',
        'xhtml2pdf.tags',
        'xhtml2pdf.util',
        'html5lib',
        'reportlab',
        'reportlab.pdfgen',
        'reportlab.lib.styles',
        'reportlab.lib.pagesizes',
        'reportlab.lib.units',
        'reportlab.platypus',
        # openpyxl
        'openpyxl',
        'openpyxl.workbook',
        'openpyxl.styles',
        'openpyxl.utils',
        # msoffcrypto
        'msoffcrypto',
        # pystray / PIL
        'pystray',
        'PIL',
        'PIL.Image',
        'PIL.ImageDraw',
        # tkinter (Konsolen-Fenster)
        'tkinter',
        'tkinter.scrolledtext',
        # Stdlib
        'cachelib',
        'cachelib.file',
        'limits',
        'limits.storage',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='NotenApp',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,       # kein Konsolenfenster (GUI-App mit Tray)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='app/static/favicon.ico',  # optional: Pfad zu einem .ico setzen
)

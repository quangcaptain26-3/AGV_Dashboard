# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec cho AGV Analyzer (khuyến nghị Python 3.10, PyQt5, onedir).

Chay tu THU MUC GOC du an (venv 3.10):
    .\.venv310\Scripts\pyinstaller.exe agv_app\build\agv_app.spec --noconfirm

Ket qua: dist\AGV_Analyzer\AGV_Analyzer.exe  (bat len chay ngay, khong can Python).
"""

import os

# SPECPATH do PyInstaller cung cap = thu muc chua file .spec (agv_app/build)
ROOT = os.path.dirname(os.path.dirname(SPECPATH))
ENTRY = os.path.join(ROOT, "agv_app", "main.py")
SETTINGS_JSON = os.path.join(ROOT, "agv_app", "point_settings.json")

APP_NAME = "AGV_Analyzer"

# Loai cac goi lon khong dung -> giam dung lung .exe
EXCLUDES = [
    "tkinter", "numpy", "pandas", "scipy", "matplotlib", "PIL", "pytest",
    "IPython", "notebook", "sqlite3",
    "PyQt5.QtWebEngineWidgets", "PyQt5.QtWebEngineCore", "PyQt5.QtWebEngine",
    "PyQt5.QtQml", "PyQt5.QtQuick", "PyQt5.QtQuickWidgets", "PyQt5.QtQuick3D",
    "PyQt5.QtMultimedia", "PyQt5.QtMultimediaWidgets",
    "PyQt5.QtBluetooth", "PyQt5.QtNfc", "PyQt5.QtPositioning",
    "PyQt5.QtLocation", "PyQt5.QtSensors", "PyQt5.QtSerialPort",
    "PyQt5.QtWebSockets", "PyQt5.QtWebChannel", "PyQt5.QtTest",
    "PyQt5.QtDBus", "PyQt5.QtHelp", "PyQt5.QtDesigner",
    "PyQt5.Qt3DCore", "PyQt5.Qt3DRender", "PyQt5.Qt3DInput",
    "PyQt5.QtChart", "PyQt5.QtDataVisualization", "PyQt5.QtNetwork",
]

# Cac DLL/plugin Qt lon chac chan khong dung -> loc bo khoi ban dong goi
_DROP_BIN_SUBSTR = [
    "WebEngine", "Qt5Quick", "Qt5Qml", "Qt5Designer", "Qt5Pdf",
    "Qt53D", "Qt5Multimedia", "Qt5Bluetooth", "Qt5Location",
    "Qt5Sensors", "Qt5SerialPort", "Qt5WebSockets", "Qt5WebChannel",
    "Qt5Charts", "Qt5DataVisualization", "Qt5Quick3D", "Qt5Nfc",
    "Qt5Positioning", "Qt5RemoteObjects", "Qt5TextToSpeech",
]


a = Analysis(
    [ENTRY],
    pathex=[ROOT],
    binaries=[],
    datas=[(SETTINGS_JSON, ".")],
    hiddenimports=["PyQt5.sip"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)


def _keep(name: str) -> bool:
    for sub in _DROP_BIN_SUBSTR:
        if sub.lower() in name.lower():
            return False
    return True


a.binaries = TOC([b for b in a.binaries if _keep(b[0])])
a.datas = TOC([d for d in a.datas if _keep(d[0])])

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # app cua so, khong hien console
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)

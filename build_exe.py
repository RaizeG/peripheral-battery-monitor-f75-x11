"""Build a standalone Windows executable (PeripheralBatteryHub.exe) with PyInstaller."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

EXCLUDES = [
    "PySide6.QtWebEngine",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtSql",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DExtras",
    "PySide6.QtCharts",
    "PySide6.QtBluetooth",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtPositioning",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtTest",
    "PySide6.QtXml",
    "PySide6.QtNetwork",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtPrintSupport",
    "PySide6.QtDBus",
    "PySide6.QtNfc",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtStateMachine",
    "PySide6.QtTextToSpeech",
    "PySide6.QtVirtualKeyboard",
    "PySide6.QtWebChannel",
    "PySide6.QtWebSockets",
    "tkinter",
    "unittest",
]


def main() -> int:
    from PySide6.QtGui import QGuiApplication
    from battery_hub.tray_icon import write_app_ico

    # QPixmap requires a QGuiApplication instance
    app = QGuiApplication([])
    ico_path = write_app_ico(ROOT / "assets" / "app_icon.ico")
    app.quit()

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        "PeripheralBatteryHub",
        "--icon",
        str(ico_path),
        "--paths",
        str(SRC),
        "--hidden-import",
        "hid",
    ]
    for mod in EXCLUDES:
        cmd.extend(["--exclude-module", mod])
    cmd.append(str(ROOT / "peripheral_battery.py"))

    print("Running:", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())

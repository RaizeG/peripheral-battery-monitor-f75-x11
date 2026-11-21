#!/usr/bin/env python3
"""Entrypoint for Peripheral Battery Hub (AULA F75 Keyboard + Attack Shark X11 Mouse)."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from battery_hub.keyboard_aula import query_keyboard_battery
from battery_hub.models import BatteryReading, DeviceStatus
from battery_hub.mouse_asx11 import query_mouse_battery_once


def _print_reading(name: str, r: BatteryReading, debug: bool) -> None:
    if r.status == DeviceStatus.CONNECTED:
        print(f"{name}: {r.percent}% (Akkubetrieb)")
    elif r.status == DeviceStatus.CHARGING:
        pct = f"{r.percent}% " if r.percent is not None else ""
        print(f"{name}: {pct}(Lädt)")
    elif r.status == DeviceStatus.SLEEPING:
        print(f"{name}: Schlafmodus / keine Antwort (drücke kurz eine Taste)")
    elif r.status == DeviceStatus.WAITING:
        print(f"{name}: Warte auf Signal (bewege kurz die Maus)")
    elif r.status == DeviceStatus.DISCONNECTED:
        print(f"{name}: Nicht verbunden ({r.error_message})")
    else:
        print(f"{name}: Fehler ({r.error_message})")
    if debug and r.raw_hex:
        print(f"  RAW: {r.raw_hex}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Peripheral Battery Hub — AULA F75 & Attack Shark X11 (Tray & Dashboard)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Akkustand beider Geräte einmalig abfragen und im Terminal ausgeben.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Rohdaten (Hex) bei --once mit ausgeben.",
    )
    parser.add_argument(
        "--minimized",
        action="store_true",
        help="Minimiert im System-Tray starten (z. B. für Autostart).",
    )
    args = parser.parse_args()

    if args.once:
        kb = query_keyboard_battery()
        mouse = query_mouse_battery_once(timeout_sec=2.5)
        _print_reading("AULA F75 (Tastatur)", kb, args.debug)
        _print_reading("Attack Shark X11 (Maus)", mouse, args.debug)
        ok = kb.status in (DeviceStatus.CONNECTED, DeviceStatus.CHARGING) or mouse.status in (
            DeviceStatus.CONNECTED,
            DeviceStatus.CHARGING,
        )
        return 0 if ok else 1

    from battery_hub.ui import run_gui

    return run_gui(Path(__file__).resolve(), start_minimized=args.minimized)


if __name__ == "__main__":
    raise SystemExit(main())

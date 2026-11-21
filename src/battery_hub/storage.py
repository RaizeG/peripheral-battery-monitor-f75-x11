"""Unified settings, per-device battery history CSV, runtime estimation, and Windows autostart."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Optional

from .models import DeviceId, HistoryPoint

APP_NAME = "Peripheral Battery Hub"
APP_ID = "PeripheralBatteryHub.Monitor"
APP_MUTEX = r"Local\PeripheralBatteryHub.Monitor"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "PeripheralBatteryHub"

DEFAULT_SETTINGS: dict[str, Any] = {
    "language": "en",
    "poll_interval_sec": 30,
    "alerts_enabled": True,
    "keyboard_last_percent": None,
    "keyboard_last_seen": None,
    "mouse_last_percent": None,
    "mouse_last_seen": None,
}


def get_data_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    target = base / "PeripheralBatteryHub"
    target.mkdir(parents=True, exist_ok=True)
    return target


DATA_DIR = get_data_dir()
SETTINGS_PATH = DATA_DIR / "settings.json"
LOG_PATH = DATA_DIR / "error.log"


def history_path_for(device_id: DeviceId, base_dir: Optional[Path] = None) -> Path:
    root = base_dir if base_dir is not None else DATA_DIR
    return root / f"history_{device_id.value}.csv"


def log_error(message: str) -> None:
    try:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(f"[{stamp}] {message}\n")
    except Exception:
        pass


def load_settings(path: Optional[Path] = None) -> dict[str, Any]:
    target = path if path is not None else SETTINGS_PATH
    data = dict(DEFAULT_SETTINGS)
    if target.exists():
        try:
            loaded = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data.update(loaded)
        except Exception as exc:
            log_error(f"Failed to load settings: {exc}")
    return data


def save_settings(settings: dict[str, Any], path: Optional[Path] = None) -> None:
    target = path if path is not None else SETTINGS_PATH
    try:
        tmp = target.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(settings, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(target)
    except Exception as exc:
        log_error(f"Failed to save settings: {exc}")


def append_history(
    device_id: DeviceId,
    percent: int,
    charging: bool,
    timestamp: Optional[float] = None,
    base_dir: Optional[Path] = None,
) -> None:
    ts = time.time() if timestamp is None else timestamp
    path = history_path_for(device_id, base_dir)
    write_header = not path.exists() or path.stat().st_size == 0
    try:
        with path.open("a", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            if write_header:
                writer.writerow(["timestamp", "percent", "charging"])
            writer.writerow([f"{ts:.1f}", int(percent), 1 if charging else 0])
    except Exception as exc:
        log_error(f"Failed to append history ({device_id.value}): {exc}")


def load_history(
    device_id: DeviceId,
    max_age_sec: Optional[float] = None,
    base_dir: Optional[Path] = None,
) -> list[HistoryPoint]:
    path = history_path_for(device_id, base_dir)
    if not path.exists():
        return []
    cutoff = (time.time() - max_age_sec) if max_age_sec is not None else None
    points: list[HistoryPoint] = []
    try:
        with path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                try:
                    ts = float(row["timestamp"])
                    pct = int(row["percent"])
                    chg = bool(int(row.get("charging", "0")))
                except (KeyError, TypeError, ValueError):
                    continue
                if cutoff is not None and ts < cutoff:
                    continue
                if 0 <= pct <= 100:
                    points.append(HistoryPoint(timestamp=ts, percent=pct, charging=chg))
    except Exception as exc:
        log_error(f"Failed to load history ({device_id.value}): {exc}")
    points.sort(key=lambda p: p.timestamp)
    return points


def estimate_drain_and_remaining(
    points: list[HistoryPoint],
    current_percent: Optional[int],
    now: Optional[float] = None,
) -> tuple[Optional[float], Optional[float]]:
    """Return (drain_pct_per_hour, remaining_hours) from recent discharging samples."""
    if current_percent is None or len(points) < 2:
        return None, None

    ref_now = time.time() if now is None else now
    segment: list[HistoryPoint] = []
    for pt in reversed(points):
        if pt.charging:
            break
        if ref_now - pt.timestamp > 48 * 3600:
            break
        segment.append(pt)
    segment.reverse()

    if len(segment) < 2:
        return None, None

    clean: list[HistoryPoint] = [segment[-1]]
    for pt in reversed(segment[:-1]):
        if pt.percent + 2 < clean[-1].percent:
            break
        clean.append(pt)
    clean.reverse()

    if len(clean) < 2:
        return None, None

    elapsed_hours = (clean[-1].timestamp - clean[0].timestamp) / 3600.0
    drop = clean[0].percent - clean[-1].percent
    if elapsed_hours < 0.25 or drop < 2:
        return None, None

    rate = drop / elapsed_hours
    if rate <= 0.05:
        return None, None

    remaining_hours = current_percent / rate
    return rate, remaining_hours


def _startup_shortcut_path() -> Path:
    appdata = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    return appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / f"{APP_NAME}.lnk"


def _remove_legacy_registry_autostart() -> None:
    if os.name != "nt":
        return
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, RUN_NAME)
            except FileNotFoundError:
                pass
    except Exception:
        pass


def is_autostart_enabled() -> bool:
    if os.name != "nt":
        return False
    return _startup_shortcut_path().exists()


def set_autostart(enabled: bool, entrypoint: Path) -> bool:
    if os.name != "nt":
        return False
    try:
        import subprocess

        _remove_legacy_registry_autostart()
        lnk = _startup_shortcut_path()
        if not enabled:
            try:
                lnk.unlink()
            except FileNotFoundError:
                pass
            return True

        py_exe = Path(sys.executable)
        pythonw = py_exe.with_name("pythonw.exe")
        launcher = pythonw if pythonw.exists() else py_exe
        ico_path = DATA_DIR / "app_icon.ico"

        def _ps_quote(value: str) -> str:
            return "'" + value.replace("'", "''") + "'"

        args_str = f'"{entrypoint}" --minimized'
        lines = [
            "$ws = New-Object -ComObject WScript.Shell",
            f"$s = $ws.CreateShortcut({_ps_quote(str(lnk))})",
            f"$s.TargetPath = {_ps_quote(str(launcher))}",
            f"$s.Arguments = {_ps_quote(args_str)}",
            f"$s.WorkingDirectory = {_ps_quote(str(entrypoint.parent))}",
            f"$s.Description = {_ps_quote(APP_NAME)}",
        ]
        if ico_path.exists():
            lines.append(f"$s.IconLocation = {_ps_quote(f'{ico_path},0')}")
        lines.append("$s.Save()")

        result = subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", "; ".join(lines)],
            check=False,
            creationflags=0x08000000,
        )
        return result.returncode == 0 and lnk.exists()
    except Exception as exc:
        log_error(f"Autostart update failed: {exc}")
        return False

"""Native HID battery reader & passive monitor for the Attack Shark X11 mouse.

Reads the mouse's native HID reports without replacing the driver:
  - VID 0x1D57, PID 0xFA60: 2.4 GHz wireless adapter
    Battery report signature: (0x03, 0x55, 0x40, 0x01), byte 4 = percent (0..100)
  - VID 0x1D57, PID 0xFA55: Wired / USB charging mode
"""

from __future__ import annotations

import sys
import threading
import time
from typing import Any, Callable, Iterable, Optional

from .models import BatteryReading, DeviceId, DeviceStatus

VID_ASX11 = 0x1D57
PID_ADAPTER = 0xFA60
PID_WIRED = 0xFA55
BATTERY_SIG = (0x03, 0x55, 0x40, 0x01)
HEARTBEAT_SECS = 180


def get_hid_module() -> Any:
    if sys.platform.startswith("linux"):
        try:
            import hidraw

            return hidraw
        except ImportError:
            return None
    try:
        import hid

        return hid
    except ImportError:
        return None


def parse_mouse_battery(data: Iterable[int] | None) -> Optional[int]:
    """Parse a raw Attack Shark X11 HID report and return percentage (0..100) or None."""
    if not data:
        return None
    values = list(data)
    if len(values) < 5 or tuple(values[:4]) != BATTERY_SIG:
        return None
    level = values[4]
    return level if 0 <= level <= 100 else None


def enumerate_mouse_mode(hid_module: Any = None) -> tuple[Optional[str], list[Any]]:
    hid_mod = hid_module or get_hid_module()
    if hid_mod is None:
        raise RuntimeError("hidapi ist nicht installiert")
    # Check wired USB mode first: the 2.4 GHz dongle usually stays plugged in
    # at the same time while the mouse is charging via USB cable.
    if hid_mod.enumerate(VID_ASX11, PID_WIRED):
        return "charging", []
    paths = list(dict.fromkeys(
        dev["path"] for dev in hid_mod.enumerate(VID_ASX11, PID_ADAPTER) if dev.get("path")
    ))
    if paths:
        return "adapter", paths
    return None, []


def _open_devices(paths: Iterable[Any], hid_mod: Any) -> list[Any]:
    devices = []
    for path in paths:
        try:
            dev = hid_mod.device()
            dev.open_path(path)
            dev.set_nonblocking(1)
            devices.append(dev)
        except (OSError, ValueError):
            continue
    return devices


def _close_devices(devices: Iterable[Any]) -> None:
    for dev in devices:
        try:
            dev.close()
        except Exception:
            pass


def query_mouse_battery_once(timeout_sec: float = 3.0, hid_module: Any = None) -> BatteryReading:
    """One-shot CLI query for the Attack Shark X11 mouse."""
    ts = time.time()
    try:
        hid_mod = hid_module or get_hid_module()
        if hid_mod is None:
            return BatteryReading(
                device_id=DeviceId.MOUSE,
                status=DeviceStatus.ERROR,
                connection_label="HID-Fehler",
                error_message="hidapi ist nicht installiert.",
                timestamp=ts,
            )
        mode, paths = enumerate_mouse_mode(hid_mod)
    except Exception as exc:
        return BatteryReading(
            device_id=DeviceId.MOUSE,
            status=DeviceStatus.ERROR,
            connection_label="HID-Fehler",
            error_message=f"HID-Suche fehlgeschlagen: {exc}",
            timestamp=ts,
        )

    if mode is None:
        return BatteryReading(
            device_id=DeviceId.MOUSE,
            status=DeviceStatus.DISCONNECTED,
            connection_label="Nicht verbunden",
            error_message="Attack Shark X11 nicht gefunden (VID 1D57 : PID FA60/FA55).",
            timestamp=ts,
        )

    if mode == "charging":
        return BatteryReading(
            device_id=DeviceId.MOUSE,
            status=DeviceStatus.CHARGING,
            percent=None,
            charging=True,
            connection_label="USB-Kabel (lädt)",
            timestamp=ts,
        )

    devices = _open_devices(paths, hid_mod)
    if not devices:
        return BatteryReading(
            device_id=DeviceId.MOUSE,
            status=DeviceStatus.ERROR,
            connection_label="HID-Zugriff fehlgeschlagen",
            error_message="Konnte kein HID-Interface der Maus öffnen.",
            timestamp=ts,
        )

    try:
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            received = False
            for dev in devices:
                try:
                    data = dev.read(64)
                except OSError:
                    continue
                if data:
                    received = True
                    lvl = parse_mouse_battery(data)
                    if lvl is not None:
                        return BatteryReading(
                            device_id=DeviceId.MOUSE,
                            status=DeviceStatus.CONNECTED,
                            percent=lvl,
                            charging=False,
                            connection_label="2,4 GHz Dongle (aktiv)",
                            raw_hex=" ".join(f"{b:02X}" for b in data[:8]),
                            timestamp=time.time(),
                        )
            if not received:
                time.sleep(0.05)
    finally:
        _close_devices(devices)

    return BatteryReading(
        device_id=DeviceId.MOUSE,
        status=DeviceStatus.WAITING,
        connection_label="2,4 GHz Dongle (warte auf Signal)",
        error_message="Kein Akku-Report empfangen (bewege die Maus kurz).",
        timestamp=time.time(),
    )


def _reading_for(mode: str, level: Optional[int]) -> BatteryReading:
    ts = time.time()
    if mode == "adapter" and level is not None:
        return BatteryReading(
            device_id=DeviceId.MOUSE,
            status=DeviceStatus.CONNECTED,
            percent=level,
            charging=False,
            connection_label="2,4 GHz Dongle (aktiv)",
            timestamp=ts,
        )
    if mode == "waiting":
        return BatteryReading(
            device_id=DeviceId.MOUSE,
            status=DeviceStatus.WAITING,
            percent=level,
            charging=False,
            connection_label="2,4 GHz Dongle (warte auf Signal)",
            timestamp=ts,
        )
    if mode == "charging":
        return BatteryReading(
            device_id=DeviceId.MOUSE,
            status=DeviceStatus.CHARGING,
            percent=None,
            charging=True,
            connection_label="USB-Kabel (lädt)",
            timestamp=ts,
        )
    if mode == "disconnected":
        return BatteryReading(
            device_id=DeviceId.MOUSE,
            status=DeviceStatus.DISCONNECTED,
            percent=None,
            charging=None,
            connection_label="Nicht verbunden",
            timestamp=ts,
        )
    return BatteryReading(
        device_id=DeviceId.MOUSE,
        status=DeviceStatus.ERROR,
        percent=None,
        charging=None,
        connection_label="HID-Fehler",
        error_message="HID-Interface konnte nicht geöffnet werden.",
        timestamp=ts,
    )


def mouse_monitor_loop(
    on_reading: Callable[[BatteryReading, bool], None],
    stop_event: threading.Event,
    *,
    reenum_secs: float = 4.0,
    heartbeat: int = HEARTBEAT_SECS,
    heartbeat_getter: Optional[Callable[[], float]] = None,
    refresh_event: Optional[threading.Event] = None,
    hid_module: Any = None,
) -> None:
    """Continuously monitor the Attack Shark X11 mouse until stop_event is set."""
    hid_mod = hid_module or get_hid_module()
    if hid_mod is None:
        on_reading(_reading_for("error", None), True)
        return

    devices: list[Any] = []
    current_mode = "__init__"
    last_level: Optional[int] = None
    last_enum = 0.0
    last_emit = time.monotonic()
    device_open_failed = False

    def fire(mode: str, level: Optional[int], is_change: bool) -> None:
        nonlocal last_emit
        last_emit = time.monotonic()
        on_reading(_reading_for(mode, level), is_change)

    while not stop_event.is_set():
        now = time.monotonic()
        forced_refresh = bool(refresh_event is not None and refresh_event.is_set())
        if forced_refresh and refresh_event is not None:
            refresh_event.clear()

        if forced_refresh or not devices or (now - last_enum) > reenum_secs:
            try:
                mode, paths = enumerate_mouse_mode(hid_mod)
            except Exception:
                mode, paths = None, []
            last_enum = now
            normalized = mode or "disconnected"

            if normalized != current_mode:
                _close_devices(devices)
                devices = []
                current_mode = normalized

                if normalized != "adapter":
                    last_level = None
                    device_open_failed = False
                    fire(normalized, None, True)
                else:
                    devices = _open_devices(paths, hid_mod)
                    device_open_failed = not devices
                    if device_open_failed:
                        fire("error", None, True)
                    elif last_level is None:
                        fire("waiting", None, True)
                    else:
                        fire("adapter", last_level, False)
            elif normalized == "adapter" and not devices:
                devices = _open_devices(paths, hid_mod)
                if devices:
                    device_open_failed = False
                    fire("waiting" if last_level is None else "adapter", last_level, True)
                elif not device_open_failed:
                    device_open_failed = True
                    fire("error", None, True)
            elif forced_refresh:
                if current_mode == "adapter":
                    fire("adapter" if last_level is not None else "waiting", last_level, False)
                else:
                    fire(current_mode, None, False)

        if current_mode == "adapter" and devices:
            received = False
            healthy: list[Any] = []
            for dev in devices:
                try:
                    data = dev.read(64)
                except OSError:
                    try:
                        dev.close()
                    except Exception:
                        pass
                    continue
                healthy.append(dev)
                if data:
                    received = True
                    lvl = parse_mouse_battery(data)
                    if lvl is not None and lvl != last_level:
                        last_level = lvl
                        fire("adapter", lvl, True)
            devices = healthy
            if not received:
                time.sleep(0.1)
        else:
            time.sleep(0.3)

        hb = heartbeat_getter() if heartbeat_getter is not None else heartbeat
        if hb and (time.monotonic() - last_emit) >= hb:
            if current_mode == "adapter":
                fire("adapter" if last_level is not None else "waiting", last_level, False)
            else:
                fire(current_mode, None, False)

    _close_devices(devices)

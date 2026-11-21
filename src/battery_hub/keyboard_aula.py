"""Native HID 2.4 GHz battery reader for the AULA F75 keyboard.

Communicates with the Compx 2.4 GHz wireless receiver (VID 0x3554, PID 0xFA09)
over vendor HID collection Usage Page 0xFF02, Usage 0x0002 (20-byte reports).

Query packet (20 bytes):
  Byte 0:  0x13 (Report ID)
  Byte 1:  0x4A (Battery / power status query command)
  Byte 2..18: 0x00
  Byte 19: sum(bytes[0:19]) & 0xFF == 0x5D

Response packet (20 bytes):
  Byte 0:  0x13 (Report ID)
  Byte 1:  0x4A (Command echo)
  Byte 2:  Online flag (0x01 = keyboard active/reachable, 0x00 = sleeping/offline)
  Byte 4:  Payload length (typically 0x02)
  Byte 5:  Battery percentage (0..100)
  Byte 6:  Power state (0x01 = discharging/on battery, 0x02 = charging)
  Byte 19: Checksum = sum(bytes[0:19]) & 0xFF
"""

from __future__ import annotations

import time
from typing import Any, Optional

from .models import BatteryReading, DeviceId, DeviceStatus

VID_AULA = 0x3554
PID_AULA_24G = 0xFA09
USAGE_PAGE_VENDOR = 0xFF02
USAGE_VENDOR = 0x0002

REPORT_ID = 0x13
CMD_BATTERY = 0x4A
PACKET_LEN = 20

POWER_DISCHARGING = 0x01
POWER_CHARGING_STATES = (0x02, 0x10)


def _get_hid() -> Any:
    import hid

    return hid


def build_battery_query() -> bytes:
    """Build the 20-byte AULA F75 2.4 GHz battery query packet."""
    buf = bytearray(PACKET_LEN)
    buf[0] = REPORT_ID
    buf[1] = CMD_BATTERY
    buf[PACKET_LEN - 1] = sum(buf[: PACKET_LEN - 1]) & 0xFF
    return bytes(buf)


def parse_battery_response(
    data: bytes | list[int],
    now: Optional[float] = None,
) -> Optional[BatteryReading]:
    """Parse a 20-byte HID response frame into a BatteryReading."""
    ts = time.time() if now is None else now
    if len(data) < PACKET_LEN:
        return None

    frame = bytes(data[:PACKET_LEN])
    if frame[0] != REPORT_ID or frame[1] != CMD_BATTERY:
        return None

    expected_checksum = sum(frame[: PACKET_LEN - 1]) & 0xFF
    if frame[PACKET_LEN - 1] != expected_checksum:
        return None

    online_raw = frame[2]
    pct_raw = frame[5]
    power_raw = frame[6]
    raw_hex = " ".join(f"{b:02X}" for b in frame)

    if online_raw == 0 or pct_raw == 0 or pct_raw > 100:
        return BatteryReading(
            device_id=DeviceId.KEYBOARD,
            status=DeviceStatus.SLEEPING,
            percent=None,
            charging=None,
            connection_label="2,4 GHz Dongle (Standby)",
            raw_hex=raw_hex,
            timestamp=ts,
        )

    if power_raw in POWER_CHARGING_STATES:
        charging: Optional[bool] = True
        status = DeviceStatus.CHARGING
        conn = "2,4 GHz + USB (lädt)"
    elif power_raw == POWER_DISCHARGING:
        charging = False
        status = DeviceStatus.CONNECTED
        conn = "2,4 GHz Dongle (aktiv)"
    else:
        charging = None
        status = DeviceStatus.CONNECTED
        conn = "2,4 GHz Dongle (aktiv)"

    return BatteryReading(
        device_id=DeviceId.KEYBOARD,
        status=status,
        percent=int(pct_raw),
        charging=charging,
        connection_label=conn,
        raw_hex=raw_hex,
        timestamp=ts,
    )


def find_receiver_paths(
    vid: int = VID_AULA,
    pid: int = PID_AULA_24G,
    hid_module: Any = None,
) -> list[bytes]:
    """Find matching vendor HID collection paths for the AULA F75 2.4 GHz dongle."""
    hid_mod = hid_module or _get_hid()
    paths: list[bytes] = []
    for info in hid_mod.enumerate(vid, pid):
        if (
            info.get("usage_page") == USAGE_PAGE_VENDOR
            and info.get("usage") == USAGE_VENDOR
        ):
            path = info.get("path")
            if path:
                paths.append(path)
    return paths


def query_keyboard_battery(
    timeout_ms: int = 1200,
    retries: int = 2,
    hid_module: Any = None,
) -> BatteryReading:
    """Query the live battery status from the AULA F75 2.4 GHz receiver."""
    ts = time.time()
    try:
        hid_mod = hid_module or _get_hid()
        paths = find_receiver_paths(hid_module=hid_mod)
    except Exception as exc:
        return BatteryReading(
            device_id=DeviceId.KEYBOARD,
            status=DeviceStatus.ERROR,
            connection_label="HID-Fehler",
            error_message=f"HID-Suche fehlgeschlagen: {exc}",
            timestamp=ts,
        )

    if not paths:
        return BatteryReading(
            device_id=DeviceId.KEYBOARD,
            status=DeviceStatus.DISCONNECTED,
            connection_label="Nicht verbunden",
            error_message="2,4-GHz-Empfänger nicht gefunden (VID 3554 : PID FA09).",
            timestamp=ts,
        )

    query = build_battery_query()
    last_error = ""

    for path in paths:
        dev = hid_mod.device()
        try:
            dev.open_path(path)
            dev.set_nonblocking(0)

            for _ in range(4):
                stale = dev.read(64, timeout_ms=20)
                if not stale:
                    break

            for _attempt in range(max(1, retries)):
                written = dev.write(query)
                if written < 0:
                    last_error = dev.error() or "HID-Schreibfehler"
                    continue

                deadline = time.monotonic() + (timeout_ms / 1000.0)
                while True:
                    remaining_ms = int((deadline - time.monotonic()) * 1000)
                    if remaining_ms <= 0:
                        break
                    resp = dev.read(64, timeout_ms=min(remaining_ms, 500))
                    if not resp:
                        continue
                    parsed = parse_battery_response(resp, now=time.time())
                    if parsed is not None:
                        return parsed

            return BatteryReading(
                device_id=DeviceId.KEYBOARD,
                status=DeviceStatus.SLEEPING,
                connection_label="2,4 GHz Dongle (Standby)",
                error_message="Keine Antwort (Tastatur evtl. im Schlafmodus).",
                timestamp=time.time(),
            )
        except Exception as exc:
            last_error = str(exc)
        finally:
            try:
                dev.close()
            except Exception:
                pass

    return BatteryReading(
        device_id=DeviceId.KEYBOARD,
        status=DeviceStatus.ERROR,
        connection_label="Verbindungsfehler",
        error_message=last_error or "Unbekannter HID-Fehler",
        timestamp=time.time(),
    )

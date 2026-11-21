"""Unit tests for Peripheral Battery Hub."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from battery_hub.keyboard_aula import (
    CMD_BATTERY,
    PACKET_LEN,
    POWER_CHARGING_STATES,
    POWER_DISCHARGING,
    REPORT_ID,
    build_battery_query,
    parse_battery_response,
)
from battery_hub.i18n import tr
from battery_hub.models import DeviceId, DeviceStatus, HistoryPoint
from battery_hub.mouse_asx11 import (
    BATTERY_SIG,
    PID_ADAPTER,
    PID_WIRED,
    VID_ASX11,
    enumerate_mouse_mode,
    parse_mouse_battery,
)
from battery_hub.storage import DEFAULT_SETTINGS, append_history, estimate_drain_and_remaining, load_history
from battery_hub.tray_icon import (
    COLOR_CHARGING,
    COLOR_GREEN,
    COLOR_RED,
    COLOR_YELLOW,
    accent_color_for,
)
from battery_hub.ui import ALERT_THRESHOLDS


class KeyboardProtocolTests(unittest.TestCase):
    def test_build_query(self) -> None:
        q = build_battery_query()
        self.assertEqual(len(q), PACKET_LEN)
        self.assertEqual(q[0], REPORT_ID)
        self.assertEqual(q[1], CMD_BATTERY)
        self.assertEqual(q[-1], (REPORT_ID + CMD_BATTERY) & 0xFF)

    def _frame(self, online: int, pct: int, power: int) -> bytes:
        buf = bytearray(PACKET_LEN)
        buf[0] = REPORT_ID
        buf[1] = CMD_BATTERY
        buf[2] = online
        buf[4] = 0x02
        buf[5] = pct
        buf[6] = power
        buf[-1] = sum(buf[:-1]) & 0xFF
        return bytes(buf)

    def test_parse_discharging(self) -> None:
        r = parse_battery_response(self._frame(1, 84, POWER_DISCHARGING), now=1000.0)
        self.assertIsNotNone(r)
        assert r is not None
        self.assertEqual(r.device_id, DeviceId.KEYBOARD)
        self.assertEqual(r.status, DeviceStatus.CONNECTED)
        self.assertEqual(r.percent, 84)
        self.assertFalse(r.charging)

    def test_parse_charging(self) -> None:
        for power_byte in POWER_CHARGING_STATES:
            r = parse_battery_response(self._frame(1, 65, power_byte), now=1000.0)
            self.assertIsNotNone(r)
            assert r is not None
            self.assertEqual(r.status, DeviceStatus.CHARGING)
            self.assertEqual(r.percent, 65)
            self.assertTrue(r.charging)

    def test_parse_sleeping(self) -> None:
        r = parse_battery_response(self._frame(0, 0, POWER_DISCHARGING), now=1000.0)
        self.assertIsNotNone(r)
        assert r is not None
        self.assertEqual(r.status, DeviceStatus.SLEEPING)
        self.assertIsNone(r.percent)

    def test_parse_bad_checksum(self) -> None:
        bad = bytearray(self._frame(1, 80, POWER_DISCHARGING))
        bad[-1] ^= 0xFF
        self.assertIsNone(parse_battery_response(bytes(bad)))


class MouseProtocolTests(unittest.TestCase):
    def test_parse_valid_mouse_report(self) -> None:
        report = list(BATTERY_SIG) + [73, 0, 0, 0]
        self.assertEqual(parse_mouse_battery(report), 73)

    def test_parse_invalid_signature(self) -> None:
        self.assertIsNone(parse_mouse_battery([0x01, 0x02, 0x03, 0x04, 50]))

    def test_parse_out_of_range(self) -> None:
        report = list(BATTERY_SIG) + [150]
        self.assertIsNone(parse_mouse_battery(report))

    def test_wired_takes_priority_over_adapter(self) -> None:
        class FakeHid:
            def enumerate(self, vid, pid):
                if vid == VID_ASX11 and pid == PID_WIRED:
                    return [{"path": b"wired"}]
                if vid == VID_ASX11 and pid == PID_ADAPTER:
                    return [{"path": b"adapter"}]
                return []

        mode, paths = enumerate_mouse_mode(FakeHid())
        self.assertEqual(mode, "charging")
        self.assertEqual(paths, [])


class StorageTests(unittest.TestCase):
    def test_per_device_history_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            append_history(DeviceId.KEYBOARD, 90, False, timestamp=1000.0, base_dir=base)
            append_history(DeviceId.MOUSE, 55, False, timestamp=1000.0, base_dir=base)

            kb_pts = load_history(DeviceId.KEYBOARD, base_dir=base)
            mouse_pts = load_history(DeviceId.MOUSE, base_dir=base)
            self.assertEqual(len(kb_pts), 1)
            self.assertEqual(kb_pts[0].percent, 90)
            self.assertEqual(len(mouse_pts), 1)
            self.assertEqual(mouse_pts[0].percent, 55)

    def test_drain_estimation(self) -> None:
        pts = [
            HistoryPoint(timestamp=1000.0, percent=80, charging=False),
            HistoryPoint(timestamp=4600.0, percent=70, charging=False),
        ]
        rate, rem = estimate_drain_and_remaining(pts, current_percent=70, now=4600.0)
        self.assertIsNotNone(rate)
        self.assertIsNotNone(rem)
        assert rate is not None and rem is not None
        self.assertAlmostEqual(rate, 10.0, places=2)
        self.assertAlmostEqual(rem, 7.0, places=2)


class TrayLogicTests(unittest.TestCase):
    def test_color_thresholds(self) -> None:
        self.assertEqual(accent_color_for(31, False, DeviceStatus.CONNECTED), COLOR_GREEN)
        self.assertEqual(accent_color_for(30, False, DeviceStatus.CONNECTED), COLOR_YELLOW)
        self.assertEqual(accent_color_for(16, False, DeviceStatus.CONNECTED), COLOR_YELLOW)
        self.assertEqual(accent_color_for(15, False, DeviceStatus.CONNECTED), COLOR_RED)
        self.assertEqual(accent_color_for(5, False, DeviceStatus.CONNECTED), COLOR_RED)
        self.assertEqual(accent_color_for(10, True, DeviceStatus.CHARGING), COLOR_CHARGING)

    def test_defaults_and_i18n(self) -> None:
        self.assertEqual(DEFAULT_SETTINGS["language"], "en")
        self.assertEqual(ALERT_THRESHOLDS, (15, 5))
        self.assertEqual(tr("en", "alerts"), "Alerts (15 / 5 %)")
        self.assertEqual(tr("de", "alerts"), "Warnung (15 / 5 %)")


if __name__ == "__main__":
    unittest.main()

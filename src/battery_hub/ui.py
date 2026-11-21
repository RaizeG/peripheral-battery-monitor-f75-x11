"""Unified PySide6 System Tray & Dashboard UI for AULA F75 + Attack Shark X11."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
import socket
import sys
import threading
import time
from typing import Callable, Optional

from PySide6.QtCore import QPointF, QRectF, QThread, QTimer, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QBrush,
    QCloseEvent,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .i18n import SUPPORTED_LANGUAGES, format_age, format_remaining, tr
from .keyboard_aula import PID_AULA_24G, VID_AULA, query_keyboard_battery
from .models import BatteryReading, DeviceId, DeviceStatus, HistoryPoint
from .mouse_asx11 import PID_ADAPTER, VID_ASX11, mouse_monitor_loop
from .storage import (
    APP_ID,
    APP_MUTEX,
    APP_NAME,
    append_history,
    estimate_drain_and_remaining,
    is_autostart_enabled,
    load_history,
    load_settings,
    log_error,
    save_settings,
    set_autostart,
)
from .tray_icon import DeviceBadgeState, accent_color_for, build_app_icon, build_combined_tray_icon

INSTANCE_PORT = 47613
ALERT_THRESHOLDS = (15, 5)
RANGES: list[tuple[str, Optional[float]]] = [
    ("1h", 3600),
    ("6h", 6 * 3600),
    ("24h", 24 * 3600),
    ("7d", 7 * 24 * 3600),
    ("all", None),
]

COLOR_KEYBOARD = QColor("#22C97A")
COLOR_MOUSE = QColor("#38BDF8")


# ---------------------------------------------------------------------------
# Background workers


class KeyboardPollWorker(QThread):
    finished_reading = Signal(object)

    def run(self) -> None:
        reading = query_keyboard_battery(timeout_ms=1200, retries=2)
        self.finished_reading.emit(reading)


class MouseMonitorWorker(QThread):
    reading_received = Signal(object, bool)

    def __init__(
        self,
        heartbeat_getter: Callable[[], float],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._stop_event = threading.Event()
        self._refresh_event = threading.Event()
        self._heartbeat_getter = heartbeat_getter

    def trigger_refresh(self) -> None:
        self._refresh_event.set()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        mouse_monitor_loop(
            lambda reading, is_change: self.reading_received.emit(reading, is_change),
            self._stop_event,
            heartbeat_getter=self._heartbeat_getter,
            refresh_event=self._refresh_event,
        )


# ---------------------------------------------------------------------------
# Single-instance server


class SingleInstanceServer(threading.Thread):
    def __init__(self, port: int, on_activate) -> None:
        super().__init__(daemon=True)
        self._port = port
        self._on_activate = on_activate
        self._sock: Optional[socket.socket] = None
        self._mutex_handle: Optional[int] = None
        self._stop = threading.Event()

    def acquire(self) -> bool:
        if os.name == "nt":
            try:
                kernel32 = ctypes.windll.kernel32
                kernel32.CreateMutexW.restype = ctypes.c_void_p
                handle = kernel32.CreateMutexW(None, False, APP_MUTEX)
                if handle:
                    self._mutex_handle = int(handle)
                    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
                        notify_existing_instance(self._port)
                        kernel32.CloseHandle(ctypes.c_void_p(handle))
                        self._mutex_handle = None
                        return False
            except Exception:
                pass

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", self._port))
            sock.listen(4)
            sock.settimeout(0.5)
            self._sock = sock
            return True
        except OSError:
            sock.close()
            notify_existing_instance(self._port)
            return False

    def run(self) -> None:
        if self._sock is None:
            return
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
                with conn:
                    conn.recv(64)
                self._on_activate()
            except socket.timeout:
                continue
            except OSError:
                break

    def close(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        if os.name == "nt" and self._mutex_handle:
            try:
                ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(self._mutex_handle))
            except Exception:
                pass
            self._mutex_handle = None


def notify_existing_instance(port: int = INSTANCE_PORT) -> bool:
    for _ in range(4):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.4) as s:
                s.sendall(b"SHOW")
            return True
        except OSError:
            time.sleep(0.1)
    return False


# ---------------------------------------------------------------------------
# Custom widgets


class BatteryGaugeWidget(QWidget):
    """Circular antialiased battery gauge."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._percent: Optional[int] = None
        self._charging: Optional[bool] = None
        self._status: DeviceStatus = DeviceStatus.WAITING
        self._subtitle: str = ""
        self.setMinimumSize(176, 176)
        self.setMaximumSize(190, 190)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_state(
        self,
        percent: Optional[int],
        charging: Optional[bool],
        status: DeviceStatus,
        subtitle: str,
    ) -> None:
        self._percent = percent
        self._charging = charging
        self._status = status
        self._subtitle = subtitle
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        side = min(self.width(), self.height())
        ring_w = 12.0
        pad = ring_w / 2.0 + 10.0
        rect = QRectF(
            (self.width() - side) / 2.0 + pad,
            (self.height() - side) / 2.0 + pad,
            side - 2 * pad,
            side - 2 * pad,
        )

        track_pen = QPen(QColor("#1A2D38"), ring_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(track_pen)
        painter.drawArc(rect, 0, 360 * 16)

        accent = accent_color_for(self._percent, self._charging, self._status)
        if self._status == DeviceStatus.CHARGING and self._percent is None:
            pct_for_ring: Optional[int] = 100
        elif self._percent is not None and self._status != DeviceStatus.DISCONNECTED:
            pct_for_ring = max(0, min(100, self._percent))
        else:
            pct_for_ring = None

        if pct_for_ring is not None:
            span = -int(round((pct_for_ring / 100.0) * 360 * 16))
            if span != 0:
                glow = QColor(accent)
                glow.setAlpha(42)
                painter.setPen(QPen(glow, ring_w + 7.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawArc(rect, 90 * 16, span)

                painter.setPen(QPen(accent, ring_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawArc(rect, 90 * 16, span)

        if self._percent is not None and self._status != DeviceStatus.DISCONNECTED:
            pct_text = f"{self._percent}%"
        elif self._status == DeviceStatus.CHARGING:
            pct_text = "⚡"
        else:
            pct_text = "—"

        painter.setFont(QFont("Segoe UI", 28, QFont.Weight.Bold))
        painter.setPen(QColor("#F5F8FA"))
        painter.drawText(
            QRectF(rect.left(), rect.top() + rect.height() * 0.24, rect.width(), rect.height() * 0.36),
            Qt.AlignmentFlag.AlignCenter,
            pct_text,
        )

        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        active = self._status in (DeviceStatus.CONNECTED, DeviceStatus.CHARGING)
        painter.setPen(accent if active else QColor("#8696A3"))
        painter.drawText(
            QRectF(rect.left() + 10, rect.top() + rect.height() * 0.59, rect.width() - 20, 22),
            Qt.AlignmentFlag.AlignCenter,
            self._subtitle,
        )

        painter.end()


class DeviceCardWidget(QFrame):
    """Unified card displaying one peripheral's battery gauge, status, and stats."""

    def __init__(self, title: str, subtitle: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setProperty("class", "card")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(8)
        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: #F5F8FA;")
        self.subtitle_lbl = QLabel(subtitle)
        self.subtitle_lbl.setProperty("class", "muted")
        title_box.addWidget(self.title_lbl)
        title_box.addWidget(self.subtitle_lbl)
        head.addLayout(title_box)
        head.addStretch()

        self.status_pill = QLabel("…")
        self.status_pill.setStyleSheet(
            "background-color: #13242E; border: 1px solid #23404F; "
            "border-radius: 11px; padding: 4px 10px; font-size: 11px; font-weight: 600; color: #C5D0D8;"
        )
        head.addWidget(self.status_pill, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(head)

        body = QHBoxLayout()
        body.setSpacing(16)

        self.gauge = BatteryGaugeWidget()
        body.addWidget(self.gauge, alignment=Qt.AlignmentFlag.AlignCenter)

        stats_col = QVBoxLayout()
        stats_col.setSpacing(10)
        stats_col.addStretch()
        self.lbl_connection, self.val_connection = self._add_stat(stats_col, "", "—")
        self.lbl_power, self.val_power = self._add_stat(stats_col, "", "—")
        self.lbl_remaining, self.val_remaining = self._add_stat(stats_col, "", "—")
        self.lbl_updated, self.val_updated = self._add_stat(stats_col, "", "—")
        stats_col.addStretch()
        body.addLayout(stats_col, 1)

        layout.addLayout(body)

    def _add_stat(self, parent_layout: QVBoxLayout, label: str, initial: str) -> tuple[QLabel, QLabel]:
        box = QVBoxLayout()
        box.setSpacing(1)
        lbl = QLabel(label)
        lbl.setProperty("class", "stat_label")
        val = QLabel(initial)
        val.setProperty("class", "stat_value")
        val.setWordWrap(True)
        box.addWidget(lbl)
        box.addWidget(val)
        parent_layout.addLayout(box)
        return lbl, val

    def set_pill(self, text: str, color_hex: str) -> None:
        self.status_pill.setText(text)
        self.status_pill.setStyleSheet(
            f"background-color: #11202A; border: 1px solid {color_hex}; "
            f"border-radius: 11px; padding: 4px 10px; font-size: 11px; font-weight: 600; color: {color_hex};"
        )


class DualBatteryChartWidget(QWidget):
    """Antialiased dual-series battery history chart for Keyboard & Mouse."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._kb_points: list[HistoryPoint] = []
        self._mouse_points: list[HistoryPoint] = []
        self._range_sec: Optional[float] = 24 * 3600
        self._filter: str = "both"
        self._empty_text: str = ""
        self.setMinimumHeight(185)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(
        self,
        kb_points: list[HistoryPoint],
        mouse_points: list[HistoryPoint],
        range_sec: Optional[float],
        device_filter: str,
        empty_text: str,
    ) -> None:
        self._kb_points = kb_points
        self._mouse_points = mouse_points
        self._range_sec = range_sec
        self._filter = device_filter
        self._empty_text = empty_text
        self.update()

    def _draw_series(
        self,
        painter: QPainter,
        plot: QRectF,
        points: list[HistoryPoint],
        t_min: float,
        span: float,
        color: QColor,
        fill_alpha: int,
    ) -> None:
        if not points:
            return
        coords: list[QPointF] = []
        for pt in points:
            x = plot.left() + ((pt.timestamp - t_min) / span) * plot.width()
            x = max(plot.left(), min(plot.right(), x))
            y = plot.bottom() - (pt.percent / 100.0) * plot.height()
            coords.append(QPointF(x, y))

        if len(coords) >= 2:
            line_path = QPainterPath(coords[0])
            for c in coords[1:]:
                line_path.lineTo(c)

            fill_path = QPainterPath(line_path)
            fill_path.lineTo(coords[-1].x(), plot.bottom())
            fill_path.lineTo(coords[0].x(), plot.bottom())
            fill_path.closeSubpath()

            grad = QLinearGradient(0, plot.top(), 0, plot.bottom())
            top_c = QColor(color)
            top_c.setAlpha(fill_alpha)
            bot_c = QColor(color)
            bot_c.setAlpha(4)
            grad.setColorAt(0.0, top_c)
            grad.setColorAt(1.0, bot_c)
            painter.fillPath(fill_path, QBrush(grad))

            painter.setPen(
                QPen(color, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            )
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(line_path)

        last_pt = coords[-1]
        painter.setPen(QPen(QColor("#081017"), 2.0))
        painter.setBrush(color)
        painter.drawEllipse(last_pt, 4.2, 4.2)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        w = float(self.width())
        h = float(self.height())
        outer = QRectF(0.5, 0.5, w - 1.0, h - 1.0)
        painter.setBrush(QColor("#0A141B"))
        painter.setPen(QPen(QColor("#1E3440"), 1.0))
        painter.drawRoundedRect(outer, 10.0, 10.0)

        left = 42.0
        right = 16.0
        top = 14.0
        bottom = 26.0
        plot = QRectF(left, top, max(10.0, w - left - right), max(10.0, h - top - bottom))

        grid_pen = QPen(QColor("#1B2D37"), 1.0, Qt.PenStyle.DashLine)
        axis_font = QFont("Segoe UI", 8)
        painter.setFont(axis_font)
        for pct in (0, 25, 50, 75, 100):
            y = plot.bottom() - (pct / 100.0) * plot.height()
            painter.setPen(grid_pen)
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(QColor("#7E92A0"))
            painter.drawText(
                QRectF(4.0, y - 8.0, left - 10.0, 16.0),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{pct}%",
            )

        show_kb = self._filter in ("both", "keyboard")
        show_mouse = self._filter in ("both", "mouse")
        active_points = (self._kb_points if show_kb else []) + (self._mouse_points if show_mouse else [])

        if not active_points:
            painter.setPen(QColor("#7E92A0"))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(plot, Qt.AlignmentFlag.AlignCenter, self._empty_text)
            painter.end()
            return

        now = time.time()
        max_ts = max(p.timestamp for p in active_points)
        min_ts = min(p.timestamp for p in active_points)
        if self._range_sec is not None:
            t_max = max(now, max_ts)
            t_min = t_max - self._range_sec
        else:
            t_min = min_ts
            t_max = max(now, max_ts)
            if t_max - t_min < 60:
                t_min = t_max - 3600

        span = max(1.0, t_max - t_min)

        if show_kb:
            self._draw_series(painter, plot, self._kb_points, t_min, span, COLOR_KEYBOARD, 48)
        if show_mouse:
            self._draw_series(painter, plot, self._mouse_points, t_min, span, COLOR_MOUSE, 44)

        painter.setPen(QColor("#7E92A0"))
        painter.setFont(axis_font)
        use_date = span > 36 * 3600
        fmt = "%d.%m." if use_date else "%H:%M"
        for frac, align in (
            (0.0, Qt.AlignmentFlag.AlignLeft),
            (0.5, Qt.AlignmentFlag.AlignCenter),
            (1.0, Qt.AlignmentFlag.AlignRight),
        ):
            t_val = t_min + span * frac
            label = time.strftime(fmt, time.localtime(t_val))
            x_box = plot.left() + frac * plot.width()
            if frac == 0.0:
                r = QRectF(plot.left(), plot.bottom() + 4, 80, 18)
            elif frac == 1.0:
                r = QRectF(plot.right() - 80, plot.bottom() + 4, 80, 18)
            else:
                r = QRectF(x_box - 40, plot.bottom() + 4, 80, 18)
            painter.drawText(r, align | Qt.AlignmentFlag.AlignVCenter, label)

        painter.end()


# ---------------------------------------------------------------------------
# Main Dashboard Window


class HubDashboardWindow(QMainWindow):
    def __init__(self, entrypoint: Path) -> None:
        super().__init__()
        self._entrypoint = entrypoint
        self._settings = load_settings()
        self._lang: str = str(self._settings.get("language") or "en")
        if self._lang not in ("en", "de"):
            self._lang = "en"
        self._quitting = False

        self._last_percent: dict[DeviceId, Optional[int]] = {
            DeviceId.KEYBOARD: self._settings.get("keyboard_last_percent"),
            DeviceId.MOUSE: self._settings.get("mouse_last_percent"),
        }
        self._last_seen: dict[DeviceId, Optional[float]] = {
            DeviceId.KEYBOARD: self._settings.get("keyboard_last_seen"),
            DeviceId.MOUSE: self._settings.get("mouse_last_seen"),
        }
        self._last_charging: dict[DeviceId, Optional[bool]] = {
            DeviceId.KEYBOARD: None,
            DeviceId.MOUSE: None,
        }
        self._last_status: dict[DeviceId, DeviceStatus] = {
            DeviceId.KEYBOARD: DeviceStatus.SLEEPING,
            DeviceId.MOUSE: DeviceStatus.WAITING,
        }
        self._last_readings: dict[DeviceId, BatteryReading] = {
            DeviceId.KEYBOARD: BatteryReading(
                device_id=DeviceId.KEYBOARD,
                status=DeviceStatus.SLEEPING,
                percent=self._last_percent[DeviceId.KEYBOARD],
                timestamp=self._last_seen[DeviceId.KEYBOARD] or 0.0,
            ),
            DeviceId.MOUSE: BatteryReading(
                device_id=DeviceId.MOUSE,
                status=DeviceStatus.WAITING,
                percent=self._last_percent[DeviceId.MOUSE],
                timestamp=self._last_seen[DeviceId.MOUSE] or 0.0,
            ),
        }
        self._last_logged_percent: dict[DeviceId, Optional[int]] = {
            DeviceId.KEYBOARD: None,
            DeviceId.MOUSE: None,
        }
        self._last_logged_time: dict[DeviceId, float] = {
            DeviceId.KEYBOARD: 0.0,
            DeviceId.MOUSE: 0.0,
        }
        self._alerted_levels: dict[DeviceId, set[int]] = {
            DeviceId.KEYBOARD: set(),
            DeviceId.MOUSE: set(),
        }
        self._tray_lines: dict[DeviceId, str] = {
            DeviceId.KEYBOARD: f"⌨ AULA F75 — {self._t('tray_loading')}",
            DeviceId.MOUSE: f"🖱 Attack Shark X11 — {self._t('tray_loading')}",
        }

        self._selected_range_sec: Optional[float] = 24 * 3600
        self._chart_filter: str = "both"
        self._kb_worker: Optional[KeyboardPollWorker] = None

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(build_app_icon())
        self.resize(980, 620)
        self.setMinimumSize(860, 540)

        self._apply_stylesheet()
        self._build_ui()
        self._build_tray()
        self._apply_language()

        # Shared polling timer (triggers keyboard poll; mouse monitor uses the same interval)
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self.trigger_poll_all)
        self._apply_poll_interval()

        self._age_timer = QTimer(self)
        self._age_timer.timeout.connect(self._refresh_age_labels)
        self._age_timer.start(10_000)

        self._mouse_worker = MouseMonitorWorker(
            heartbeat_getter=lambda: max(10.0, float(self._settings.get("poll_interval_sec", 30))),
            parent=self,
        )
        self._mouse_worker.reading_received.connect(self._on_mouse_reading)
        self._mouse_worker.start()

        QTimer.singleShot(150, self.trigger_poll_all)

    def _t(self, key: str, **kwargs) -> str:
        return tr(self._lang, key, **kwargs)

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget#root {
                background-color: #081017;
                color: #F5F8FA;
                font-family: "Segoe UI", sans-serif;
            }
            QFrame.card {
                background-color: #0D1821;
                border: 1px solid #1E3945;
                border-radius: 14px;
            }
            QLabel.title {
                font-size: 20px;
                font-weight: 700;
                color: #F5F8FA;
            }
            QLabel.muted {
                color: #8696A3;
                font-size: 12px;
            }
            QLabel.stat_label {
                color: #8696A3;
                font-size: 10px;
                font-weight: 600;
                text-transform: uppercase;
            }
            QLabel.stat_value {
                color: #F5F8FA;
                font-size: 13px;
                font-weight: 700;
            }
            QPushButton {
                background-color: #142631;
                color: #F5F8FA;
                border: 1px solid #244554;
                border-radius: 8px;
                padding: 7px 14px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #1B3441;
                border-color: #2E5B6E;
            }
            QPushButton:disabled {
                color: #5C7280;
                background-color: #0E1B24;
            }
            QPushButton.pill_btn {
                padding: 4px 10px;
                border-radius: 6px;
                font-size: 11px;
                background-color: #0F1D27;
                border: 1px solid #1D3440;
                color: #9BB0BD;
            }
            QPushButton.pill_btn[active="true"] {
                background-color: #173D32;
                border-color: #22C97A;
                color: #E8FFF4;
            }
            QComboBox {
                background-color: #142631;
                color: #F5F8FA;
                border: 1px solid #244554;
                border-radius: 7px;
                padding: 4px 10px;
                font-size: 12px;
            }
            QComboBox QAbstractItemView {
                background-color: #0D1821;
                color: #F5F8FA;
                selection-background-color: #1B3441;
                border: 1px solid #1E3945;
            }
            QCheckBox {
                color: #C5D0D8;
                font-size: 12px;
                spacing: 7px;
            }
            QCheckBox::indicator {
                width: 15px;
                height: 15px;
                border-radius: 4px;
                border: 1px solid #2D4E5E;
                background-color: #0D1821;
            }
            QCheckBox::indicator:checked {
                background-color: #22C97A;
                border-color: #22C97A;
            }
            """
        )

    def _build_ui(self) -> None:
        root = QWidget(self)
        root.setObjectName("root")
        self.setCentralWidget(root)

        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(20, 16, 20, 14)
        main_layout.setSpacing(14)

        # Header
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title_lbl = QLabel(APP_NAME)
        title_lbl.setProperty("class", "title")
        self._subtitle_lbl = QLabel("")
        self._subtitle_lbl.setProperty("class", "muted")
        title_box.addWidget(title_lbl)
        title_box.addWidget(self._subtitle_lbl)
        header.addLayout(title_box)
        header.addStretch()

        self._refresh_btn = QPushButton("")
        self._refresh_btn.clicked.connect(self.trigger_poll_all)
        header.addWidget(self._refresh_btn)
        main_layout.addLayout(header)

        # Side-by-side Device Cards
        cards_row = QHBoxLayout()
        cards_row.setSpacing(14)

        self._kb_card = DeviceCardWidget("⌨ AULA F75", "")
        self._mouse_card = DeviceCardWidget("🖱 Attack Shark X11", "")
        self._cards = {
            DeviceId.KEYBOARD: self._kb_card,
            DeviceId.MOUSE: self._mouse_card,
        }
        cards_row.addWidget(self._kb_card, 1)
        cards_row.addWidget(self._mouse_card, 1)
        main_layout.addLayout(cards_row)

        # Combined History Chart Card
        chart_card = QFrame()
        chart_card.setProperty("class", "card")
        chart_layout = QVBoxLayout(chart_card)
        chart_layout.setContentsMargins(16, 12, 16, 12)
        chart_layout.setSpacing(10)

        chart_header = QHBoxLayout()
        self._chart_title_lbl = QLabel("")
        self._chart_title_lbl.setStyleSheet("font-size: 14px; font-weight: 700; color: #F5F8FA;")
        chart_header.addWidget(self._chart_title_lbl)

        self._legend_kb_lbl = QLabel("")
        self._legend_kb_lbl.setStyleSheet("color: #22C97A; font-size: 11px; font-weight: 600; margin-left: 10px;")
        self._legend_mouse_lbl = QLabel("")
        self._legend_mouse_lbl.setStyleSheet("color: #38BDF8; font-size: 11px; font-weight: 600; margin-left: 6px;")
        chart_header.addWidget(self._legend_kb_lbl)
        chart_header.addWidget(self._legend_mouse_lbl)
        chart_header.addStretch()

        self._filter_buttons: list[tuple[QPushButton, str]] = []
        for key in ("both", "keyboard", "mouse"):
            btn = QPushButton("")
            btn.setProperty("class", "pill_btn")
            btn.setProperty("active", key == self._chart_filter)
            btn.clicked.connect(lambda _c=False, k=key: self._select_chart_filter(k))
            chart_header.addWidget(btn)
            self._filter_buttons.append((btn, key))

        sep = QLabel("|")
        sep.setStyleSheet("color: #28414F; margin: 0 4px;")
        chart_header.addWidget(sep)

        self._range_buttons: list[tuple[QPushButton, str, Optional[float]]] = []
        for key, secs in RANGES:
            btn = QPushButton(key)
            btn.setProperty("class", "pill_btn")
            btn.setProperty("active", secs == self._selected_range_sec)
            btn.clicked.connect(lambda _c=False, s=secs: self._select_range(s))
            chart_header.addWidget(btn)
            self._range_buttons.append((btn, key, secs))

        chart_layout.addLayout(chart_header)
        self._chart = DualBatteryChartWidget()
        chart_layout.addWidget(self._chart)
        main_layout.addWidget(chart_card, 1)

        # Footer controls
        footer = QHBoxLayout()
        footer.setSpacing(12)

        self._autostart_cb = QCheckBox("")
        self._autostart_cb.setChecked(is_autostart_enabled())
        self._autostart_cb.toggled.connect(self._on_autostart_toggled)
        footer.addWidget(self._autostart_cb)

        self._alerts_cb = QCheckBox("")
        self._alerts_cb.setChecked(bool(self._settings.get("alerts_enabled", True)))
        self._alerts_cb.toggled.connect(self._on_alerts_toggled)
        footer.addWidget(self._alerts_cb)

        footer.addStretch()

        self._iv_lbl = QLabel("")
        self._iv_lbl.setProperty("class", "muted")
        footer.addWidget(self._iv_lbl)

        self._interval_values = [15, 30, 60, 300]
        self._interval_combo = QComboBox()
        current_iv = int(self._settings.get("poll_interval_sec", 30))
        sel_idx = 1
        for i, secs in enumerate(self._interval_values):
            self._interval_combo.addItem("", secs)
            if secs == current_iv:
                sel_idx = i
        self._interval_combo.setCurrentIndex(sel_idx)
        self._interval_combo.currentIndexChanged.connect(self._on_interval_changed)
        footer.addWidget(self._interval_combo)

        self._lang_lbl = QLabel("")
        self._lang_lbl.setProperty("class", "muted")
        footer.addWidget(self._lang_lbl)

        self._lang_combo = QComboBox()
        lang_idx = 0
        for i, (label, code) in enumerate(SUPPORTED_LANGUAGES):
            self._lang_combo.addItem(label, code)
            if code == self._lang:
                lang_idx = i
        self._lang_combo.setCurrentIndex(lang_idx)
        self._lang_combo.currentIndexChanged.connect(self._on_language_changed)
        footer.addWidget(self._lang_combo)

        ver_lbl = QLabel(f"v{__version__}")
        ver_lbl.setProperty("class", "muted")
        footer.addWidget(ver_lbl)
        main_layout.addLayout(footer)

    def _build_tray(self) -> None:
        self._tray = QSystemTrayIcon(self)
        menu = QMenu()

        self._tray_kb_action = QAction(self._tray_lines[DeviceId.KEYBOARD], self)
        self._tray_kb_action.triggered.connect(self.show_and_focus)
        menu.addAction(self._tray_kb_action)

        self._tray_mouse_action = QAction(self._tray_lines[DeviceId.MOUSE], self)
        self._tray_mouse_action.triggered.connect(self.show_and_focus)
        menu.addAction(self._tray_mouse_action)

        menu.addSeparator()

        self._tray_open_action = QAction("", self)
        self._tray_open_action.triggered.connect(self.show_and_focus)
        menu.addAction(self._tray_open_action)

        self._tray_refresh_action = QAction("", self)
        self._tray_refresh_action.triggered.connect(self.trigger_poll_all)
        menu.addAction(self._tray_refresh_action)

        self._tray_autostart_action = QAction("", self)
        self._tray_autostart_action.setCheckable(True)
        self._tray_autostart_action.setChecked(self._autostart_cb.isChecked())
        self._tray_autostart_action.toggled.connect(self._autostart_cb.setChecked)
        menu.addAction(self._tray_autostart_action)

        menu.addSeparator()
        self._tray_quit_action = QAction("", self)
        self._tray_quit_action.triggered.connect(self.quit_app)
        menu.addAction(self._tray_quit_action)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._refresh_tray()
        self._tray.show()

    def _apply_language(self) -> None:
        self._subtitle_lbl.setText(self._t("subtitle"))
        self._refresh_btn.setText(self._t("refresh"))

        self._kb_card.subtitle_lbl.setText(self._t("kb_sub", vid=VID_AULA, pid=PID_AULA_24G))
        self._mouse_card.subtitle_lbl.setText(self._t("mouse_sub", vid=VID_ASX11, pid=PID_ADAPTER))

        for card in self._cards.values():
            card.lbl_connection.setText(self._t("stat_connection"))
            card.lbl_power.setText(self._t("stat_status"))
            card.lbl_remaining.setText(self._t("stat_remaining"))
            card.lbl_updated.setText(self._t("stat_updated"))

        self._chart_title_lbl.setText(self._t("chart_title"))
        self._legend_kb_lbl.setText(self._t("legend_kb"))
        self._legend_mouse_lbl.setText(self._t("legend_mouse"))

        filter_key_map = {"both": "filter_both", "keyboard": "filter_kb", "mouse": "filter_mouse"}
        for btn, key in self._filter_buttons:
            btn.setText(self._t(filter_key_map[key]))

        for btn, key, _secs in self._range_buttons:
            btn.setText(self._t("range_all") if key == "all" else key)

        self._autostart_cb.setText(self._t("autostart"))
        self._alerts_cb.setText(self._t("alerts"))
        self._iv_lbl.setText(self._t("poll_interval"))
        self._lang_lbl.setText(self._t("lang_label"))

        iv_keys = {15: "iv_15", 30: "iv_30", 60: "iv_60", 300: "iv_300"}
        for i, secs in enumerate(self._interval_values):
            self._interval_combo.setItemText(i, self._t(iv_keys[secs]))

        self._tray_open_action.setText(self._t("tray_open"))
        self._tray_refresh_action.setText(self._t("tray_refresh"))
        self._tray_autostart_action.setText(self._t("autostart"))
        self._tray_quit_action.setText(self._t("tray_quit"))

        # Re-render both device cards, chart, and tray in the selected language
        for dev in (DeviceId.KEYBOARD, DeviceId.MOUSE):
            self._update_device_view(self._last_readings[dev], initial=True)

    def _on_language_changed(self, idx: int) -> None:
        code = str(self._lang_combo.itemData(idx) or "en")
        if code == self._lang:
            return
        self._lang = code
        self._settings["language"] = code
        save_settings(self._settings)
        self._apply_language()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            if self.isVisible() and not self.isMinimized() and self.isActiveWindow():
                self.hide()
            else:
                self.show_and_focus()

    def show_and_focus(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._quitting or not QSystemTrayIcon.isSystemTrayAvailable():
            event.accept()
            return
        event.ignore()
        self.hide()

    def quit_app(self) -> None:
        self._quitting = True
        self._poll_timer.stop()
        self._age_timer.stop()
        if self._mouse_worker.isRunning():
            self._mouse_worker.stop()
            self._mouse_worker.wait(1500)
        self._tray.hide()
        QApplication.quit()

    def _apply_poll_interval(self) -> None:
        secs = max(10, int(self._settings.get("poll_interval_sec", 30)))
        self._poll_timer.start(secs * 1000)

    def _on_interval_changed(self, idx: int) -> None:
        secs = int(self._interval_combo.itemData(idx))
        self._settings["poll_interval_sec"] = secs
        save_settings(self._settings)
        self._apply_poll_interval()

    def _on_autostart_toggled(self, checked: bool) -> None:
        ok = set_autostart(checked, self._entrypoint)
        if not ok:
            self._autostart_cb.blockSignals(True)
            self._autostart_cb.setChecked(is_autostart_enabled())
            self._autostart_cb.blockSignals(False)
        self._tray_autostart_action.blockSignals(True)
        self._tray_autostart_action.setChecked(self._autostart_cb.isChecked())
        self._tray_autostart_action.blockSignals(False)

    def _on_alerts_toggled(self, checked: bool) -> None:
        self._settings["alerts_enabled"] = bool(checked)
        save_settings(self._settings)

    def _select_range(self, secs: Optional[float]) -> None:
        self._selected_range_sec = secs
        for btn, _k, s in self._range_buttons:
            btn.setProperty("active", s == secs)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._refresh_chart()

    def _select_chart_filter(self, key: str) -> None:
        self._chart_filter = key
        for btn, k in self._filter_buttons:
            btn.setProperty("active", k == key)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._refresh_chart()

    # -----------------------------------------------------------------------
    # Polling & updates

    def trigger_poll_all(self) -> None:
        if hasattr(self, "_mouse_worker") and self._mouse_worker.isRunning():
            self._mouse_worker.trigger_refresh()
        if self._kb_worker is not None and self._kb_worker.isRunning():
            return
        self._refresh_btn.setEnabled(False)
        self._kb_worker = KeyboardPollWorker(self)
        self._kb_worker.finished_reading.connect(self._on_keyboard_poll_finished)
        self._kb_worker.start()

    def _on_keyboard_poll_finished(self, reading: BatteryReading) -> None:
        self._refresh_btn.setEnabled(True)
        self._update_device_view(reading, initial=False)

    def _on_mouse_reading(self, reading: BatteryReading, _is_change: bool) -> None:
        self._update_device_view(reading, initial=False)

    def _localized_connection(self, dev: DeviceId, status: DeviceStatus) -> str:
        if status == DeviceStatus.DISCONNECTED:
            return self._t("conn_disconnected")
        if status == DeviceStatus.ERROR:
            return self._t("conn_error")
        if dev == DeviceId.KEYBOARD:
            if status == DeviceStatus.CHARGING:
                return self._t("conn_kb_charging")
            if status == DeviceStatus.CONNECTED:
                return self._t("conn_kb_active")
            return self._t("conn_kb_standby")
        if status == DeviceStatus.CHARGING:
            return self._t("conn_mouse_charging")
        if status == DeviceStatus.CONNECTED:
            return self._t("conn_mouse_active")
        return self._t("conn_mouse_waiting")

    def _update_device_view(self, reading: BatteryReading, *, initial: bool) -> None:
        dev = reading.device_id
        self._last_readings[dev] = reading
        self._last_status[dev] = reading.status

        if reading.status in (DeviceStatus.CONNECTED, DeviceStatus.CHARGING) and reading.percent is not None:
            self._last_percent[dev] = reading.percent
            self._last_charging[dev] = reading.charging
            self._last_seen[dev] = reading.timestamp
            self._settings[f"{dev.value}_last_percent"] = reading.percent
            self._settings[f"{dev.value}_last_seen"] = reading.timestamp
            save_settings(self._settings)

            if not initial:
                now = reading.timestamp
                should_log = (
                    self._last_logged_percent[dev] != reading.percent
                    or (now - self._last_logged_time[dev]) >= 900
                )
                if should_log:
                    append_history(dev, reading.percent, bool(reading.charging), now)
                    self._last_logged_percent[dev] = reading.percent
                    self._last_logged_time[dev] = now

            self._check_low_battery_alerts(dev, reading.percent, bool(reading.charging))
        elif reading.status == DeviceStatus.CHARGING:
            self._last_charging[dev] = True
            self._alerted_levels[dev].clear()
            if not initial and reading.timestamp:
                self._last_seen[dev] = reading.timestamp

        display_pct = (
            reading.percent
            if reading.percent is not None
            else (None if reading.status == DeviceStatus.DISCONNECTED else self._last_percent[dev])
        )
        display_chg = (
            reading.charging
            if reading.status in (DeviceStatus.CONNECTED, DeviceStatus.CHARGING)
            else None
        )

        prefix = "⌨ AULA F75" if dev == DeviceId.KEYBOARD else "🖱 Attack Shark X11"
        card = self._cards[dev]
        conn_val = self._localized_connection(dev, reading.status)

        if reading.status == DeviceStatus.CHARGING:
            pill_text = self._t("pill_charging")
            pill_color = "#38BDF8"
            gauge_sub = self._t("gauge_charging")
            power_val = self._t("power_charging")
            tray_line = (
                self._t("tray_charging_pct", prefix=prefix, pct=display_pct)
                if display_pct is not None
                else self._t("tray_charging_usb", prefix=prefix)
            )
        elif reading.status == DeviceStatus.CONNECTED:
            pill_text = self._t("pill_active")
            # Green when active on battery for BOTH keyboard & mouse; blue is charging only
            pill_color = "#22C97A"
            gauge_sub = self._t("gauge_battery")
            power_val = self._t("power_battery")
            tray_line = self._t("tray_active_pct", prefix=prefix, pct=display_pct)
        elif reading.status == DeviceStatus.SLEEPING:
            pill_text = self._t("pill_sleeping")
            pill_color = "#94A3B8"
            gauge_sub = self._t("gauge_sleeping") if display_pct is not None else self._t("gauge_press_key")
            power_val = self._t("power_sleeping")
            tray_line = (
                self._t("tray_standby_pct", prefix=prefix, pct=display_pct)
                if display_pct is not None
                else self._t("tray_sleeping", prefix=prefix)
            )
        elif reading.status == DeviceStatus.WAITING:
            pill_text = self._t("pill_waiting")
            pill_color = "#94A3B8"
            gauge_sub = self._t("gauge_move_mouse") if display_pct is None else self._t("gauge_standby")
            power_val = self._t("power_waiting")
            tray_line = (
                self._t("tray_standby_pct", prefix=prefix, pct=display_pct)
                if display_pct is not None
                else self._t("tray_waiting", prefix=prefix)
            )
        elif reading.status == DeviceStatus.DISCONNECTED:
            pill_text = self._t("pill_disconnected")
            pill_color = "#EF4444"
            gauge_sub = self._t("gauge_no_dongle")
            power_val = "—"
            tray_line = self._t("tray_disconnected", prefix=prefix)
        else:
            pill_text = self._t("pill_error")
            pill_color = "#F59E0B"
            gauge_sub = self._t("gauge_error")
            power_val = "—"
            if reading.error_message:
                conn_val = reading.error_message
            tray_line = self._t("tray_error", prefix=prefix)
            if not initial and reading.error_message:
                log_error(f"[{dev.value}] {reading.error_message}")

        card.set_pill(pill_text, pill_color)
        card.gauge.set_state(display_pct, display_chg, reading.status, gauge_sub)
        card.val_connection.setText(conn_val)
        card.val_power.setText(power_val)
        self._tray_lines[dev] = tray_line

        self._refresh_tray()
        self._refresh_age_labels()
        self._refresh_chart()

    def _badge_state(self, dev: DeviceId) -> DeviceBadgeState:
        status = self._last_status[dev]
        pct = None if status == DeviceStatus.DISCONNECTED else self._last_percent[dev]
        chg = self._last_charging[dev] if status in (DeviceStatus.CONNECTED, DeviceStatus.CHARGING) else None
        return DeviceBadgeState(percent=pct, charging=chg, status=status)

    def _refresh_tray(self) -> None:
        kb_state = self._badge_state(DeviceId.KEYBOARD)
        mouse_state = self._badge_state(DeviceId.MOUSE)
        icon = build_combined_tray_icon(kb_state, mouse_state)
        self._tray.setIcon(icon)
        if not self._tray.isVisible():
            self._tray.show()

        kb_line = self._tray_lines[DeviceId.KEYBOARD]
        mouse_line = self._tray_lines[DeviceId.MOUSE]
        self._tray_kb_action.setText(kb_line)
        self._tray_mouse_action.setText(mouse_line)
        self._tray.setToolTip(f"{kb_line}\n{mouse_line}")

    def _refresh_age_labels(self) -> None:
        for dev, card in self._cards.items():
            ts = self._last_seen[dev]
            card.val_updated.setText(format_age(ts, self._lang))

    def _refresh_chart(self) -> None:
        kb_all = load_history(DeviceId.KEYBOARD, None)
        mouse_all = load_history(DeviceId.MOUSE, None)
        kb_vis = load_history(DeviceId.KEYBOARD, self._selected_range_sec)
        mouse_vis = load_history(DeviceId.MOUSE, self._selected_range_sec)
        self._chart.set_data(
            kb_vis,
            mouse_vis,
            self._selected_range_sec,
            self._chart_filter,
            self._t("chart_empty"),
        )

        for dev, pts in ((DeviceId.KEYBOARD, kb_all), (DeviceId.MOUSE, mouse_all)):
            card = self._cards[dev]
            if self._last_status[dev] == DeviceStatus.CHARGING or self._last_charging[dev]:
                card.val_remaining.setText(self._t("power_charging"))
            else:
                rate, rem_hours = estimate_drain_and_remaining(pts, self._last_percent[dev])
                if rate is not None and rem_hours is not None:
                    unit = "%/h" if self._lang == "en" else "%/Std."
                    card.val_remaining.setText(f"{format_remaining(rem_hours, self._lang)} ({rate:.1f} {unit})")
                else:
                    card.val_remaining.setText(self._t("collecting"))

    def _check_low_battery_alerts(self, dev: DeviceId, percent: int, charging: bool) -> None:
        if charging:
            self._alerted_levels[dev].clear()
            return

        for lvl in list(self._alerted_levels[dev]):
            if percent > lvl + 2:
                self._alerted_levels[dev].discard(lvl)

        if not self._settings.get("alerts_enabled", True):
            return

        name = self._t("name_kb") if dev == DeviceId.KEYBOARD else self._t("name_mouse")
        for lvl in ALERT_THRESHOLDS:
            if percent <= lvl and lvl not in self._alerted_levels[dev]:
                self._alerted_levels[dev].add(lvl)
                self._tray.showMessage(
                    self._t("alert_title", name=name),
                    self._t("alert_body", pct=percent),
                    QSystemTrayIcon.MessageIcon.Warning,
                    6000,
                )
                break


def run_gui(entrypoint: Path, start_minimized: bool = False) -> int:
    server = SingleInstanceServer(INSTANCE_PORT, lambda: None)
    if not server.acquire():
        return 0

    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(build_app_icon())
    app.setQuitOnLastWindowClosed(False)

    window = HubDashboardWindow(entrypoint)
    server._on_activate = lambda: QTimer.singleShot(0, window.show_and_focus)
    server.start()

    if not start_minimized or not QSystemTrayIcon.isSystemTrayAvailable():
        window.show_and_focus()

    try:
        return app.exec()
    finally:
        server.close()

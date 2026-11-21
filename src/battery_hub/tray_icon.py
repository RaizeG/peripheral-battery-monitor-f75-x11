"""High-DPI crisp dual vertical battery-bar tray icon renderer for Peripheral Battery Hub.

Shows two vertical battery bars side by side:
  - Left bar:  Keyboard (AULA F75)
  - Right bar: Mouse (Attack Shark X11)

Color thresholds per bar:
  - > 30%:  Green  (#22C97A)
  - <= 30%: Yellow (#FACC15)
  - <= 15%: Red    (#EF4444)
  - Charging: Sky Blue (#38BDF8)
  - Disconnected / unknown: Slate (#64748B)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from .models import DeviceStatus

COLOR_GREEN = QColor("#22C97A")
COLOR_YELLOW = QColor("#FACC15")
COLOR_RED = QColor("#EF4444")
COLOR_CHARGING = QColor("#38BDF8")
COLOR_MUTED = QColor("#64748B")


@dataclass(frozen=True)
class DeviceBadgeState:
    percent: Optional[int]
    charging: Optional[bool]
    status: DeviceStatus


def accent_color_for(
    percent: Optional[int],
    charging: Optional[bool],
    status: DeviceStatus,
) -> QColor:
    if status in (DeviceStatus.DISCONNECTED, DeviceStatus.ERROR):
        return COLOR_MUTED
    if status == DeviceStatus.CHARGING or charging:
        return COLOR_CHARGING
    if percent is None:
        return COLOR_MUTED
    if percent <= 15:
        return COLOR_RED
    if percent <= 30:
        return COLOR_YELLOW
    return COLOR_GREEN


def _draw_vertical_battery_bar(
    painter: QPainter,
    body_rect: QRectF,
    state: DeviceBadgeState,
    size: int,
) -> None:
    color = accent_color_for(state.percent, state.charging, state.status)
    is_disconnected = state.status in (DeviceStatus.DISCONNECTED, DeviceStatus.ERROR)

    # Small battery terminal cap centered on top of the bar
    cap_w = max(2.0, body_rect.width() * 0.48)
    cap_h = max(1.2, size * 0.065)
    cap_rect = QRectF(
        body_rect.center().x() - cap_w / 2.0,
        body_rect.top() - cap_h - max(0.4, size * 0.015),
        cap_w,
        cap_h,
    )
    cap_color = QColor("#475569") if is_disconnected else color
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(cap_color)
    painter.drawRoundedRect(cap_rect, cap_h / 2.0, cap_h / 2.0)

    # Track background
    radius = max(1.5, body_rect.width() * 0.24)
    track_path = QPainterPath()
    track_path.addRoundedRect(body_rect, radius, radius)
    painter.fillPath(track_path, QColor("#162631"))

    # Fill level from bottom to top
    if state.status == DeviceStatus.CHARGING and state.percent is None:
        fill_frac = 1.0
    elif state.percent is not None and not is_disconnected:
        fill_frac = max(0.0, min(100, state.percent)) / 100.0
    else:
        fill_frac = 0.0

    if fill_frac > 0.0:
        inset = max(0.8, size * 0.025)
        inner = body_rect.adjusted(inset, inset, -inset, -inset)
        fill_h = max(1.5, inner.height() * fill_frac)
        fill_rect = QRectF(
            inner.left(),
            inner.bottom() - fill_h,
            inner.width(),
            fill_h,
        )

        painter.save()
        clip_path = QPainterPath()
        clip_path.addRoundedRect(inner, max(1.0, radius - inset * 0.5), max(1.0, radius - inset * 0.5))
        painter.setClipPath(clip_path)

        fill_color = QColor(color)
        if state.status in (DeviceStatus.SLEEPING, DeviceStatus.WAITING):
            fill_color.setAlpha(190)
        painter.fillRect(fill_rect, fill_color)
        painter.restore()

    # Crisp outline around each vertical bar
    border_w = max(0.9, size * 0.038)
    outline_color = QColor("#334B5C") if is_disconnected else QColor(color)
    if not is_disconnected and state.status not in (DeviceStatus.CHARGING,) and (
        state.percent is None or state.percent > 30
    ):
        outline_color = QColor("#3B5B6E")
    painter.setPen(QPen(outline_color, border_w))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(body_rect, radius, radius)


def render_combined_pixmap(
    size: int,
    kb: DeviceBadgeState,
    mouse: DeviceBadgeState,
) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    # Dark rounded square badge backdrop so bars stay crisp on any taskbar theme
    margin = max(0.8, size * 0.03)
    bg_rect = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)
    bg_radius = size * 0.20
    bg_path = QPainterPath()
    bg_path.addRoundedRect(bg_rect, bg_radius, bg_radius)
    painter.fillPath(bg_path, QColor("#0B141C"))

    border_pen = QPen(QColor("#223846"), max(0.8, size * 0.035))
    painter.setPen(border_pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(bg_rect.adjusted(0.5, 0.5, -0.5, -0.5), bg_radius, bg_radius)

    # Two side-by-side vertical battery bars: Left = Keyboard, Right = Mouse
    pad_x = max(2.2, size * 0.14)
    gap = max(1.8, size * 0.12)
    top_y = max(3.0, size * 0.21)
    bottom_pad = max(2.0, size * 0.12)

    avail_w = size - 2 * pad_x - gap
    bar_w = max(3.0, avail_w / 2.0)
    bar_h = max(6.0, size - top_y - bottom_pad)

    left_bar = QRectF(pad_x, top_y, bar_w, bar_h)
    right_bar = QRectF(pad_x + bar_w + gap, top_y, bar_w, bar_h)

    _draw_vertical_battery_bar(painter, left_bar, kb, size)
    _draw_vertical_battery_bar(painter, right_bar, mouse, size)

    painter.end()
    return pm


def build_combined_tray_icon(
    kb: DeviceBadgeState,
    mouse: DeviceBadgeState,
) -> QIcon:
    """Create a multi-resolution QIcon for sharp display at all Windows DPI scales."""
    icon = QIcon()
    for sz in (16, 20, 24, 32, 48, 64):
        icon.addPixmap(render_combined_pixmap(sz, kb, mouse))
    return icon


def build_app_icon() -> QIcon:
    """Create the static taskbar / window app icon (left bar green, right bar yellow)."""
    kb_demo = DeviceBadgeState(percent=82, charging=False, status=DeviceStatus.CONNECTED)
    mouse_demo = DeviceBadgeState(percent=30, charging=False, status=DeviceStatus.CONNECTED)
    icon = QIcon()
    for sz in (16, 20, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(render_combined_pixmap(sz, kb_demo, mouse_demo))
    return icon

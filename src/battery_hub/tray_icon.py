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
import os
from pathlib import Path
import struct
from typing import Optional

from PySide6.QtCore import QBuffer, QIODevice, QRectF, Qt
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

    # Track background (neutral charcoal)
    radius = max(1.5, body_rect.width() * 0.24)
    track_path = QPainterPath()
    track_path.addRoundedRect(body_rect, radius, radius)
    painter.fillPath(track_path, QColor("#242424"))

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
    outline_color = QColor("#4A4A4A") if is_disconnected else QColor(color)
    if not is_disconnected and state.status not in (DeviceStatus.CHARGING,) and (
        state.percent is None or state.percent > 30
    ):
        outline_color = QColor("#5A5A5A")
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

    # Neutral dark-grey rounded square backdrop
    margin = max(0.8, size * 0.03)
    bg_rect = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)
    bg_radius = size * 0.20
    bg_path = QPainterPath()
    bg_path.addRoundedRect(bg_rect, bg_radius, bg_radius)
    painter.fillPath(bg_path, QColor("#141414"))

    border_pen = QPen(QColor("#383838"), max(0.8, size * 0.035))
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


def write_app_ico(ico_path: Path) -> Path:
    """Write a standard multi-resolution PNG-backed Windows .ico file."""
    kb_demo = DeviceBadgeState(percent=82, charging=False, status=DeviceStatus.CONNECTED)
    mouse_demo = DeviceBadgeState(percent=30, charging=False, status=DeviceStatus.CONNECTED)
    sizes = (16, 24, 32, 48, 64, 128, 256)
    entries: list[tuple[int, bytes]] = []
    for sz in sizes:
        pm = render_combined_pixmap(sz, kb_demo, mouse_demo)
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        pm.save(buf, "PNG")
        entries.append((sz, bytes(buf.data())))
        buf.close()

    header = struct.pack("<HHH", 0, 1, len(entries))
    offset = 6 + 16 * len(entries)
    directory = bytearray()
    payload = bytearray()
    for sz, png in entries:
        dim = 0 if sz >= 256 else sz
        directory.extend(struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset))
        payload.extend(png)
        offset += len(png)

    ico_path.parent.mkdir(parents=True, exist_ok=True)
    ico_path.write_bytes(header + bytes(directory) + bytes(payload))
    return ico_path


def _set_window_property_store(hwnd: int, app_id: str, ico_path: Path, display_name: str) -> None:
    """Set PKEY_AppUserModel_ID and PKEY_AppUserModel_RelaunchIconResource on the HWND.

    Required on Windows 11 when running under Microsoft Store (MSIX) Python so the
    taskbar renders our .ico instead of the packaged pythonw.exe logo.
    """
    import ctypes
    from ctypes import POINTER, Structure, byref, c_ubyte, c_uint, c_ulong, c_ulonglong, c_ushort, c_void_p, c_wchar_p

    class GUID(Structure):
        _fields_ = [
            ("Data1", c_ulong),
            ("Data2", c_ushort),
            ("Data3", c_ushort),
            ("Data4", c_ubyte * 8),
        ]

    class PROPERTYKEY(Structure):
        _fields_ = [("fmtid", GUID), ("pid", c_ulong)]

    class PROPVARIANT(Structure):
        _fields_ = [
            ("vt", c_ushort),
            ("wReserved1", c_ushort),
            ("wReserved2", c_ushort),
            ("wReserved3", c_ushort),
            ("pwszVal", c_wchar_p),
            ("pad", c_ulonglong),
        ]

    iid_prop_store = GUID(
        0x886D8EEB, 0x8CF2, 0x4446, (c_ubyte * 8)(0x8D, 0x02, 0xCD, 0xBA, 0x1D, 0xBD, 0xCF, 0x99)
    )
    fmtid_aumid = GUID(
        0x9F4C2855, 0x9F79, 0x4B39, (c_ubyte * 8)(0xA8, 0xD0, 0xE1, 0xD4, 0x2D, 0xE1, 0xD5, 0xF3)
    )

    shell32 = ctypes.windll.shell32
    shell32.SHGetPropertyStoreForWindow.argtypes = [c_void_p, POINTER(GUID), POINTER(c_void_p)]
    shell32.SHGetPropertyStoreForWindow.restype = ctypes.c_long

    store_ptr = c_void_p()
    hr = shell32.SHGetPropertyStoreForWindow(c_void_p(hwnd), byref(iid_prop_store), byref(store_ptr))
    if hr != 0 or not store_ptr.value:
        return

    vtable = ctypes.cast(ctypes.cast(store_ptr, POINTER(c_void_p)).contents, POINTER(c_void_p))
    release_fn = ctypes.WINFUNCTYPE(c_ulong, c_void_p)(vtable[2])
    set_value_fn = ctypes.WINFUNCTYPE(
        ctypes.c_long, c_void_p, POINTER(PROPERTYKEY), POINTER(PROPVARIANT)
    )(vtable[6])
    commit_fn = ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p)(vtable[7])

    VT_LPWSTR = 31
    try:
        # Setting PKEY_AppUserModel_ID detaches the window from the MSIX Python
        # taskbar icon so Explorer renders the window's own WM_SETICON directly.
        pkey = PROPERTYKEY(fmtid_aumid, 5)  # PKEY_AppUserModel_ID
        pv = PROPVARIANT(VT_LPWSTR, 0, 0, 0, app_id, 0)
        set_value_fn(store_ptr, byref(pkey), byref(pv))
        commit_fn(store_ptr)
    finally:
        release_fn(store_ptr)


def apply_windows_taskbar_icon(
    hwnd: int,
    ico_path: Path,
    app_id: str = "PeripheralBatteryHub.Monitor",
    display_name: str = "Peripheral Battery Hub",
) -> None:
    """Explicitly set Win32 taskbar icon via PropertyStore, Class icon, and WM_SETICON."""
    if os.name != "nt" or not hwnd or not ico_path.exists():
        return
    try:
        _set_window_property_store(hwnd, app_id, ico_path, display_name)
    except Exception:
        pass
    try:
        import ctypes

        user32 = ctypes.windll.user32
        user32.LoadImageW.restype = ctypes.c_void_p
        user32.LoadImageW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_wchar_p,
            ctypes.c_uint,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        ]
        user32.SendMessageW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_size_t,
            ctypes.c_void_p,
        ]

        IMAGE_ICON = 1
        LR_LOADFROMFILE = 0x00000010
        WM_SETICON = 0x0080
        ICON_SMALL = 0
        ICON_BIG = 1
        GCLP_HICON = -14
        GCLP_HICONSM = -34

        h_big = user32.LoadImageW(None, str(ico_path), IMAGE_ICON, 48, 48, LR_LOADFROMFILE)
        h_small = user32.LoadImageW(None, str(ico_path), IMAGE_ICON, 16, 16, LR_LOADFROMFILE)

        set_class = getattr(user32, "SetClassLongPtrW", user32.SetClassLongW)
        set_class.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        set_class.restype = ctypes.c_void_p

        if h_big:
            set_class(ctypes.c_void_p(hwnd), GCLP_HICON, ctypes.c_void_p(h_big))
            user32.SendMessageW(ctypes.c_void_p(hwnd), WM_SETICON, ICON_BIG, ctypes.c_void_p(h_big))
        if h_small:
            set_class(ctypes.c_void_p(hwnd), GCLP_HICONSM, ctypes.c_void_p(h_small))
            user32.SendMessageW(ctypes.c_void_p(hwnd), WM_SETICON, ICON_SMALL, ctypes.c_void_p(h_small))
    except Exception:
        pass

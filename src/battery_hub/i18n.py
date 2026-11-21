"""English (default) and German translations for Peripheral Battery Hub."""

from __future__ import annotations

from typing import Optional

SUPPORTED_LANGUAGES: list[tuple[str, str]] = [
    ("English", "en"),
    ("Deutsch", "de"),
]

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "subtitle": "AULA F75 (Keyboard) • Attack Shark X11 (Mouse)",
        "refresh": "Refresh",
        "kb_sub": "Keyboard • VID {vid:04X}:{pid:04X}",
        "mouse_sub": "Mouse • VID {vid:04X}:{pid:04X}",
        "searching": "Searching…",
        "stat_connection": "Connection",
        "stat_status": "Status",
        "stat_remaining": "Estimated runtime",
        "stat_updated": "Last updated",
        "collecting": "Collecting data…",
        "never_measured": "Not measured yet",
        "just_now": "Just now",
        "ago_sec": "{n}s ago",
        "ago_min": "{n}m ago",
        "ago_hour": "{n}h ago",
        "ago_day": "{n}d ago",
        "rem_days": "~{d:.1f} days",
        "rem_hm": "~{h}h {m:02d}m",
        "rem_m": "~{m}m",
        "chart_title": "Battery History",
        "legend_kb": "● Keyboard",
        "legend_mouse": "● Mouse",
        "filter_both": "Both",
        "filter_kb": "Keyboard",
        "filter_mouse": "Mouse",
        "range_all": "All",
        "chart_empty": "History will be recorded once readings arrive…",
        "autostart": "Start with Windows",
        "alerts": "Alerts (15 / 5 %)",
        "poll_interval": "Polling:",
        "lang_label": "Language:",
        "iv_15": "15s",
        "iv_30": "30s",
        "iv_60": "60s",
        "iv_300": "5m",
        "tray_open": "Open Dashboard",
        "tray_refresh": "Refresh now",
        "tray_quit": "Quit",
        "tray_loading": "Loading…",
        "pill_charging": "⚡ Charging",
        "pill_active": "● 2.4 GHz active",
        "pill_sleeping": "☾ Sleep mode",
        "pill_waiting": "◌ Waiting for signal",
        "pill_disconnected": "○ Disconnected",
        "pill_error": "⚠ HID error",
        "gauge_charging": "Charging",
        "gauge_battery": "On battery",
        "gauge_sleeping": "Sleep mode",
        "gauge_press_key": "Press a key…",
        "gauge_move_mouse": "Move mouse…",
        "gauge_standby": "Standby",
        "gauge_no_dongle": "No dongle",
        "gauge_error": "Error",
        "power_charging": "Charging",
        "power_battery": "On battery (wireless)",
        "power_sleeping": "In sleep mode",
        "power_waiting": "Waiting for battery report",
        "conn_kb_charging": "2.4 GHz + USB (charging)",
        "conn_kb_active": "2.4 GHz dongle (active)",
        "conn_kb_standby": "2.4 GHz dongle (standby)",
        "conn_mouse_charging": "USB cable (charging)",
        "conn_mouse_active": "2.4 GHz dongle (active)",
        "conn_mouse_waiting": "2.4 GHz dongle (waiting)",
        "conn_disconnected": "Not connected",
        "conn_error": "Connection error",
        "tray_charging_pct": "{prefix}: {pct}% (Charging)",
        "tray_charging_usb": "{prefix}: Charging (USB)",
        "tray_active_pct": "{prefix}: {pct}% (2.4 GHz)",
        "tray_standby_pct": "{prefix}: {pct}% (Standby)",
        "tray_sleeping": "{prefix}: Sleep mode",
        "tray_waiting": "{prefix}: Waiting for signal",
        "tray_disconnected": "{prefix}: Disconnected",
        "tray_error": "{prefix}: Read error",
        "alert_title": "{name} battery low",
        "alert_body": "Battery level is down to {pct}%.",
        "name_kb": "AULA F75 (Keyboard)",
        "name_mouse": "Attack Shark X11 (Mouse)",
    },
    "de": {
        "subtitle": "AULA F75 (Tastatur) • Attack Shark X11 (Maus)",
        "refresh": "Aktualisieren",
        "kb_sub": "Tastatur • VID {vid:04X}:{pid:04X}",
        "mouse_sub": "Maus • VID {vid:04X}:{pid:04X}",
        "searching": "Suche…",
        "stat_connection": "Verbindung",
        "stat_status": "Status",
        "stat_remaining": "Geschätzte Restzeit",
        "stat_updated": "Zuletzt aktualisiert",
        "collecting": "Sammle Daten…",
        "never_measured": "Noch nicht gemessen",
        "just_now": "Gerade eben",
        "ago_sec": "Vor {n} Sek.",
        "ago_min": "Vor {n} Min.",
        "ago_hour": "Vor {n} Std.",
        "ago_day": "Vor {n} T.",
        "rem_days": "~{d:.1f} Tage",
        "rem_hm": "~{h} Std. {m:02d} Min.",
        "rem_m": "~{m} Min.",
        "chart_title": "Akku-Verlauf",
        "legend_kb": "● Tastatur",
        "legend_mouse": "● Maus",
        "filter_both": "Beide",
        "filter_kb": "Tastatur",
        "filter_mouse": "Maus",
        "range_all": "Alle",
        "chart_empty": "Verlauf wird aufgezeichnet, sobald Messwerte vorliegen…",
        "autostart": "Mit Windows starten",
        "alerts": "Warnung (15 / 5 %)",
        "poll_interval": "Abfrage:",
        "lang_label": "Sprache:",
        "iv_15": "15 Sek.",
        "iv_30": "30 Sek.",
        "iv_60": "60 Sek.",
        "iv_300": "5 Min.",
        "tray_open": "Dashboard öffnen",
        "tray_refresh": "Jetzt aktualisieren",
        "tray_quit": "Beenden",
        "tray_loading": "Lade…",
        "pill_charging": "⚡ Lädt",
        "pill_active": "● 2,4 GHz aktiv",
        "pill_sleeping": "☾ Schlafmodus",
        "pill_waiting": "◌ Warte auf Signal",
        "pill_disconnected": "○ Getrennt",
        "pill_error": "⚠ HID-Fehler",
        "gauge_charging": "Wird geladen",
        "gauge_battery": "Akkubetrieb",
        "gauge_sleeping": "Schlafmodus",
        "gauge_press_key": "Taste drücken…",
        "gauge_move_mouse": "Maus bewegen…",
        "gauge_standby": "Standby",
        "gauge_no_dongle": "Kein Dongle",
        "gauge_error": "Fehler",
        "power_charging": "Wird geladen",
        "power_battery": "Akkubetrieb (kabellos)",
        "power_sleeping": "Im Schlafmodus",
        "power_waiting": "Warte auf Akku-Report",
        "conn_kb_charging": "2,4 GHz + USB (lädt)",
        "conn_kb_active": "2,4 GHz Dongle (aktiv)",
        "conn_kb_standby": "2,4 GHz Dongle (Standby)",
        "conn_mouse_charging": "USB-Kabel (lädt)",
        "conn_mouse_active": "2,4 GHz Dongle (aktiv)",
        "conn_mouse_waiting": "2,4 GHz Dongle (warte auf Signal)",
        "conn_disconnected": "Nicht verbunden",
        "conn_error": "Verbindungsfehler",
        "tray_charging_pct": "{prefix}: {pct}% (Lädt)",
        "tray_charging_usb": "{prefix}: Lädt (USB)",
        "tray_active_pct": "{prefix}: {pct}% (2,4 GHz)",
        "tray_standby_pct": "{prefix}: {pct}% (Standby)",
        "tray_sleeping": "{prefix}: Schlafmodus",
        "tray_waiting": "{prefix}: Warte auf Signal",
        "tray_disconnected": "{prefix}: Getrennt",
        "tray_error": "{prefix}: Lesefehler",
        "alert_title": "{name} Akku niedrig",
        "alert_body": "Der Akkustand beträgt noch {pct}%.",
        "name_kb": "AULA F75 (Tastatur)",
        "name_mouse": "Attack Shark X11 (Maus)",
    },
}


def tr(lang: str, key: str, **kwargs) -> str:
    table = STRINGS.get(lang, STRINGS["en"])
    template = table.get(key, STRINGS["en"].get(key, key))
    return template.format(**kwargs) if kwargs else template


def format_age(ts: Optional[float], lang: str, now: Optional[float] = None) -> str:
    if not ts:
        return tr(lang, "never_measured")
    import time

    ref = time.time() if now is None else now
    diff = max(0, int(ref - ts))
    if diff < 10:
        return tr(lang, "just_now")
    if diff < 60:
        return tr(lang, "ago_sec", n=diff)
    mins = diff // 60
    if mins < 60:
        return tr(lang, "ago_min", n=mins)
    hours = mins // 60
    if hours < 24:
        return tr(lang, "ago_hour", n=hours)
    return tr(lang, "ago_day", n=hours // 24)


def format_remaining(hours: Optional[float], lang: str) -> str:
    if hours is None:
        return tr(lang, "collecting")
    if hours >= 48:
        return tr(lang, "rem_days", d=hours / 24.0)
    if hours >= 1:
        h = int(hours)
        m = int(round((hours - h) * 60))
        if m == 60:
            h += 1
            m = 0
        return tr(lang, "rem_hm", h=h, m=m)
    return tr(lang, "rem_m", m=max(1, int(round(hours * 60))))

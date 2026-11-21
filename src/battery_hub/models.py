"""Shared data models for Peripheral Battery Hub."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class DeviceId(str, Enum):
    KEYBOARD = "keyboard"
    MOUSE = "mouse"


class DeviceStatus(str, Enum):
    CONNECTED = "connected"
    CHARGING = "charging"
    SLEEPING = "sleeping"
    WAITING = "waiting"
    DISCONNECTED = "disconnected"
    ERROR = "error"


@dataclass(frozen=True)
class BatteryReading:
    device_id: DeviceId
    status: DeviceStatus
    percent: Optional[int] = None
    charging: Optional[bool] = None
    connection_label: str = ""
    raw_hex: str = ""
    error_message: str = ""
    timestamp: float = 0.0


@dataclass(frozen=True)
class HistoryPoint:
    timestamp: float
    percent: int
    charging: bool

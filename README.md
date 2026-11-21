# Peripheral Battery Hub (AULA F75 & Attack Shark X11)

Unified Windows system tray and desktop dashboard for monitoring the battery level of both wireless peripherals in **one** tray icon and **one** window:

- **⌨ AULA F75** — 2.4 GHz Compx wireless receiver (`VID 0x3554`, `PID 0xFA09`)
- **🖱 Attack Shark X11** — 2.4 GHz wireless adapter (`VID 0x1D57`, `PID 0xFA60`) & USB charging mode (`PID 0xFA55`)

## Features

- **Dual Vertical-Bar Tray Icon**: Two vertical battery bars side by side (left = keyboard, right = mouse), dynamically colored per device:
  - **> 30%**: Green
  - **≤ 30%**: Yellow
  - **≤ 15%**: Red
  - **Charging**: Blue
  - Hovering over the tray icon shows exact percentages and connection states for both devices.
- **Unified Dashboard**: Side-by-side battery gauges, connection status, estimated remaining runtime, and last-updated timestamps.
- **Combined Battery History Chart**: Tracks both devices over time (`1h`, `6h`, `24h`, `7d`, `All`) with a device filter (`Both`, `Keyboard`, `Mouse`).
- **Low-Battery Alerts (15% / 5%)**, **Windows Autostart**, **Configurable Polling Interval**, and **English / German UI** (English by default).

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
```

## Usage

- Double-click `start_battery_monitor.bat` or `start_battery_monitor.vbs` to launch without a console window.
- Or run from the terminal:
  ```powershell
  .\.venv\Scripts\python.exe peripheral_battery.py
  .\.venv\Scripts\python.exe peripheral_battery.py --once --debug
  .\.venv\Scripts\python.exe peripheral_battery.py --minimized
  ```

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

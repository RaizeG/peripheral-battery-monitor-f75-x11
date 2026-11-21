@echo off
setlocal
set "BASE=%~dp0"
if exist "%BASE%.venv\Scripts\pythonw.exe" (
    start "" "%BASE%.venv\Scripts\pythonw.exe" "%BASE%peripheral_battery.py" %*
) else if exist "%BASE%..\aula-f75-battery\.venv\Scripts\pythonw.exe" (
    start "" "%BASE%..\aula-f75-battery\.venv\Scripts\pythonw.exe" "%BASE%peripheral_battery.py" %*
) else (
    start "" pythonw.exe "%BASE%peripheral_battery.py" %*
)

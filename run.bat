@echo off
py main.py
if errorlevel 1 (
    python main.py
)
pause

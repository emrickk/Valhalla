@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel% equ 0 (
  py -3 clean_phone.py
) else (
  python clean_phone.py
)
pause

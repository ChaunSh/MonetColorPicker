@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv
    if errorlevel 1 goto fail
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m pip install pyinstaller
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed --name WallpaperMonetADB --collect-all materialyoucolor main.py
if errorlevel 1 goto fail
echo EXE generated at dist\WallpaperMonetADB.exe
pause
exit /b 0
:fail
pause
exit /b 1

@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
if errorlevel 1 (
    echo.
    echo Installation failed. Review the error message above.
    pause
    exit /b 1
)
echo.
echo Installation complete. Launch Frame Extractor from the desktop shortcut.
pause
endlocal

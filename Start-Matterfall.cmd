@echo off
rem Matterfall - opens the launcher (no console window).
cd /d "%~dp0"
if exist "Matterfall Launcher.exe" (
    start "" "Matterfall Launcher.exe"
) else (
    start "" pythonw "launcher\matterfall_launcher.pyw"
)

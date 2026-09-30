@echo off
setlocal
title Disinstallazione TIFF Viewer
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall-windows.ps1"
if errorlevel 1 (
    echo.
    echo Disinstallazione non riuscita. Leggi il messaggio di errore qui sopra.
)
echo.
pause


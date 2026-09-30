@echo off
setlocal
title Installazione TIFF Viewer
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-windows.ps1"
if errorlevel 1 (
    echo.
    echo Installazione non riuscita. Leggi il messaggio di errore qui sopra.
) else (
    echo.
    echo TIFF Viewer e pronto.
)
echo.
pause


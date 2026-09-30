@echo off
setlocal
set "LAUNCHER=%~dp0.venv-windows\Scripts\tiff-viewer.exe"
if not exist "%LAUNCHER%" (
    echo TIFF Viewer non e ancora installato.
    echo Esegui prima install-windows.bat.
    pause
    exit /b 1
)
start "" "%LAUNCHER%" %*


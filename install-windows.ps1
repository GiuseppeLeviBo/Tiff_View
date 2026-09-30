param(
    [switch]$NoShortcuts,
    [switch]$NoRegistration
)

$ErrorActionPreference = "Stop"
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = Join-Path $AppDir ".venv-windows"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$Launcher = Join-Path $VenvDir "Scripts\tiff-viewer.exe"

function Invoke-SystemPython {
    param([string[]]$PythonArguments)

    $PyLauncher = Get-Command "py.exe" -ErrorAction SilentlyContinue
    if ($PyLauncher) {
        & $PyLauncher.Source -3 @PythonArguments
        return
    }

    $Python = Get-Command "python.exe" -ErrorAction SilentlyContinue
    if ($Python) {
        & $Python.Source @PythonArguments
        return
    }

    throw "Python 3 non trovato. Installalo da https://www.python.org/downloads/windows/ e riprova."
}

function New-Shortcut {
    param(
        [string]$Path,
        [string]$Target
    )

    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($Path)
    $Shortcut.TargetPath = $Target
    $Shortcut.WorkingDirectory = $AppDir
    $Shortcut.Description = "Visualizzatore scientifico per immagini TIFF"
    $Shortcut.IconLocation = "$Target,0"
    $Shortcut.Save()
}

Write-Host "TIFF Viewer - installazione per Windows" -ForegroundColor Cyan
Write-Host "Cartella applicazione: $AppDir"
Write-Host

Write-Host "1/4 - Creo l'ambiente Python isolato..."
Invoke-SystemPython -PythonArguments @("-m", "venv", $VenvDir)

if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw "Creazione dell'ambiente Python non riuscita."
}

Write-Host "2/4 - Installo TIFF Viewer e le dipendenze..."
& $VenvPython -m pip install $AppDir
if ($LASTEXITCODE -ne 0) {
    throw "Installazione delle dipendenze non riuscita. Controlla la connessione Internet."
}

Write-Host "3/4 - Verifico l'installazione..."
& $VenvPython -c "import tkinter, numpy, PIL, tifffile, tiff_viewer; print('Componenti verificati.')"
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $Launcher)) {
    throw "La verifica finale non e riuscita."
}

if (-not $NoShortcuts) {
    Write-Host "4/4 - Creo i collegamenti..."
    $Desktop = [Environment]::GetFolderPath("Desktop")
    $StartMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
    New-Shortcut -Path (Join-Path $Desktop "TIFF Viewer.lnk") -Target $Launcher
    New-Shortcut -Path (Join-Path $StartMenu "TIFF Viewer.lnk") -Target $Launcher
} else {
    Write-Host "4/4 - Collegamenti non richiesti."
}

if (-not $NoRegistration) {
    foreach ($Extension in @(".tif", ".tiff")) {
        $MenuKey = "HKCU:\Software\Classes\SystemFileAssociations\$Extension\shell\TIFFViewer"
        $CommandKey = Join-Path $MenuKey "command"
        New-Item -Path $CommandKey -Force | Out-Null
        Set-Item -Path $MenuKey -Value "Apri con TIFF Viewer"
        Set-ItemProperty -Path $MenuKey -Name "Icon" -Value $Launcher
        Set-Item -Path $CommandKey -Value ('"{0}" "%1"' -f $Launcher)
    }
}

Write-Host
Write-Host "Installazione completata." -ForegroundColor Green
Write-Host "Puoi avviare TIFF Viewer dal Desktop, dal menu Start o facendo clic destro su un TIFF."


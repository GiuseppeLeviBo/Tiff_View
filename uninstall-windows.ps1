param(
    [switch]$KeepEnvironment,
    [switch]$NoShortcuts,
    [switch]$NoRegistration
)

$ErrorActionPreference = "Stop"
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = Join-Path $AppDir ".venv-windows"
$DesktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "TIFF Viewer.lnk"
$StartShortcut = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\TIFF Viewer.lnk"

if (-not $NoShortcuts) {
    foreach ($Shortcut in @($DesktopShortcut, $StartShortcut)) {
        if (Test-Path -LiteralPath $Shortcut) {
            Remove-Item -LiteralPath $Shortcut -Force
        }
    }
}

if (-not $NoRegistration) {
    foreach ($Extension in @(".tif", ".tiff")) {
        $MenuKey = "HKCU:\Software\Classes\SystemFileAssociations\$Extension\shell\TIFFViewer"
        if (Test-Path -LiteralPath $MenuKey) {
            Remove-Item -LiteralPath $MenuKey -Recurse -Force
        }
    }
}

if (-not $KeepEnvironment -and (Test-Path -LiteralPath $VenvDir)) {
    $ResolvedApp = (Resolve-Path -LiteralPath $AppDir).Path
    $ResolvedVenv = (Resolve-Path -LiteralPath $VenvDir).Path
    if (-not $ResolvedVenv.StartsWith($ResolvedApp + "\", [StringComparison]::OrdinalIgnoreCase)) {
        throw "Percorso dell'ambiente non sicuro: $ResolvedVenv"
    }
    Remove-Item -LiteralPath $ResolvedVenv -Recurse -Force
}

Write-Host "TIFF Viewer e stato disinstallato." -ForegroundColor Green


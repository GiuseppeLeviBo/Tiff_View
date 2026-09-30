#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$APP_DIR/.venv"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Errore: Python 3 non è installato."
    exit 1
fi

if ! python3 -c 'import tkinter' >/dev/null 2>&1; then
    echo "Manca Tkinter. Installalo con uno di questi comandi:"
    echo "  Ubuntu/Debian: sudo apt install python3-tk"
    echo "  Fedora:        sudo dnf install python3-tkinter"
    echo "  Arch Linux:    sudo pacman -S tk"
    exit 1
fi

echo "Creo l'ambiente Python…"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install "$APP_DIR"

mkdir -p "$BIN_DIR" "$DESKTOP_DIR"
cat > "$BIN_DIR/tiff-viewer" <<EOF
#!/usr/bin/env bash
exec "$VENV_DIR/bin/tiff-viewer" "\$@"
EOF
chmod +x "$BIN_DIR/tiff-viewer"

cat > "$DESKTOP_DIR/tiff-viewer.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=TIFF Viewer
Comment=Visualizza immagini TIFF scientifiche
Exec=$BIN_DIR/tiff-viewer %f
Terminal=false
Categories=Graphics;Viewer;
MimeType=image/tiff;
StartupNotify=true
EOF

echo
echo "Installazione completata."
echo "Apri 'TIFF Viewer' dal menu applicazioni oppure esegui:"
echo "  $BIN_DIR/tiff-viewer immagine.tif"


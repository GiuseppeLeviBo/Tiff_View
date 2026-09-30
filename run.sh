#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -x "$APP_DIR/.venv/bin/python" ]]; then
    echo "Applicazione non ancora installata. Esegui prima: ./install.sh"
    exit 1
fi

exec "$APP_DIR/.venv/bin/python" -m tiff_viewer "$@"


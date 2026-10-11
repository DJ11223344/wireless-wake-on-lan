#!/bin/sh
# Install or upgrade wwol. Run from the project directory as root:
#   sudo sh install.sh
set -eu

# WWOL_APP_DIR is only for tests; wwol.service expects /opt/wwol.
APP_DIR=${WWOL_APP_DIR:-/opt/wwol}
SERVICE_FILE=/etc/systemd/system/wwol.service
SRC_DIR=$(cd "$(dirname "$0")" && pwd -P)

# Installing replaces $APP_DIR/wwol, which would delete the source itself.
if [ -d "$APP_DIR" ] && [ "$(cd "$APP_DIR" && pwd -P)" = "$SRC_DIR" ]; then
    echo "Clone or copy wwol somewhere else (e.g. ~/wwol), not into $APP_DIR." >&2
    exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
    echo "Please run as root: sudo sh install.sh" >&2
    exit 1
fi

missing=""
command -v python3 >/dev/null 2>&1 || missing="$missing python3"
command -v ping >/dev/null 2>&1 || missing="$missing iputils-ping"
if [ -n "$missing" ]; then
    echo "Missing packages:$missing" >&2
    echo "Install them with: apt update && apt install -y$missing" >&2
    exit 1
fi

if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 7))'; then
    echo "wwol needs Python 3.7 or newer (found $(python3 --version 2>&1))" >&2
    exit 1
fi

if ! id wwol >/dev/null 2>&1; then
    useradd --system --user-group --no-create-home --shell /usr/sbin/nologin wwol
    echo "Created system user wwol"
fi

mkdir -p "$APP_DIR"
rm -rf "$APP_DIR/wwol" "$APP_DIR/static"
cp -r "$SRC_DIR/wwol" "$SRC_DIR/static" "$SRC_DIR/config.example.json" "$APP_DIR/"

new_config=0
if [ ! -f "$APP_DIR/config.json" ]; then
    cp "$APP_DIR/config.example.json" "$APP_DIR/config.json"
    new_config=1
fi

chown -R root:wwol "$APP_DIR"
chmod -R u=rwX,g=rX,o= "$APP_DIR"

install -m 644 "$SRC_DIR/wwol.service" "$SERVICE_FILE"
systemctl daemon-reload
systemctl enable wwol
systemctl restart wwol

echo
if [ "$new_config" -eq 1 ]; then
    echo "Created $APP_DIR/config.json from the example. Edit it with your PCs:"
    echo "  nano $APP_DIR/config.json"
    echo "then restart: systemctl restart wwol"
    echo
fi
echo "wwol is running. Open one of these in a browser (port 8080 unless changed in config.json):"
for ip in $(hostname -I 2>/dev/null || true); do
    echo "  http://$ip:8080"
done

#!/usr/bin/env bash
# 24-Hour Analog Screentime Clock Launcher Script
# Sets library search path for Qt platform xcb cursor plugins and executes within project venv.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$SCRIPT_DIR/lib/usr/lib/x86_64-linux-gnu"

if [ -d "$LIB_DIR" ]; then
    export LD_LIBRARY_PATH="$LIB_DIR:${LD_LIBRARY_PATH:-}"
fi

export DISPLAY="${DISPLAY:-:0.0}"
export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"

# If started early by systemd at boot, wait briefly for X11 to accept connections
RETRIES=0
while ! xset q >/dev/null 2>&1; do
    sleep 1
    RETRIES=$((RETRIES + 1))
    if [ "$RETRIES" -ge 20 ]; then
        echo "Notice: X11 DISPLAY $DISPLAY not ready after 20s, attempting start anyway..."
        break
    fi
done

# Single-instance lock protection to guarantee only one widget instance can ever run
LOCK_FILE="${XDG_RUNTIME_DIR:-/tmp}/screentime-clock.lock"
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    echo "24H Screentime Clock is already running. Exiting cleanly."
    exit 0
fi

exec "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/main.py" "$@"

#!/bin/bash
# Start the MS-Project-2025 Flask server + LAN proxy in one shot.
#
# Usage:  ./start_lan.sh            (start both servers)
#         ./start_lan.sh stop       (stop both)
#         ./start_lan.sh status     (show listeners + quick health check)
#
# Why /usr/bin/python3 for the proxy: this Mac's macOS Application Firewall
# BLOCKS incoming connections for the venv's uv-installed python3.11 binary
# (see ~/.local/share/uv/python/.../bin/python3.11). lan_proxy.py is pure
# stdlib, so it runs fine on the firewall-permitted /usr/bin/python3 (3.9.6).
# Flask stays on the venv python because it only binds 127.0.0.1 (loopback
# is never blocked by the firewall).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
FLASK_CMD="$ROOT/.venv/bin/python $ROOT/app.py"
PROXY_CMD="/usr/bin/python3 $ROOT/scripts/lan_proxy.py"
HOST_IP="$(ipconfig getifaddr en1 2>/dev/null || ipconfig getifaddr en0 2>/dev/null || echo '?')"

start() {
  echo "Starting Flask (127.0.0.1:8080)..."
  ( $FLASK_CMD >>"$ROOT/lan_server.log" 2>&1 & )
  echo "Starting LAN proxy (0.0.0.0:8081)..."
  ( $PROXY_CMD >>"$ROOT/lan_server.log" 2>&1 & )
  sleep 3
  echo "Done. Open on your iPhone:"
  echo "    http://${HOST_IP}:8081"
}

stop() {
  pkill -f "$ROOT/app.py" 2>/dev/null && echo "Stopped Flask" || echo "Flask not running"
  pkill -f 'scripts/lan_proxy.py' 2>/dev/null && echo "Stopped proxy" || echo "Proxy not running"
}

status() {
  echo "== Listeners =="
  lsof -iTCP -sTCP:LISTEN -P -n 2>/dev/null | grep -E ':8080|:8081' || echo "none"
  echo "== Health =="
  curl -s -o /dev/null -w "Flask  127.0.0.1:8080  HTTP %{http_code}\n" http://127.0.0.1:8080/ || echo "Flask down"
  curl -s -o /dev/null -w "Proxy  ${HOST_IP}:8081  HTTP %{http_code}\n" --connect-timeout 6 "http://${HOST_IP}:8081/" || echo "Proxy down"
}

case "${1:-start}" in
  start)  start ;;
  stop)   stop ;;
  status) status ;;
  *) echo "Usage: $0 [start|stop|status]"; exit 1 ;;
esac

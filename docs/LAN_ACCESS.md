# Access the App from Another Device (LAN / Phone)

Serve the Flask medical-screening app on `http://<LAN-IP>:8081` so you can
open it in a browser from a phone or another computer on the same Wi‑Fi / LAN.

## Quick start

```bash
cd /Users/hxu/VS-Code-Workspace/MS-Project-2025
./start_lan.sh start     # starts Flask(127.0.0.1:8080) + LAN proxy(*:8081)
./start_lan.sh status    # listeners + health check, prints http://<LAN-IP>:8081
./start_lan.sh stop      # stops both
```

Open the printed URL from the other device, e.g. `http://192.168.1.94:8081`.
The other device must be on the same network. This is plain HTTP, so keep it
LAN-only.

## Why there is a proxy (the core gotcha)

This project's dev machine is a managed Mac whose **Application Firewall
BLOCKS incoming connections for the venv's uv-installed python**
(`~/.local/share/uv/python/cpython-3.11.x-.../bin/python3.11`). Symptoms:

- The proxy itself listens on `*:8081` (all interfaces) fine.
- Loopback (`127.0.0.1:8081`) returns 200 — so it looks like it works.
- But LAN clients get `HTTP 000` / connection reset: the firewall lets the TCP
  handshake complete, then RSTs it. The proxy log shows the LAN connection
  arriving then dying with `OSError: [Errno 57] Socket is not connected`.
- `socketfilterfw --getappblocked <binary>` reports **blocked** for the uv
  python3.11, but **permitted** for `/usr/bin/python3` (3.9.6).

**Fix:** `scripts/lan_proxy.py` is pure stdlib (`http.server` + `urllib`), so it
runs under the firewall-permitted `/usr/bin/python3`. Flask stays on the venv
python because it only binds `127.0.0.1` (loopback is never firewall-blocked).

## Manual fallback (no script)

```bash
cd /Users/hxu/VS-Code-Workspace/MS-Project-2025
# Flask (venv python, loopback only):
.venv/bin/python app.py &
# LAN proxy (STDLIB interpreter the firewall permits — REQUIRED):
/usr/bin/python3 scripts/lan_proxy.py &
```

## Gotchas

- **Never run the proxy under the venv python** — it will be firewall-blocked
  on LAN even though loopback works. This is the #1 trap.
- Launch `lan_proxy.py` from the project root (keeps relative paths sane).
- The host IP is DHCP. If the other device cannot connect later, re-check the
  LAN IP with `ipconfig getifaddr en0` (or `en1`) — it may have changed.

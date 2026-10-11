# wwol — Raspberry Pi Wake-on-LAN Web App: Design

Date: 2026-10-11

## Goal

A lightweight web app that runs on a Raspberry Pi (3B on Raspberry Pi OS, Zero on DietPi
with a USB-Ethernet adapter) and lets anyone on the home LAN wake configured PCs from a
browser (phone or desktop), and see whether each PC is currently online.

### Success criteria

- Opening `http://<pi-ip>:8080` shows every configured PC with an online/offline status
  and a **Wake Up** button.
- Pressing **Wake Up** sends a WoL magic packet and the PC powers on (given WoL is enabled
  on the PC).
- Runs on Pi Zero (ARMv6) and Pi 3B with only `python3` and `iputils-ping` installed — no
  pip packages, no Node, no build step.
- Starts automatically on boot via systemd.
- README lets a user go from a fresh DietPi / Raspberry Pi OS install to a working app.

### Non-goals

- Authentication (trusted home LAN only; never port-forward).
- Access from outside the LAN.
- Editing devices from the web UI (devices are defined in `config.json`).
- Shutdown/sleep, LUKS unlock, or anything beyond wake + status.

## Constraints

- Python 3.7+ standard library only (`http.server.ThreadingHTTPServer`, `socket`,
  `subprocess`, `json`, `concurrent.futures`).
- Low memory footprint (target < 20 MB RSS on Pi Zero).
- Frontend is one static HTML file with inline CSS and JS; no external assets/CDNs.

## Architecture

```
wwol/
  wwol/
    __init__.py
    config.py        # load + validate config.json -> Config / Device objects
    wol.py           # build magic packet; send via UDP broadcast
    status.py        # ping a host; check many hosts concurrently
    server.py        # HTTP server: static page + JSON API; entry point
  static/
    index.html       # UI: markup + inline CSS + inline JS
  config.example.json
  wwol.service       # systemd unit
  install.sh         # installer for the Pi
  tests/
    test_config.py
    test_wol.py
    test_status.py
    test_server.py
  README.md
```

Each module has one job and no dependency on the others except `server.py`, which wires
them together.

### `config.py`

- `load_config(path) -> Config`. Raises `ConfigError` with a human-readable message on any
  problem (missing file, invalid JSON, missing/invalid field).
- Config file format:

  ```json
  {
    "host": "0.0.0.0",
    "port": 8080,
    "broadcast": "192.168.1.255",
    "devices": [
      { "name": "Gaming PC", "mac": "AA:BB:CC:DD:EE:FF", "ip": "192.168.1.50" },
      { "name": "Media PC",  "mac": "11-22-33-44-55-66", "broadcast": "192.168.2.255", "wol_port": 7 }
    ]
  }
  ```

- Fields:
  | Field | Required | Default | Notes |
  |---|---|---|---|
  | `host` | no | `"0.0.0.0"` | Interface the web server binds to |
  | `port` | no | `8080` | Web server port, 1–65535 |
  | `broadcast` | yes | — | Default subnet broadcast address for all devices, e.g. `192.168.1.255` |
  | `devices` | yes | — | Non-empty list |
  | `devices[].name` | yes | — | Non-empty string |
  | `devices[].mac` | yes | — | 12 hex digits, separators `:`, `-`, `.` or none; normalised to `AA:BB:CC:DD:EE:FF` |
  | `devices[].ip` | no | none | If absent, status is `unknown` |
  | `devices[].broadcast` | no | top-level `broadcast` | Per-device override |
  | `devices[].wol_port` | no | `9` | UDP port for magic packet |

- IP and broadcast values are validated with `ipaddress.IPv4Address`.
- The subnet broadcast (not `255.255.255.255`) is used so the packet leaves via the correct
  interface on Pis with multiple interfaces (Wi-Fi + Ethernet, or USB Ethernet).

### `wol.py`

- `build_magic_packet(mac: str) -> bytes`: `b"\xff" * 6 + mac_bytes * 16` (102 bytes).
- `send_magic_packet(mac, broadcast, port=9)`: UDP socket with `SO_BROADCAST`, sends packet
  to `(broadcast, port)`. Lets `OSError` propagate.

### `status.py`

- `is_online(ip, timeout=1) -> bool`: runs `ping -c 1 -W <timeout> <ip>` via `subprocess`
  (no shell), returns True on exit code 0. Returns False on any failure (non-zero exit,
  `FileNotFoundError`, subprocess timeout of `timeout + 1` s).
- `check_all(ips) -> dict[ip, bool]`: runs `is_online` concurrently with a
  `ThreadPoolExecutor` (max 8 workers) so total time ≈ 1 s regardless of device count.

### `server.py`

- Entry point: `python3 -m wwol.server [--config PATH]`. Default config path:
  `config.json` in the project root (parent of the `wwol` package).
- On startup: load config; on `ConfigError` print message to stderr and exit code 1.
  Log `Listening on http://host:port` to stdout (journald captures it).
- `ThreadingHTTPServer` with a `BaseHTTPRequestHandler` subclass.
- Routes:

  | Method & path | Response |
  |---|---|
  | `GET /` | `static/index.html`, `text/html; charset=utf-8` |
  | `GET /api/devices` | `200` JSON `[{"id": 0, "name": "...", "mac": "...", "ip": "..."|null, "status": "online"|"offline"|"unknown"}]` |
  | `POST /api/wake/<id>` | `200 {"ok": true}`; `404 {"ok": false, "error": "Unknown device"}` for bad/out-of-range id; `500 {"ok": false, "error": "<OSError message>"}` if send fails |
  | anything else | `404` (JSON for `/api/*`, plain text otherwise); wrong method on a known path → `405` |

- `id` is the device's index in `config.json`.
- Each wake is logged: `Sent magic packet to <name> (<mac>) via <broadcast>:<port>`.
- Default request logging is kept (goes to journald).

### `static/index.html`

Single page, inline `<style>` and `<script>`, `<meta name="viewport">` for mobile.

**Behaviour**
- On load and every 10 s: `GET /api/devices`, render one row per device.
- Row: device name, status pill, **Wake Up** button. Device names inserted with
  `textContent` (no HTML injection).
- Clicking **Wake Up**: `POST /api/wake/<id>`. On success the button is disabled with text
  `Waking…` and the pill shows `waking` (pending style) until the device reports `online`
  or 120 s pass (then the button re-enables). On error, an inline error message is shown
  under the row with the server's `error` text.
- If `/api/devices` fails, show a banner "Can't reach the Pi" and keep retrying.

**Styles** (ported from `remote-wake-on-lan`, kept minimal ~40 lines):
- `body`: background `#F0EBD8`, text `#0D1321`, font
  `'Trebuchet MS', 'Lucida Sans Unicode', 'Lucida Grande', 'Lucida Sans', Arial, sans-serif`,
  `letter-spacing: 0.05rem`, margin 0.
- Content column: `max-width: 40rem; margin: 0 auto; padding: 1rem` (replaces the old
  `margin: 1rem 20rem`, which breaks on phones).
- `button`: background `#3e5c76`, text `#F0EBD8`, `3px solid #1d2d44` border, `5px`
  radius, `0.25rem` padding, uppercase, bold, `letter-spacing: 0.1rem`. Disabled:
  `opacity: 0.7; cursor: not-allowed`.
- Status pill: `padding: 0.1rem 1rem; border-radius: 1rem; border: 3px solid transparent`.
  `.online` green bg / cream text, `.pending` yellow bg, `.offline` red bg / cream text,
  `.unknown` `3px solid black` border.
- Device rows: flex, `align-items: center`, `flex-wrap: wrap`, gap `1rem`; separated by the
  `.custom-hr` divider (`height: 5px; background: #1d2d44; border-radius: 5px`).

### `wwol.service`

```ini
[Unit]
Description=wwol Wake-on-LAN web app
After=network-online.target
Wants=network-online.target

[Service]
User=wwol
WorkingDirectory=/opt/wwol
ExecStart=/usr/bin/python3 -m wwol.server --config /opt/wwol/config.json
Restart=on-failure
AmbientCapabilities=CAP_NET_RAW

[Install]
WantedBy=multi-user.target
```

`CAP_NET_RAW` ensures `ping` works for the unprivileged `wwol` user even on minimal images
where ping lacks file capabilities. Port 8080 needs no privilege.

### `install.sh`

Run as root from the project directory: `sudo ./install.sh`. POSIX `sh`, `set -eu`. Steps:
1. Abort with a message if not root or if `python3` / `ping` are missing (tells the user
   the `apt install` command).
2. Create system user `wwol` (no login shell, no home) if absent.
3. Copy `wwol/`, `static/`, `config.example.json` to `/opt/wwol` (create dir).
4. If `/opt/wwol/config.json` doesn't exist, copy it from `config.example.json` and print a
   reminder to edit it. Never overwrites an existing config.
5. `chown -R root:wwol /opt/wwol`; config readable by `wwol`.
6. Install `wwol.service` to `/etc/systemd/system/`, `systemctl daemon-reload`,
   `systemctl enable --now wwol`.
7. Print the URL(s) to open (`hostname -I`).

Re-running `install.sh` upgrades the code in place and restarts the service.

## README.md contents

1. What it is (one short paragraph, text only).
2. **Prepare the PC**: enable WoL in BIOS/UEFI; Windows Device Manager → network adapter →
   Power Management ("Allow this device to wake the computer", "Only allow a magic
   packet") and Advanced ("Wake on Magic Packet" = Enabled); disable Fast Startup; must be
   on wired Ethernet; finding the MAC (`ipconfig /all`) and setting a DHCP reservation for
   the PC's IP.
3. **Pi Zero on DietPi**:
   - Flash DietPi (ARMv6 image for Pi Zero/1), plug in USB-Ethernet adapter before first
     boot, find the Pi's IP from the router, SSH in as `root`.
   - Verify adapter: `ip link` (expect `eth0`), `ip -4 addr show eth0`.
   - Static IP / DHCP reservation: `dietpi-config` → Network Options: Adapters → Ethernet,
     or reservation on the router.
   - Packages: `apt update && apt install -y python3 iputils-ping git`.
4. **Pi 3B on Raspberry Pi OS Lite**: `sudo apt update && sudo apt install -y python3
   iputils-ping git` (usually already present).
5. **Install wwol**: `git clone …` (or `scp -r`), `cd wwol`, `sudo ./install.sh`.
6. **Configure**: find broadcast address (`ip -4 addr show eth0` → value after `brd`),
   edit `/opt/wwol/config.json`, `sudo systemctl restart wwol`.
7. **Use**: open `http://<pi-ip>:8080`.
8. **Manage**: `systemctl status wwol`, `journalctl -u wwol -f`, update (pull + re-run
   installer), uninstall steps.
9. **Troubleshooting**: PC doesn't wake (WoL settings, wrong MAC, wrong broadcast, Wi-Fi
   PC, Fast Startup, switch/power state); status always offline (Windows firewall blocks
   ICMP echo — allow "File and Printer Sharing (Echo Request – ICMPv4-In)"); service won't
   start (config error in journal).
10. Security note: no authentication; LAN only; don't port-forward.

## Error handling summary

| Situation | Behaviour |
|---|---|
| Bad/missing config | Exit 1 with clear message (visible in `journalctl`); systemd retries |
| Magic packet send fails | API 500 with error; UI shows it inline |
| Unknown device id | API 404 |
| Ping missing/fails | Device shows `offline` (never crashes the request) |
| Pi unreachable from browser | UI banner, keeps polling |

## Testing

`python -m unittest discover tests` (stdlib only; runs on Windows dev machine and on Pi).

- `test_config`: valid config loads with defaults; MAC normalisation for each separator
  style; each invalid case raises `ConfigError` (missing broadcast, empty devices, bad MAC,
  bad IP, bad port, invalid JSON, missing file).
- `test_wol`: packet is 102 bytes, starts with 6×`0xFF`, contains MAC 16 times; send uses
  `SO_BROADCAST` and correct address (socket mocked).
- `test_status`: exit 0 → True, non-zero → False, `FileNotFoundError` / timeout → False;
  correct argv (subprocess mocked); `check_all` returns mapping for all IPs.
- `test_server`: starts server on an ephemeral port in a thread with a temp config and
  mocked `send_magic_packet` / `check_all`; asserts `/`, `/api/devices`, wake 200/404/500,
  unknown path 404, wrong method 405.
- Manual: run locally with `curl` against each endpoint; on the Pi, wake a real PC.

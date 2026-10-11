"""HTTP server: serves the web page and a small JSON API.

Run with: python3 -m wwol.server [--config PATH]
"""
import argparse
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from wwol import link, status, wol
from wwol.config import ConfigError, load_config

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG = os.path.join(PROJECT_ROOT, "config.json")
DEFAULT_STATIC = os.path.join(PROJECT_ROOT, "static")
WAKE_PREFIX = "/api/wake/"
WAKE_HEADER = "X-WWOL"
_DEVICE_ID = re.compile(r"[0-9]+")


def make_handler(config, static_dir, sysfs_root=link.DEFAULT_SYSFS_ROOT):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def _dispatch(self, method):
            path = urlsplit(self.path).path
            if path.startswith(WAKE_PREFIX):
                allowed = "POST"
                action = lambda: self._wake(path[len(WAKE_PREFIX):])
            elif path == "/api/devices":
                allowed, action = "GET", self._devices
            elif path == "/":
                allowed, action = "GET", self._index
            elif path.startswith("/api/"):
                return self._send_json(404, {"ok": False, "error": "Not found"})
            else:
                return self._send_text(404, "Not found")
            if method != allowed:
                headers = {"Allow": allowed}
                if path.startswith("/api/"):
                    return self._send_json(
                        405, {"ok": False, "error": "Method not allowed"}, headers)
                return self._send_text(405, "Method not allowed", headers)
            action()

        def _index(self):
            try:
                with open(os.path.join(static_dir, "index.html"), "rb") as f:
                    body = f.read()
            except OSError as e:
                self.log_error("Cannot read index.html: %s", e)
                return self._send_text(500, "index.html is missing")
            self._send(200, "text/html; charset=utf-8", body)

        def _devices(self):
            online = status.check_all([d.ip for d in config.devices if d.ip])
            devices = []
            for i, d in enumerate(config.devices):
                if d.ip is not None and online.get(d.ip, False):
                    state = "online"
                elif d.interface is not None:
                    # The PC's network card keeps its link while Wake-on-LAN is armed.
                    up = link.is_link_up(d.interface, sysfs_root)
                    state = "standby" if up else "nolink"
                elif d.ip is None:
                    state = "unknown"
                else:
                    state = "offline"
                devices.append({"id": i, "name": d.name, "mac": d.mac, "ip": d.ip,
                                "interface": d.interface, "status": state})
            self._send_json(200, devices)

        def _wake(self, raw_id):
            # Browsers only let another site send a custom header after a CORS
            # preflight, which this server never approves, so requiring one
            # stops other web pages from waking PCs.
            if self.headers.get(WAKE_HEADER) != "1":
                return self._send_json(
                    403, {"ok": False, "error": "Missing {}: 1 header".format(WAKE_HEADER)})
            if not _DEVICE_ID.fullmatch(raw_id) or int(raw_id) >= len(config.devices):
                return self._send_json(404, {"ok": False, "error": "Unknown device"})
            device = config.devices[int(raw_id)]
            try:
                wol.send_magic_packet(device.mac, device.broadcast, device.wol_port)
            except OSError as e:
                self.log_error("Failed to wake %s (%s): %s", device.name, device.mac, e)
                return self._send_json(500, {"ok": False, "error": str(e)})
            self.log_message("Sent magic packet to %s (%s) via %s:%d",
                             device.name, device.mac, device.broadcast, device.wol_port)
            self._send_json(200, {"ok": True})

        def _send_json(self, code, obj, headers=None):
            body = json.dumps(obj).encode("utf-8")
            self._send(code, "application/json", body, headers)

        def _send_text(self, code, text, headers=None):
            self._send(code, "text/plain; charset=utf-8", text.encode("utf-8"), headers)

        def _send(self, code, content_type, body, headers=None):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

    return Handler


def create_server(config, static_dir=DEFAULT_STATIC,
                  sysfs_root=link.DEFAULT_SYSFS_ROOT):
    return ThreadingHTTPServer((config.host, config.port),
                               make_handler(config, static_dir, sysfs_root))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="wwol", description="Wake-on-LAN web app for Raspberry Pi.")
    parser.add_argument("--config", default=DEFAULT_CONFIG,
                        help="path to config.json (default: %(default)s)")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
    except ConfigError as e:
        print("Config error: {}".format(e), file=sys.stderr)
        return 1
    try:
        server = create_server(config)
    except OSError as e:
        print("Cannot listen on {}:{}: {}".format(config.host, config.port, e),
              file=sys.stderr)
        return 1
    print("Listening on http://{}:{}".format(config.host, config.port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

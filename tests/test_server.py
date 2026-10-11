import contextlib
import io
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock

from wwol.config import Config, Device
from wwol.server import create_server, main

DEVICES = [
    Device(name="Gaming PC", mac="AA:BB:CC:DD:EE:FF",
           broadcast="192.168.1.255", ip="192.168.1.50"),
    Device(name="Laptop", mac="11:22:33:44:55:66",
           broadcast="192.168.2.255", wol_port=7, ip="192.168.1.51"),
    Device(name="<b>Media</b> PC", mac="66:55:44:33:22:11",
           broadcast="192.168.1.255"),
]

WAKE_HEADERS = {"X-WWOL": "1"}

# No proxies, even if the dev machine has one configured.
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class ServerTestBase(unittest.TestCase):
    devices = DEVICES

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.static = tmp.name
        with open(os.path.join(tmp.name, "index.html"), "w", encoding="utf-8") as f:
            f.write("<!doctype html><title>test page</title>")
        self.sysfs = os.path.join(tmp.name, "sys")
        os.makedirs(self.sysfs)

        # Silence per-request logging during tests.
        self.patch("http.server.BaseHTTPRequestHandler.log_message")
        self.check_all = self.patch(
            "wwol.status.check_all", return_value={"192.168.1.50": True,
                                                   "192.168.1.51": False})
        self.send = self.patch("wwol.wol.send_magic_packet")
        self.start_server(self.sysfs)

    def start_server(self, sysfs_root):
        config = Config(host="127.0.0.1", port=0, devices=list(self.devices))
        server = create_server(config, static_dir=self.static, sysfs_root=sysfs_root)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.base = "http://127.0.0.1:{}".format(server.server_address[1])

    def patch(self, target, **kwargs):
        patcher = mock.patch(target, **kwargs)
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        return mocked

    def request(self, method, path, headers=None):
        data = b"" if method == "POST" else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers=headers or {})
        try:
            with OPENER.open(req, timeout=5) as resp:
                return resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as e:
            body = e.read()
            e.close()
            return e.code, e.headers, body


class ServerTest(ServerTestBase):
    def test_index_served(self):
        code, headers, body = self.request("GET", "/")
        self.assertEqual(code, 200)
        self.assertEqual(headers["Content-Type"], "text/html; charset=utf-8")
        self.assertIn(b"test page", body)

    def test_devices_reports_status(self):
        code, headers, body = self.request("GET", "/api/devices")
        self.assertEqual(code, 200)
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(json.loads(body.decode("utf-8")), [
            {"id": 0, "name": "Gaming PC", "mac": "AA:BB:CC:DD:EE:FF",
             "ip": "192.168.1.50", "interface": None, "status": "online"},
            {"id": 1, "name": "Laptop", "mac": "11:22:33:44:55:66",
             "ip": "192.168.1.51", "interface": None, "status": "offline"},
            {"id": 2, "name": "<b>Media</b> PC", "mac": "66:55:44:33:22:11",
             "ip": None, "interface": None, "status": "unknown"},
        ])
        # The device without an ip is never pinged.
        self.check_all.assert_called_once_with(["192.168.1.50", "192.168.1.51"])

    def test_query_strings_are_ignored(self):
        for path in ["/?v=2", "/api/devices?t=123"]:
            with self.subTest(path=path):
                code, _, _ = self.request("GET", path)
                self.assertEqual(code, 200)

    def test_wake_sends_packet(self):
        code, _, body = self.request("POST", "/api/wake/1", WAKE_HEADERS)
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body.decode("utf-8")), {"ok": True})
        self.send.assert_called_once_with("11:22:33:44:55:66", "192.168.2.255", 7)

    def test_wake_without_custom_header_is_rejected(self):
        # What another website's form or simple fetch() would send: no custom
        # header, because adding one forces a CORS preflight we never approve.
        for headers in [None, {"Content-Type": "text/plain"}, {"X-WWOL": "0"}]:
            with self.subTest(headers=headers):
                code, _, body = self.request("POST", "/api/wake/0", headers)
                self.assertEqual(code, 403)
                self.assertEqual(json.loads(body.decode("utf-8"))["ok"], False)
        self.send.assert_not_called()

    def test_wake_unknown_ids_return_404(self):
        for path in ["/api/wake/3", "/api/wake/99", "/api/wake/-1",
                     "/api/wake/abc", "/api/wake/", "/api/wake/0/extra"]:
            with self.subTest(path=path):
                code, _, body = self.request("POST", path, WAKE_HEADERS)
                self.assertEqual(code, 404)
                self.assertEqual(json.loads(body.decode("utf-8")),
                                 {"ok": False, "error": "Unknown device"})
        self.send.assert_not_called()

    def test_wake_send_failure_returns_500(self):
        self.send.side_effect = OSError("Network is unreachable")
        code, _, body = self.request("POST", "/api/wake/0", WAKE_HEADERS)
        self.assertEqual(code, 500)
        self.assertEqual(json.loads(body.decode("utf-8")),
                         {"ok": False, "error": "Network is unreachable"})

    def test_unknown_api_path_is_json_404(self):
        code, headers, body = self.request("GET", "/api/nope")
        self.assertEqual(code, 404)
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(json.loads(body.decode("utf-8"))["ok"], False)

    def test_unknown_path_is_text_404(self):
        code, headers, _ = self.request("GET", "/favicon.ico")
        self.assertEqual(code, 404)
        self.assertTrue(headers["Content-Type"].startswith("text/plain"))

    def test_wrong_method_is_405(self):
        for method, path, allowed in [("GET", "/api/wake/0", "POST"),
                                      ("POST", "/api/devices", "GET"),
                                      ("POST", "/", "GET")]:
            with self.subTest(method=method, path=path):
                code, headers, _ = self.request(method, path)
                self.assertEqual(code, 405)
                self.assertEqual(headers["Allow"], allowed)
        self.send.assert_not_called()


def link_device(name, iface, ip=None):
    return Device(name=name, mac="AA:BB:CC:DD:EE:FF", broadcast="10.0.0.255",
                  ip=ip, interface=iface)


class LinkStatusTest(ServerTestBase):
    """Devices with an interface report standby/nolink from the cable's link state."""
    devices = [
        link_device("Pings", "eth0", ip="192.168.1.50"),        # ping ok, link up
        link_device("Standby", "eth1", ip="192.168.1.51"),      # ping fails, link up
        link_device("No ip, up", "eth2"),                       # never pinged, link up
        link_device("Cable dead", "eth3", ip="192.168.1.51"),   # ping fails, link down
        link_device("No such iface", "eth9", ip="192.168.1.51"),
        link_device("Pings, no link", "eth3", ip="192.168.1.50"),
        link_device("No ip, down", "eth3"),
    ]

    def setUp(self):
        super().setUp()
        for iface, carrier in [("eth0", "1"), ("eth1", "1"), ("eth2", "1"),
                               ("eth3", "0")]:
            os.makedirs(os.path.join(self.sysfs, iface))
            with open(os.path.join(self.sysfs, iface, "carrier"), "w") as f:
                f.write(carrier + "\n")

    def test_devices_reports_status(self):
        code, _, body = self.request("GET", "/api/devices")
        self.assertEqual(code, 200)
        got = [(d["name"], d["interface"], d["status"])
               for d in json.loads(body.decode("utf-8"))]
        self.assertEqual(got, [
            ("Pings", "eth0", "online"),
            ("Standby", "eth1", "standby"),
            ("No ip, up", "eth2", "standby"),
            ("Cable dead", "eth3", "nolink"),
            ("No such iface", "eth9", "nolink"),
            ("Pings, no link", "eth3", "online"),
            ("No ip, down", "eth3", "nolink"),
        ])
        # Devices without an ip are never pinged.
        self.check_all.assert_called_once_with(
            ["192.168.1.50", "192.168.1.51", "192.168.1.51", "192.168.1.51",
             "192.168.1.50"])

    def test_no_sysfs_means_nolink(self):
        # Like the Windows dev machine, which has no /sys at all.
        self.start_server(os.path.join(self.sysfs, "nope"))
        _, _, body = self.request("GET", "/api/devices")
        got = [d["status"] for d in json.loads(body.decode("utf-8"))]
        self.assertEqual(got, ["online", "nolink", "nolink", "nolink",
                               "nolink", "online", "nolink"])


class MainTest(unittest.TestCase):
    def test_bad_config_exits_1_with_message(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = main(["--config", os.path.join(tempfile.gettempdir(),
                                                  "wwol-missing-config.json")])
        self.assertEqual(code, 1)
        self.assertIn("Config error", stderr.getvalue())
        self.assertIn("not found", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()

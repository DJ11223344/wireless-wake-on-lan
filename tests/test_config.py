import os
import tempfile
import unittest

from wwol.config import (
    Config,
    ConfigError,
    Device,
    load_config,
    normalize_mac,
    parse_config,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def minimal(**overrides):
    data = {
        "broadcast": "192.168.1.255",
        "devices": [{"name": "PC", "mac": "AA:BB:CC:DD:EE:FF"}],
    }
    data.update(overrides)
    return data


def with_device(**fields):
    device = {"name": "PC", "mac": "AA:BB:CC:DD:EE:FF"}
    device.update(fields)
    return minimal(devices=[device])


def without(data, key):
    data = dict(data)
    del data[key]
    return data


class NormalizeMacTest(unittest.TestCase):
    def test_accepts_separator_styles(self):
        for raw in [
            "AA:BB:CC:DD:EE:FF",
            "aa-bb-cc-dd-ee-ff",
            "aabb.ccdd.eeff",
            "AABBCCDDEEFF",
            "  aa:bb:cc:dd:ee:ff  ",
        ]:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_mac(raw), "AA:BB:CC:DD:EE:FF")

    def test_rejects_invalid(self):
        for raw in [
            "",
            "AA:BB:CC:DD:EE",
            "AA:BB:CC:DD:EE:FF:00",
            "GG:BB:CC:DD:EE:FF",
            "AA BB CC DD EE FF",
            None,
            123,
        ]:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    normalize_mac(raw)


class ParseConfigTest(unittest.TestCase):
    def test_minimal_config_uses_defaults(self):
        config = parse_config(minimal())
        self.assertEqual(
            config,
            Config(
                host="0.0.0.0",
                port=8080,
                devices=[
                    Device(
                        name="PC",
                        mac="AA:BB:CC:DD:EE:FF",
                        broadcast="192.168.1.255",
                        wol_port=9,
                        ip=None,
                    )
                ],
            ),
        )

    def test_full_device_overrides(self):
        config = parse_config(
            minimal(
                host="127.0.0.1",
                port=9000,
                devices=[
                    {
                        "name": "  Media PC  ",
                        "mac": "11-22-33-44-55-66",
                        "ip": "192.168.2.50",
                        "broadcast": "192.168.2.255",
                        "wol_port": 7,
                    }
                ],
            )
        )
        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.port, 9000)
        self.assertEqual(
            config.devices[0],
            Device(
                name="Media PC",
                mac="11:22:33:44:55:66",
                broadcast="192.168.2.255",
                wol_port=7,
                ip="192.168.2.50",
            ),
        )

    def test_null_ip_means_no_ip(self):
        config = parse_config(with_device(ip=None))
        self.assertIsNone(config.devices[0].ip)

    def test_interface_defaults_to_none(self):
        self.assertIsNone(parse_config(minimal()).devices[0].interface)
        self.assertIsNone(parse_config(with_device(interface=None)).devices[0].interface)

    def test_valid_interface_names(self):
        for name in ["eth0", "enx001122334455", "wlan0", "a", "x" * 15, "br-lan.10"]:
            with self.subTest(name=name):
                config = parse_config(with_device(interface=name))
                self.assertEqual(config.devices[0].interface, name)

    def test_invalid_interface_names(self):
        for name in ["", "x" * 16, "eth/0", "../eth0", "eth 0", " eth0", "eth0\n",
                     "eth\t0", ".", "..", "eth0:1", 0, True, ["eth0"]]:
            with self.subTest(name=name):
                with self.assertRaises(ConfigError) as ctx:
                    parse_config(with_device(interface=name))
                self.assertIn("devices[0].interface", str(ctx.exception))

    def test_invalid_configs(self):
        cases = [
            ([], "JSON object"),
            ("text", "JSON object"),
            (without(minimal(), "broadcast"), "broadcast"),
            (minimal(broadcast="192.168.1"), "broadcast"),
            (minimal(broadcast=255), "broadcast"),
            (without(minimal(), "devices"), "devices"),
            (minimal(devices=[]), "devices"),
            (minimal(devices={"name": "PC"}), "devices"),
            (minimal(devices=["PC"]), "devices[0]"),
            (with_device(name=""), "devices[0].name"),
            (with_device(name="   "), "devices[0].name"),
            (minimal(devices=[{"mac": "AA:BB:CC:DD:EE:FF"}]), "devices[0].name"),
            (with_device(mac="nope"), "devices[0].mac"),
            (minimal(devices=[{"name": "PC"}]), "devices[0].mac"),
            (with_device(ip="999.1.1.1"), "devices[0].ip"),
            (with_device(broadcast="x"), "devices[0].broadcast"),
            (with_device(wol_port=True), "devices[0].wol_port"),
            (with_device(wol_port=0), "devices[0].wol_port"),
            (minimal(port=0), "port"),
            (minimal(port=70000), "port"),
            (minimal(port="8080"), "port"),
            (minimal(port=True), "port"),
            (minimal(port=80.5), "port"),
            (minimal(host=""), "host"),
            (minimal(host=None), "host"),
        ]
        for data, expected in cases:
            with self.subTest(data=data):
                with self.assertRaises(ConfigError) as ctx:
                    parse_config(data)
                self.assertIn(expected, str(ctx.exception))


class LoadConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, content, encoding="utf-8"):
        path = os.path.join(self.tmp.name, "config.json")
        with open(path, "w", encoding=encoding) as f:
            f.write(content)
        return path

    def test_missing_file(self):
        with self.assertRaises(ConfigError) as ctx:
            load_config(os.path.join(self.tmp.name, "nope.json"))
        self.assertIn("not found", str(ctx.exception))

    def test_invalid_json(self):
        path = self.write('{"broadcast": ')
        with self.assertRaises(ConfigError) as ctx:
            load_config(path)
        self.assertIn("not valid JSON", str(ctx.exception))

    def test_loads_file_with_utf8_bom(self):
        path = self.write(
            '{"broadcast": "192.168.1.255", '
            '"devices": [{"name": "PC", "mac": "AA:BB:CC:DD:EE:FF"}]}',
            encoding="utf-8-sig",
        )
        self.assertEqual(load_config(path).devices[0].name, "PC")

    def test_example_config_is_valid(self):
        config = load_config(os.path.join(PROJECT_ROOT, "config.example.json"))
        self.assertEqual(len(config.devices), 2)
        self.assertEqual(config.devices[1].mac, "11:22:33:44:55:66")
        self.assertIsNone(config.devices[1].ip)


if __name__ == "__main__":
    unittest.main()

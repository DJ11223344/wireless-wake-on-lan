"""Load and validate the wwol config file."""
import ipaddress
import json
import re
from dataclasses import dataclass
from typing import List, Optional

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8080
DEFAULT_WOL_PORT = 9

_MAC_SEPARATORS = re.compile(r"[:.\-]")
_MAC_DIGITS = re.compile(r"[0-9A-Fa-f]{12}")
# Linux interface names: at most 15 characters (IFNAMSIZ - 1), no '/', ':' or
# whitespace, and not '.' or '..' (the same rules as the kernel's dev_valid_name).
_INTERFACE = re.compile(r"[^/:\s]{1,15}")


class ConfigError(Exception):
    """The config file is missing or invalid. The message is shown to the user."""


@dataclass(frozen=True)
class Device:
    name: str
    mac: str
    broadcast: str
    wol_port: int = DEFAULT_WOL_PORT
    ip: Optional[str] = None
    interface: Optional[str] = None


@dataclass(frozen=True)
class Config:
    host: str
    port: int
    devices: List[Device]


def normalize_mac(value):
    """Return value as 'AA:BB:CC:DD:EE:FF'. Raises ValueError if it isn't a MAC."""
    if not isinstance(value, str):
        raise ValueError("MAC address must be a string")
    digits = _MAC_SEPARATORS.sub("", value.strip())
    if not _MAC_DIGITS.fullmatch(digits):
        raise ValueError("{!r} is not a valid MAC address".format(value))
    digits = digits.upper()
    return ":".join(digits[i:i + 2] for i in range(0, 12, 2))


def load_config(path):
    """Read and validate the config file at path."""
    try:
        # utf-8-sig also accepts files saved with a BOM (e.g. by Windows Notepad).
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise ConfigError("Config file not found: {}".format(path)) from None
    except json.JSONDecodeError as e:
        raise ConfigError("{} is not valid JSON: {}".format(path, e)) from None
    except (OSError, UnicodeDecodeError) as e:
        raise ConfigError("Cannot read {}: {}".format(path, e)) from None
    return parse_config(data)


def parse_config(data):
    """Validate already-parsed JSON data and build a Config."""
    if not isinstance(data, dict):
        raise ConfigError("Config must be a JSON object")
    host = data.get("host", DEFAULT_HOST)
    if not isinstance(host, str) or not host.strip():
        raise ConfigError("host: must be a non-empty string like \"0.0.0.0\"")
    port = _port(data.get("port", DEFAULT_PORT), "port")
    if "broadcast" not in data:
        raise ConfigError("broadcast: required, e.g. \"192.168.1.255\"")
    default_broadcast = _ipv4(data["broadcast"], "broadcast")
    devices = data.get("devices")
    if not isinstance(devices, list) or not devices:
        raise ConfigError("devices: must be a non-empty list")
    return Config(
        host=host.strip(),
        port=port,
        devices=[_device(raw, i, default_broadcast) for i, raw in enumerate(devices)],
    )


def _device(raw, index, default_broadcast):
    where = "devices[{}]".format(index)
    if not isinstance(raw, dict):
        raise ConfigError("{}: must be an object with name and mac".format(where))
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ConfigError("{}.name: must be a non-empty string".format(where))
    try:
        mac = normalize_mac(raw.get("mac"))
    except ValueError as e:
        raise ConfigError("{}.mac: {}".format(where, e)) from None
    ip = raw.get("ip")
    if ip is not None:
        ip = _ipv4(ip, where + ".ip")
    broadcast = default_broadcast
    if "broadcast" in raw:
        broadcast = _ipv4(raw["broadcast"], where + ".broadcast")
    wol_port = _port(raw.get("wol_port", DEFAULT_WOL_PORT), where + ".wol_port")
    interface = raw.get("interface")
    if interface is not None:
        interface = _interface(interface, where + ".interface")
    return Device(name=name.strip(), mac=mac, broadcast=broadcast,
                  wol_port=wol_port, ip=ip, interface=interface)


def _interface(value, where):
    if (not isinstance(value, str) or not _INTERFACE.fullmatch(value)
            or value in (".", "..")):
        raise ConfigError(
            "{}: must be a network interface name like \"eth0\" "
            "(1-15 characters, no '/', ':' or spaces)".format(where))
    return value


def _ipv4(value, where):
    if not isinstance(value, str):
        raise ConfigError("{}: must be a string like \"192.168.1.255\"".format(where))
    try:
        return str(ipaddress.IPv4Address(value.strip()))
    except ValueError:
        raise ConfigError(
            "{}: {!r} is not a valid IPv4 address".format(where, value)) from None


def _port(value, where):
    # bool is a subclass of int, so reject it explicitly.
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        raise ConfigError("{}: must be a whole number from 1 to 65535".format(where))
    return value

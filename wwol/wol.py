"""Build and send Wake-on-LAN magic packets."""
import socket


def build_magic_packet(mac):
    """6 x 0xFF followed by the 6-byte MAC repeated 16 times (102 bytes)."""
    mac_bytes = bytes.fromhex(mac.replace(":", ""))
    if len(mac_bytes) != 6:
        raise ValueError("{!r} is not a valid MAC address".format(mac))
    return b"\xff" * 6 + mac_bytes * 16


def send_magic_packet(mac, broadcast, port=9):
    """Send a magic packet for mac to the broadcast address over UDP."""
    packet = build_magic_packet(mac)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (broadcast, port))

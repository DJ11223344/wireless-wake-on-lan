import socket
import unittest
from unittest import mock

from wwol.wol import build_magic_packet, send_magic_packet

MAC = "AA:BB:CC:DD:EE:FF"


class BuildMagicPacketTest(unittest.TestCase):
    def test_layout(self):
        packet = build_magic_packet(MAC)
        self.assertEqual(len(packet), 102)
        self.assertEqual(packet[:6], b"\xff" * 6)
        self.assertEqual(packet[6:], bytes.fromhex("AABBCCDDEEFF") * 16)

    def test_rejects_bad_mac(self):
        for bad in ["AA:BB", "ZZ:BB:CC:DD:EE:FF", ""]:
            with self.subTest(mac=bad):
                with self.assertRaises(ValueError):
                    build_magic_packet(bad)


class SendMagicPacketTest(unittest.TestCase):
    def test_enables_broadcast_and_sends_to_address(self):
        with mock.patch("wwol.wol.socket.socket") as socket_cls:
            sock = socket_cls.return_value.__enter__.return_value
            send_magic_packet(MAC, "192.168.1.255", 9)
        socket_cls.assert_called_once_with(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt.assert_called_once_with(
            socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto.assert_called_once_with(
            build_magic_packet(MAC), ("192.168.1.255", 9))

    def test_packet_arrives_over_udp(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
            receiver.bind(("127.0.0.1", 0))
            receiver.settimeout(2)
            send_magic_packet(MAC, "127.0.0.1", receiver.getsockname()[1])
            data, _ = receiver.recvfrom(1024)
        self.assertEqual(data, build_magic_packet(MAC))

    def test_network_errors_propagate(self):
        with mock.patch("wwol.wol.socket.socket") as socket_cls:
            sock = socket_cls.return_value.__enter__.return_value
            sock.sendto.side_effect = OSError("Network is unreachable")
            with self.assertRaises(OSError):
                send_magic_packet(MAC, "192.168.1.255")


if __name__ == "__main__":
    unittest.main()

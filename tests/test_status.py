import subprocess
import time
import unittest
from unittest import mock

from wwol import status


class IsOnlineTest(unittest.TestCase):
    def run_with(self, **mock_kwargs):
        with mock.patch("wwol.status.subprocess.run", **mock_kwargs) as run:
            result = status.is_online("192.168.1.50")
        return result, run

    def test_reply_means_online(self):
        result, run = self.run_with(
            return_value=subprocess.CompletedProcess([], 0))
        self.assertTrue(result)
        args, kwargs = run.call_args
        self.assertEqual(args[0], ["ping", "-c", "1", "-W", "1", "192.168.1.50"])
        self.assertEqual(kwargs["timeout"], 2)
        self.assertEqual(kwargs["stdout"], subprocess.DEVNULL)
        self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)

    def test_no_reply_means_offline(self):
        result, _ = self.run_with(return_value=subprocess.CompletedProcess([], 1))
        self.assertFalse(result)

    def test_missing_ping_binary_means_offline(self):
        result, _ = self.run_with(side_effect=FileNotFoundError("ping"))
        self.assertFalse(result)

    def test_hung_ping_means_offline(self):
        result, _ = self.run_with(
            side_effect=subprocess.TimeoutExpired(cmd="ping", timeout=2))
        self.assertFalse(result)


class CheckAllTest(unittest.TestCase):
    def test_returns_result_per_ip(self):
        def fake(ip, timeout=1):
            return ip.endswith(".50")

        with mock.patch("wwol.status.is_online", side_effect=fake):
            result = status.check_all(["192.168.1.50", "192.168.1.51"])
        self.assertEqual(result, {"192.168.1.50": True, "192.168.1.51": False})

    def test_empty_input(self):
        self.assertEqual(status.check_all([]), {})

    def test_duplicate_ips_pinged_once(self):
        with mock.patch("wwol.status.is_online", return_value=True) as is_online:
            result = status.check_all(["10.0.0.1", "10.0.0.1"])
        self.assertEqual(result, {"10.0.0.1": True})
        self.assertEqual(is_online.call_count, 1)

    def test_pings_run_concurrently(self):
        def slow(ip, timeout=1):
            time.sleep(0.3)
            return True

        ips = ["10.0.0.{}".format(n) for n in range(1, 5)]
        with mock.patch("wwol.status.is_online", side_effect=slow):
            start = time.monotonic()
            status.check_all(ips)
            elapsed = time.monotonic() - start
        self.assertLess(elapsed, 0.9)


if __name__ == "__main__":
    unittest.main()

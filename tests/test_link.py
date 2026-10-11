import os
import tempfile
import unittest

from wwol import link


class IsLinkUpTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name

    def make(self, iface, carrier=None):
        """Create a fake sysfs interface dir; None leaves the carrier file out."""
        path = os.path.join(self.root, iface)
        os.makedirs(path)
        if carrier is not None:
            with open(os.path.join(path, "carrier"), "w") as f:
                f.write(carrier)

    def up(self, iface):
        return link.is_link_up(iface, sysfs_root=self.root)

    def test_carrier_1_means_up(self):
        self.make("eth0", "1\n")
        self.assertIs(self.up("eth0"), True)

    def test_carrier_0_means_down(self):
        self.make("eth0", "0\n")
        self.assertIs(self.up("eth0"), False)

    def test_unreadable_carrier_means_down(self):
        self.make("nocarrier")
        self.make("garbage", "garbage\n")
        self.make("empty", "")
        for iface in ["nocarrier", "garbage", "empty", "missing"]:
            with self.subTest(iface=iface):
                self.assertIs(self.up(iface), False)

    def test_carrier_directory_instead_of_file_means_down(self):
        os.makedirs(os.path.join(self.root, "eth0", "carrier"))
        self.assertIs(self.up("eth0"), False)

    def test_missing_sysfs_root_means_down(self):
        self.assertIs(
            link.is_link_up("eth0", sysfs_root=os.path.join(self.root, "nope")), False)

    def test_default_root_is_sys_class_net(self):
        self.assertEqual(link.DEFAULT_SYSFS_ROOT, "/sys/class/net")


if __name__ == "__main__":
    unittest.main()

"""Read a network interface's link state from Linux sysfs."""
import os

DEFAULT_SYSFS_ROOT = "/sys/class/net"


def is_link_up(interface, sysfs_root=DEFAULT_SYSFS_ROOT):
    """True if interface's carrier file reads 1. Never raises."""
    try:
        with open(os.path.join(sysfs_root, interface, "carrier")) as f:
            return f.read().strip() == "1"
    except (OSError, ValueError):
        # Missing interface, no /sys (e.g. Windows), or EINVAL from a down link.
        return False

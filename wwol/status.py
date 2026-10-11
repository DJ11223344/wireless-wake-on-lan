"""Check whether hosts are online with a single ping."""
import subprocess
from concurrent.futures import ThreadPoolExecutor

MAX_WORKERS = 8


def is_online(ip, timeout=1):
    """True if ip answers one ping within timeout seconds. Never raises."""
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", str(timeout), ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout + 1,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def check_all(ips, timeout=1):
    """Ping every unique ip concurrently. Returns {ip: online}."""
    unique = list(dict.fromkeys(ips))
    if not unique:
        return {}
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(unique))) as pool:
        results = list(pool.map(lambda ip: is_online(ip, timeout), unique))
    return dict(zip(unique, results))

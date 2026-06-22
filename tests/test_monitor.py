import importlib.util
import pathlib
import unittest


MODULE_PATH = pathlib.Path(__file__).parents[1] / "scripts" / "monitor-system.py"
SPEC = importlib.util.spec_from_file_location("monitor_system", MODULE_PATH)
monitor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(monitor)


class AccessModeChecksTests(unittest.TestCase):
    """cloudflared only exists in tunnel mode; checking it in LAN/VPN mode is a
    permanent false 'down' alert and keeps the watchdog unit failing forever."""

    def test_cloudflared_skipped_without_tunnel(self):
        self.assertFalse(monitor.tunnel_enabled({"ACCESS_MODE": "lan", "COMPOSE_PROFILES": ""}))
        self.assertNotIn("cloudflared", monitor.active_checks({"ACCESS_MODE": "lan"}))
        self.assertNotIn("cloudflared", monitor.active_checks({"COMPOSE_PROFILES": ""}))

    def test_cloudflared_checked_in_tunnel_mode(self):
        self.assertTrue(monitor.tunnel_enabled({"COMPOSE_PROFILES": "tunnel"}))
        self.assertTrue(monitor.tunnel_enabled({"ACCESS_MODE": "tunnel"}))
        self.assertIn("cloudflared", monitor.active_checks({"COMPOSE_PROFILES": "tunnel"}))
        self.assertIn("cloudflared", monitor.active_checks({"ACCESS_MODE": "tunnel"}))

    def test_core_checks_run_in_every_mode(self):
        for env in ({"ACCESS_MODE": "lan"}, {"COMPOSE_PROFILES": "tunnel"}):
            names = set(monitor.active_checks(env))
            self.assertLessEqual({"n8n", "memo-bridge", "public-tunnel", "daily-brief"}, names)


if __name__ == "__main__":
    unittest.main()

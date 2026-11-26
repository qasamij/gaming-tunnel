import socket
import threading
import time
import unittest

import monitor


class MonitorTests(unittest.TestCase):
    def setUp(self):
        monitor._previous.clear()
        monitor.history.clear()
        monitor.latest.clear()

    def test_parse(self):
        self.assertEqual(monitor.parse("key 10 20\n"), {"key": (10, 20)})

    def test_rate_and_counter_reset(self):
        self.assertEqual(monitor.sample("x", 10, 20, 1), (None, None))
        self.assertEqual(monitor.sample("x", 110, 220, 3), (400, 800))
        self.assertEqual(monitor.sample("x", 1, 2, 4), (None, None))

    def test_udp_probe_uses_no_clock_sync(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server.bind(("127.0.0.1", 0))
        port = server.getsockname()[1]
        stop = threading.Event()

        def echo():
            while not stop.is_set():
                try:
                    data, addr = server.recvfrom(128)
                    server.sendto(data[:8], addr)
                except OSError:
                    break

        thread = threading.Thread(target=echo, daemon=True)
        thread.start()
        try:
            result = monitor.probe_once({
                "probe_host": "127.0.0.1",
                "probe_port": port,
                "probe_timeout": 1.0,
                "tunnel": "omawg0",
            })
            self.assertEqual(result["mode"], "udp")
            self.assertIsNotNone(result["rtt"])
            self.assertLess(result["rtt"], 500)
        finally:
            stop.set()
            server.close()

    def test_loss_percent_uses_the_whole_window(self):
        self.assertIsNone(monitor.loss_percent([]))
        self.assertEqual(monitor.loss_percent([True, True, True]), 0.0)
        self.assertAlmostEqual(monitor.loss_percent([True, False, True, False]), 50.0)
        self.assertAlmostEqual(monitor.loss_percent([False]), 100.0)

    def test_snapshot_enriches_users(self):
        result = monitor.snapshot({
            "PUB": {"name": "client01", "used": 1024, "enabled": True,
                    "expires": 0, "quota": 0},
        })
        self.assertEqual(result["users"]["PUB"]["name"], "client01")
        self.assertEqual(result["users"]["PUB"]["used"], 1024)
        self.assertIn("latency", result)


if __name__ == "__main__":
    unittest.main()

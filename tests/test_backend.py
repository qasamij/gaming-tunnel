import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import backend as b


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.data = root / "panel"
        self.data.mkdir()
        self.client = root / "client"
        self.client.mkdir()
        self.runtime = root / "runtime"
        self.runtime.mkdir()
        (self.client / "server.pub").write_text("SERVERPUB\n")
        (self.data / "network.json").write_text(json.dumps({
            "endpoint": "198.51.100.10",
            "network": "10.7.0.0/24",
            "obfuscation": {"Jc": 3, "Jmin": 40, "Jmax": 70,
                            "S1": 32, "S2": 48,
                            "H1": 111, "H2": 222, "H3": 333, "H4": 444},
        }))
        self.calls = []

        def fake_run(*args, data=None, timeout=15):
            self.calls.append(args)
            if args[-1] == "genkey":
                return "PRIVKEY"
            if args[-1] == "pubkey":
                return "PEERPUB"
            if args[-1] == "listen-port":
                return "51820"
            if args[-1] in ("allowed-ips", "transfer"):
                return ""
            if args[-1] == "showconf":
                return "[Interface]\n"
            return ""

        self.patches = [
            patch.object(b, "D", self.data),
            patch.object(b, "DB", self.data / "users.json"),
            patch.object(b, "CLIENT", self.client),
            patch.object(b, "RUNTIME", self.runtime),
            patch.object(b, "run", side_effect=fake_run),
        ]
        for item in self.patches:
            item.start()
        self.addCleanup(self.stop_patches)

    def stop_patches(self):
        for item in self.patches:
            item.stop()
        self.tmp.cleanup()

    def test_create_allocates_ip_and_renders_config(self):
        b.create({"name": "client01", "days": "0", "quota": "0"})
        users = b.load()
        self.assertEqual(users["client01"]["ip"], "10.7.0.2/32")
        self.assertTrue(users["client01"]["enabled"])
        cfg = (self.data / "client01.conf").read_text()
        self.assertIn("Address = 10.7.0.2/32", cfg)
        self.assertIn("Endpoint = 198.51.100.10:51820", cfg)
        self.assertIn("H1 = 111", cfg)
        self.assertIn("PublicKey = SERVERPUB", cfg)

    def test_reconcile_disables_expired_user(self):
        b.create({"name": "client01", "days": "0", "quota": "0"})
        users = b.load()
        users["client01"]["expires"] = time.time() - 1
        b.save(users)
        b.reconcile()
        self.assertFalse(b.load()["client01"]["enabled"])
        self.assertTrue(any("remove" in str(call) for call in self.calls))


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import healthcheck

PUB = "A" * 43 + "="


class HealthcheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.data = root / "panel"
        self.data.mkdir()
        self.runtime = root / "runtime"
        self.runtime.mkdir()
        (self.data / "network.json").write_text(json.dumps({
            "endpoint": "198.51.100.10", "network": "10.7.0.0/24",
            "probe_host": "10.9.0.1", "probe_port": 5355,
        }))
        (self.runtime / "omawg0.conf").write_text(
            "[Interface]\nPrivateKey = B\n\n[Peer]\nPublicKey = {}\n".format(PUB))
        self.now = 1_800_000_000

    def tearDown(self):
        self.tmp.cleanup()

    def test_peer_pubkey_and_handshake_age(self):
        self.assertEqual(healthcheck.peer_pubkey("[Peer]\nPublicKey = " + PUB), PUB)
        text = "{} {}\nOTHER {}\n".format(PUB, self.now - 42, self.now)
        self.assertEqual(healthcheck.handshake_age(text, PUB, self.now), 42)
        self.assertIsNone(healthcheck.handshake_age(text, "MISSING", self.now))

    def test_assess_reasons(self):
        self.assertEqual(healthcheck.assess(None, True, 300), (False, "no-handshake"))
        self.assertEqual(healthcheck.assess(301, True, 300), (False, "stale-handshake"))
        self.assertEqual(healthcheck.assess(10, False, 300), (False, "probe-failed"))
        self.assertEqual(healthcheck.assess(10, None, 300), (True, "ok"))
        self.assertEqual(healthcheck.assess(10, True, 300), (True, "ok"))

    def test_check_healthy_with_fresh_handshake_and_probe(self):
        runner = lambda *a, **k: "{} {}\n".format(PUB, self.now - 5)
        probe = lambda cfg, run: {"rtt": 18.0}
        with patch.object(healthcheck, "RUNTIME", self.runtime):
            ok, reason = healthcheck.check(self.data, runner, probe, self.now)
        self.assertEqual((ok, reason), (True, "ok"))

    def test_check_fails_when_end_to_end_probe_fails(self):
        runner = lambda *a, **k: "{} {}\n".format(PUB, self.now - 5)
        probe = lambda cfg, run: {"rtt": None}
        with patch.object(healthcheck, "RUNTIME", self.runtime):
            ok, reason = healthcheck.check(self.data, runner, probe, self.now)
        self.assertEqual((ok, reason), (False, "probe-failed"))

    def test_check_fails_when_handshake_is_stale(self):
        runner = lambda *a, **k: "{} {}\n".format(PUB, self.now - 500)
        probe = lambda cfg, run: {"rtt": 18.0}
        with patch.object(healthcheck, "RUNTIME", self.runtime):
            ok, reason = healthcheck.check(self.data, runner, probe, self.now)
        self.assertEqual((ok, reason), (False, "stale-handshake"))

    def test_check_without_saved_config(self):
        (self.runtime / "omawg0.conf").unlink()
        with patch.object(healthcheck, "RUNTIME", self.runtime):
            ok, reason = healthcheck.check(self.data, lambda *a, **k: "", None, self.now)
        self.assertEqual((ok, reason), (False, "no-saved-config"))


if __name__ == "__main__":
    unittest.main()

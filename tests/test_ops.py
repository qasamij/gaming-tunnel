import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ops


class OpsTests(unittest.TestCase):
    def test_endpoint_and_obfuscation_rewrite(self):
        text = "Jc = 3\nH1 = 1\nEndpoint = 192.0.2.1:12\n"
        out = ops.endpoint_config(text, "198.51.100.2", "5204",
                                  {"Jc": 8, "H1": 999})
        self.assertIn("Endpoint = 198.51.100.2:5204", out)
        self.assertIn("Jc = 8", out)
        self.assertIn("H1 = 999", out)

    def test_settings_merge_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "network.json").write_text(json.dumps({
                "endpoint": "192.0.2.10", "network": "10.9.0.0/24",
                "probe_host": "10.9.0.1",
            }))
            s = ops.settings(d)
            self.assertEqual(s["network"], "10.9.0.0/24")
            self.assertEqual(s["probe_port"], 5355)
            self.assertEqual(s["table"], 179)
            self.assertEqual(s["probe_host"], "10.9.0.1")

    def test_repair_uses_dedicated_table(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "network.json").write_text(json.dumps({
                "endpoint": "192.0.2.1", "network": "10.7.0.0/24",
            }))
            with patch("ops.checked", return_value="") as checked, \
                 patch("ops.diagnostics", return_value="OK"):
                self.assertEqual(ops.repair(d), "OK")
                checked.assert_any_call(
                    "ip", "route", "replace", "10.7.0.0/24",
                    "dev", "omclient0", "table", "179")


if __name__ == "__main__":
    unittest.main()

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import awgdetect

KEY = "A" * 43 + "="


class FakeRun:
    """Return canned (rc, output) per argv prefix; record every call."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __call__(self, args, input_text=None, timeout=10):
        self.calls.append((list(args), input_text, timeout))
        for command, value in self.responses.items():
            if command[0] in args[1:]:
                return value
        return 0, ""


class AwgDetectTests(unittest.TestCase):
    def test_valid_key(self):
        self.assertTrue(awgdetect.valid_key(KEY + "\n"))
        self.assertFalse(awgdetect.valid_key("short"))
        self.assertFalse(awgdetect.valid_key(""))

    def test_candidate_order(self):
        with patch.dict(os.environ, {"AWG_BIN": "/custom/awg"}):
            with patch.object(awgdetect.shutil, "which",
                              side_effect=lambda name: "/bin/" + name):
                out = awgdetect.candidates(which=lambda name: "/bin/" + name)
        self.assertEqual(out[:3], ["/custom/awg", "/usr/local/bin/awg", "/bin/awg"])
        self.assertIn("/bin/wg", out)

    def test_go_candidates_accepts_renamed_engine(self):
        with patch.object(awgdetect.os.path, "exists", return_value=True), \
             patch.object(awgdetect.shutil, "which",
                          side_effect=lambda name: "/bin/" + name):
            values = awgdetect.go_candidates()
        self.assertTrue(values[0].endswith("amneziawg-go"))
        self.assertIn("/bin/awg-go", values)

    def test_basic_probe(self):
        run = FakeRun({
            ("genkey",): (0, KEY + "\n"),
            ("pubkey",): (0, KEY + "\n"),
        })
        ok, private = awgdetect.basic_probe("/usr/bin/wg", run)
        self.assertTrue(ok)
        self.assertEqual(private, KEY)

    def test_basic_probe_rejects_bad_key(self):
        run = FakeRun({("genkey",): (0, "not-a-key")})
        ok, _ = awgdetect.basic_probe("/usr/bin/wg", run)
        self.assertFalse(ok)

    def test_amnezia_probe_uses_obfuscation_and_cleans_up(self):
        run = FakeRun({
            ("genkey",): (0, KEY),
            ("pubkey",): (0, KEY),
            ("setconf",): (0, ""),
            ("show",): (0, KEY),
        })
        events = []

        def create(iface):
            events.append("create:" + iface)
            return True

        def cleanup(iface):
            events.append("cleanup:" + iface)

        seen = {}

        def recording(args, input_text=None, timeout=10):
            if "setconf" in args:
                seen["conf"] = Path(args[3]).read_text()
            return run(args, input_text, timeout)

        ok, detail = awgdetect.amnezia_probe("/usr/bin/wg", recording,
                                            create, cleanup, "test0")
        self.assertTrue(ok, detail)
        self.assertEqual(events, ["create:test0", "cleanup:test0"])
        self.assertIn("Jc = 3", seen["conf"])
        self.assertIn("H4 = 4", seen["conf"])

    def test_amnezia_probe_rejects_plain_wireguard(self):
        run = FakeRun({
            ("genkey",): (0, KEY),
            ("pubkey",): (0, KEY),
            ("setconf",): (1, "Line unrecognized: `Jc = 3'"),
        })
        ok, detail = awgdetect.amnezia_probe("/usr/bin/wg", run,
                                            lambda i: True, lambda i: None)
        self.assertFalse(ok)
        self.assertIn("obfuscation", detail)

    def test_detect_prefers_verified_wg_over_broken_awg(self):
        responses = {
            ("genkey",): (0, KEY),
            ("pubkey",): (0, KEY),
        }
        broken = FakeRun(dict(responses))
        broken.responses[("setconf",)] = (1, "Line unrecognized: `Jc = 3'")
        good = FakeRun(dict(responses))
        good.responses[("setconf",)] = (0, "")
        good.responses[("show",)] = (0, KEY)

        def run(args, input_text=None, timeout=10):
            candidate = broken if args[0].endswith("awg") else good
            return candidate(args, input_text, timeout)

        with patch.dict(os.environ, {}, clear=True):
            result = awgdetect.detect(
                which=lambda name: "/usr/local/bin/awg" if name == "awg" else None,
                run=run, create=lambda i: True, cleanup=lambda i: None)
        self.assertTrue(result["verified"])
        self.assertTrue(result["binary"].endswith("/wg"))

    @unittest.skipIf(os.name == "nt", "symlinks need extra privileges on Windows")
    def test_ensure_link_is_atomic_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "real-wg"
            target.write_text("binary")
            link = Path(tmp) / "awg"
            awgdetect.ensure_link(str(target), str(link))
            self.assertTrue(link.is_symlink())
            self.assertEqual(os.readlink(str(link)), str(target))
            awgdetect.ensure_link(str(target), str(link))
            self.assertEqual(os.readlink(str(link)), str(target))


if __name__ == "__main__":
    unittest.main()

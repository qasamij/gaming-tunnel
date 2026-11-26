import os
import tempfile
import time
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
        tail = list(args[1:])
        for command, value in self.responses.items():
            if all(part in tail for part in command):
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
                run=run, create=lambda i: True, cleanup=lambda i: None,
                iface="awgchktest")
        self.assertTrue(result["verified"])
        self.assertTrue(result["binary"].endswith("/wg"))

    def test_interface_existence_check(self):
        run = FakeRun({("show",): (0, "3: omawg0: <POINTOPOINT>")})
        self.assertTrue(awgdetect.interface_exists("omawg0", run))
        self.assertFalse(awgdetect.interface_exists("awgchk0", FakeRun({})))

    def test_unique_iface_rejects_names_already_in_use(self):
        taken = {"awgchk" + "a" * 6}
        name = awgdetect.unique_iface(exists=lambda value: value in taken)
        self.assertTrue(name.startswith("awgchk"))
        self.assertLessEqual(len(name), 15)
        self.assertNotIn(name, taken)

    def test_create_test_iface_needs_the_link_to_appear(self):
        run = FakeRun({("add",): (0, ""), ("show",): (0, "")})
        with patch.object(awgdetect, "find_go", return_value=""):
            self.assertFalse(awgdetect.create_test_iface("awgchk0", run))
        run = FakeRun({("add",): (0, ""), ("show",): (0, "9: awgchk0: <POINTOPOINT>")})
        with patch.object(awgdetect, "find_go", return_value=""):
            self.assertTrue(awgdetect.create_test_iface("awgchk0", run))

    def test_detect_uses_one_shared_interface_and_removes_it_once(self):
        responses = {("genkey",): (0, KEY), ("pubkey",): (0, KEY)}
        broken = FakeRun(dict(responses))
        broken.responses[("setconf",)] = (1, "Line unrecognized: `Jc = 3'")
        good = FakeRun(dict(responses))
        good.responses[("setconf",)] = (0, "")
        good.responses[("show", "private-key")] = (0, KEY)

        def run(args, input_text=None, timeout=10):
            candidate = broken if args[0].endswith("awg") else good
            return candidate(args, input_text, timeout)

        created, removed = [], []

        with patch.dict(os.environ, {}, clear=True), \
             patch.object(awgdetect, "unique_iface", return_value="awgchk123"):
            result = awgdetect.detect(
                which=lambda name: "/usr/local/bin/awg" if name == "awg" else None,
                run=run,
                create=lambda name: created.append(name) or True,
                cleanup=lambda name: removed.append(name))
        self.assertTrue(result["verified"])
        self.assertEqual(created, ["awgchk123"])
        self.assertEqual(removed, ["awgchk123"])

    def test_detect_does_not_delete_an_interface_it_did_not_create(self):
        removed = []
        result = awgdetect.detect(
            which=lambda name: None,
            run=FakeRun({}), create=lambda name: False,
            cleanup=lambda name: removed.append(name), iface="omawg0")
        self.assertFalse(result["verified"])
        self.assertEqual(removed, [])

    def test_marker_cache_expires_and_can_be_forced(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "awg.verified"
            awgdetect.write_marker("/usr/bin/wg", str(marker))
            self.assertEqual(awgdetect.read_marker(str(marker)), "/usr/bin/wg")
            marker.write_text("{} /usr/bin/wg\n".format(int(time.time()) - 90000))
            self.assertEqual(awgdetect.read_marker(str(marker)), "")

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

"""Find a *working* AmneziaWG CLI and expose it as ``awg``.

Some builds of amneziawg-tools install the binary as ``wg`` instead of
``awg``. Checking ``command -v awg`` is therefore not enough: the file may be
absent, or it may be a plain WireGuard binary that rejects AmneziaWG's
obfuscation keys. This module verifies a candidate by actually creating a
throwaway interface and applying an obfuscated config to it, then (optionally)
creates a stable ``/usr/local/bin/awg`` symlink so every caller uses the same
verified tool.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess as sp
import sys
import tempfile
from pathlib import Path

KEY_RE = re.compile(r"^[A-Za-z0-9+/]{43}=$")
DEFAULT_LINK = "/usr/local/bin/awg"
GO_LINK = "/usr/local/bin/amneziawg-go"
GO_NAMES = ("amneziawg-go", "awg-go", "wg-go")
TEST_IFACE = "awgchk0"
OBFUSCATION = {"Jc": 3, "Jmin": 40, "Jmax": 70, "S1": 32, "S2": 48,
               "H1": 1, "H2": 2, "H3": 3, "H4": 4}


def execute(args, input_text=None, timeout=10):
    """Run argv directly (never through a shell); return (rc, stdout+stderr)."""
    try:
        p = sp.run(args, input=input_text, text=True, stdout=sp.PIPE,
                   stderr=sp.STDOUT, timeout=timeout, check=False)
        return p.returncode, p.stdout.strip()
    except (OSError, sp.TimeoutExpired) as exc:
        return 127, str(exc)


def valid_key(text):
    lines = str(text or "").strip().splitlines()
    return bool(lines) and bool(KEY_RE.fullmatch(lines[-1].strip()))


def candidates(explicit=None, which=None):
    """Ordered binary candidates: explicit first, awg names before wg names."""
    which = which or shutil.which
    out = []
    for value in (explicit, os.getenv("AWG_BIN"), "/usr/local/bin/awg",
                  which("awg"), "/usr/bin/awg", "/usr/local/bin/wg",
                  which("wg"), "/usr/bin/wg"):
        if value and value not in out:
            out.append(value)
    return out


def basic_probe(binary, run=execute):
    """Check that the candidate can generate and derive a key."""
    rc, out = run([binary, "genkey"], timeout=10)
    if rc != 0 or not valid_key(out):
        return False, "genkey failed"
    key = out.strip().splitlines()[-1].strip()
    rc, pub = run([binary, "pubkey"], input_text=key + "\n", timeout=10)
    if rc != 0 or not valid_key(pub):
        return False, "pubkey failed"
    return True, key


def go_candidates(which=None):
    """Possible names of the userspace AmneziaWG engine binary."""
    which = which or shutil.which
    out = []
    for name in GO_NAMES:
        for value in ("/usr/local/bin/" + name, "/usr/bin/" + name, which(name)):
            if value and os.path.exists(value) and value not in out:
                out.append(value)
    return out


def find_go(which=None):
    values = go_candidates(which)
    return values[0] if values else ""


def default_create(iface):
    go = find_go()
    if go:
        rc, _out = execute([go, iface], timeout=10)
        if rc == 0:
            return True
    rc, _out = execute(["ip", "link", "add", iface, "type", "wireguard"], timeout=10)
    return rc == 0


def default_cleanup(iface):
    execute(["ip", "link", "del", iface], timeout=10)


def config_text(private):
    lines = ["[Interface]", "PrivateKey = " + private, "ListenPort = 0"]
    lines += ["{} = {}".format(k, v) for k, v in OBFUSCATION.items()]
    return "\n".join(lines) + "\n"


def amnezia_probe(binary, run=execute, create=None, cleanup=None, iface=TEST_IFACE):
    """Prove the candidate accepts AmneziaWG obfuscation keys on a real link."""
    ok, private = basic_probe(binary, run)
    if not ok:
        return False, private
    if not (create or default_create)(iface):
        return False, "cannot create a test interface"
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as handle:
            handle.write(config_text(private))
            path = handle.name
        try:
            os.chmod(path, 0o600)
            rc, out = run([binary, "setconf", iface, path], timeout=10)
            if rc != 0:
                return False, "setconf rejected obfuscation keys: " + out[:160]
            rc, shown = run([binary, "show", iface, "private-key"], timeout=10)
            if rc != 0 or shown.strip() != private:
                return False, "show private-key mismatch"
            return True, "verified with obfuscation keys"
        finally:
            os.unlink(path)
    finally:
        (cleanup or default_cleanup)(iface)


def detect(explicit=None, run=execute, which=None, create=None, cleanup=None):
    """Return ``{'binary': path, 'verified': bool, 'detail': str}``."""
    fallback = None
    for binary in candidates(explicit, which):
        ok, detail = basic_probe(binary, run)
        if not ok:
            continue
        verified, detail = amnezia_probe(binary, run, create, cleanup)
        if verified:
            return {"binary": binary, "verified": True, "detail": detail}
        if fallback is None:
            fallback = {"binary": binary, "verified": False, "detail": detail}
    return fallback or {"binary": "", "verified": False,
                        "detail": "no working AmneziaWG CLI found"}


def ensure_link(binary, link=DEFAULT_LINK):
    """Atomically point ``link`` at the verified binary."""
    target = os.path.realpath(binary)
    if os.path.islink(link) and os.path.realpath(link) == target:
        return True
    if os.path.isfile(link) and os.path.realpath(link) == target:
        return True
    tmp = link + ".tmp-1mobile"
    if os.path.lexists(tmp):
        os.unlink(tmp)
    os.symlink(binary, tmp)
    os.replace(tmp, link)
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--explicit", default=None, help="force a candidate binary")
    parser.add_argument("--link", action="store_true",
                        help="create /usr/local/bin/awg pointing at the verified binary")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    result = detect(args.explicit)
    if not result["verified"]:
        print("awgdetect: " + result["detail"], file=sys.stderr)
        return 1
    if args.link:
        try:
            ensure_link(result["binary"])
            go = find_go()
            if go:
                ensure_link(go, GO_LINK)
        except OSError as exc:
            print("awgdetect: could not install tool symlinks: " + str(exc), file=sys.stderr)
            return 1
        # Test the final path itself, not merely the symlink target.
        result = detect(explicit=DEFAULT_LINK)
        if not result["verified"]:
            print("awgdetect: final awg check failed: " + result["detail"], file=sys.stderr)
            return 1
    if not args.quiet:
        print(result["binary"])
    return 0


if __name__ == "__main__":
    sys.exit(main())

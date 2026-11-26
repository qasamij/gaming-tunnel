"""Find a *working* AmneziaWG CLI and expose it as ``awg``.

Some builds of amneziawg-tools install the binary as ``wg`` instead of
``awg``. Checking ``command -v awg`` is therefore not enough: the file may be
absent, or it may be a plain WireGuard binary that rejects AmneziaWG's
obfuscation keys.

Safety rules for the temporary test link:

* the name is random and checked to be free before creation;
* only a link that *we* created is ever deleted;
* at most one throwaway link exists during a full detection, and all
  candidates share it;
* a successful verification is cached, so later scripts need no link at all.
"""

from __future__ import annotations

import argparse
import os
import re
import secrets
import shutil
import subprocess as sp
import sys
import tempfile
import time
from pathlib import Path

KEY_RE = re.compile(r"^[A-Za-z0-9+/]{43}=$")
DEFAULT_LINK = "/usr/local/bin/awg"
GO_LINK = "/usr/local/bin/amneziawg-go"
GO_NAMES = ("amneziawg-go", "awg-go", "wg-go")
MARKER = os.getenv("AWG_VERIFY_MARKER", "/etc/1mobile-runtime/awg.verified")
CACHE_TTL = 86400                    # 24 hours
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
    """Check that the candidate can generate and derive a key (no link)."""
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


def interface_exists(iface, run=execute):
    rc, out = run(["ip", "link", "show", iface], timeout=5)
    return rc == 0 and bool(out.strip())


def unique_iface(prefix="awgchk", run=execute, exists=None):
    """Pick an unused, kernel-legal interface name; empty when none is free."""
    checker = exists or (lambda name: interface_exists(name, run))
    for _ in range(20):
        name = prefix + secrets.token_hex(3)   # <= 15 characters
        if not checker(name):
            return name
    return ""


def create_test_iface(iface, run=execute, go=None):
    """Create a throwaway link; return True only if it really appeared."""
    go = go or find_go()
    if go:
        rc, _out = run([go, iface], timeout=10)
        if rc == 0 and interface_exists(iface, run):
            return True
    rc, _out = run(["ip", "link", "add", iface, "type", "wireguard"], timeout=10)
    return rc == 0 and interface_exists(iface, run)


def delete_test_iface(iface, run=execute):
    run(["ip", "link", "del", iface], timeout=10)


def default_create(iface):
    return create_test_iface(iface)


def default_cleanup(iface):
    delete_test_iface(iface)


def config_text(private):
    lines = ["[Interface]", "PrivateKey = " + private, "ListenPort = 0"]
    lines += ["{} = {}".format(k, v) for k, v in OBFUSCATION.items()]
    return "\n".join(lines) + "\n"


def amnezia_probe(binary, run=execute, create=None, cleanup=None,
                  iface=None, private=None):
    """Prove the candidate accepts AmneziaWG obfuscation keys on a real link.

    ``create``/``cleanup`` are injectable for tests. ``cleanup`` runs only
    after a successful creation, so an existing interface is never removed.
    """
    if private is None:
        ok, private = basic_probe(binary, run)
        if not ok:
            return False, private
    name = iface or unique_iface(run=run)
    if not name:
        return False, "no free throwaway interface name"
    if not (create or default_create)(name):
        return False, "cannot create a test interface"
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as handle:
            handle.write(config_text(private))
            path = handle.name
        try:
            os.chmod(path, 0o600)
            rc, out = run([binary, "setconf", name, path], timeout=10)
            if rc != 0:
                return False, "setconf rejected obfuscation keys: " + out[:160]
            rc, shown = run([binary, "show", name, "private-key"], timeout=10)
            if rc != 0 or shown.strip() != private:
                return False, "show private-key mismatch"
            return True, "verified with obfuscation keys"
        finally:
            os.unlink(path)
    finally:
        (cleanup or default_cleanup)(name)


def detect(explicit=None, run=execute, which=None, create=None, cleanup=None, iface=None):
    """Return ``{'binary': path, 'verified': bool, 'detail': str}``.

    All cheap key probes run first. Only candidates that pass get a single
    shared throwaway interface, which is removed exactly once in ``finally``.
    """
    basics = []
    for binary in candidates(explicit, which):
        ok, key = basic_probe(binary, run)
        if ok:
            basics.append((binary, key))
    if not basics:
        return {"binary": "", "verified": False,
                "detail": "no working AmneziaWG CLI found"}

    name = iface or unique_iface(run=run)
    if not name:
        return {"binary": "", "verified": False,
                "detail": "no free throwaway interface name"}
    creator = create or (lambda value: create_test_iface(value, run))
    remover = cleanup or (lambda value: delete_test_iface(value, run))
    owned = False
    fallback = None
    try:
        if not creator(name):
            return {"binary": "", "verified": False,
                    "detail": "cannot create a throwaway interface"}
        owned = True
        for binary, key in basics:
            verified, detail = amnezia_probe(binary, run, lambda i: True,
                                             lambda i: None, name, private=key)
            if verified:
                return {"binary": binary, "verified": True, "detail": detail}
            if fallback is None:
                fallback = {"binary": binary, "verified": False, "detail": detail}
        return fallback or {"binary": "", "verified": False,
                            "detail": "no verified AmneziaWG CLI"}
    finally:
        if owned:
            remover(name)


def read_marker(marker=None):
    """Return a recently verified binary path, or an empty string."""
    try:
        parts = Path(marker or MARKER).read_text().strip().split()
        if len(parts) >= 2 and abs(time.time() - int(parts[0])) <= CACHE_TTL:
            return parts[1]
    except (OSError, ValueError):
        pass
    return ""


def write_marker(binary, marker=None):
    """Persist a successful verification so later calls avoid creating a link."""
    try:
        path = Path(marker or MARKER)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text("{} {}\n".format(int(time.time()), binary))
        tmp.replace(path)
    except OSError:
        pass


def ensure_link(binary, link=DEFAULT_LINK):
    """Atomically point ``link`` at the verified binary."""
    target = os.path.realpath(binary)
    if os.path.exists(link) and os.path.realpath(link) == target:
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
    parser.add_argument("--no-cache", action="store_true",
                        help="repeat the full functional test even if cached")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    cached = "" if args.no_cache else read_marker()
    if cached and basic_probe(cached)[0]:
        result = {"binary": cached, "verified": True, "detail": "cached verification"}
    else:
        result = detect(args.explicit)
        if result["verified"]:
            write_marker(result["binary"])

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
        # The binary behind this link was already verified (now or via the
        # cache). Check the final path itself, but do NOT create a second
        # throwaway interface: low-memory hosts only ever see one link.
        ok, _key = basic_probe(DEFAULT_LINK)
        if not ok:
            print("awgdetect: final awg check failed", file=sys.stderr)
            return 1
        write_marker(DEFAULT_LINK)
        result = {"binary": DEFAULT_LINK, "verified": True, "detail": "link verified"}
    if not args.quiet:
        print(result["binary"])
    return 0


if __name__ == "__main__":
    sys.exit(main())

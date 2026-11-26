"""Supervisor-side tunnel health check.

The supervisor originally only noticed a *missing* interface. This module
also checks that the tunnel peer has a fresh handshake and, where an echo
responder is configured (Iran), that a real end-to-end UDP round trip works.
It is called by the root-owned supervisor, never from an HTTP request.
"""

from __future__ import annotations

import os
import re
import subprocess as sp
import sys
import time
from pathlib import Path

import monitor
import ops

STALE = int(os.getenv("STALE_HANDSHAKE", "300"))
RUNTIME = Path(os.getenv("RUNTIME_DATA", "/etc/1mobile-runtime"))
AWG = os.getenv("AWG_BIN", "/usr/local/bin/awg")


def peer_pubkey(conf_text):
    match = re.search(r"(?m)^PublicKey\s*=\s*(\S+)", str(conf_text))
    return match.group(1) if match else ""


def handshake_age(handshakes_text, pub, now=None):
    """Seconds since ``pub``'s last handshake, or None when not found."""
    now = time.time() if now is None else now
    for line in str(handshakes_text).splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == pub:
            try:
                return max(0, int(now) - int(parts[1]))
            except (TypeError, ValueError):
                return None
    return None


def assess(age, probe_ok, stale=STALE):
    """Return ``(healthy, reason)``; probe_ok=None means not configured."""
    if age is None:
        return False, "no-handshake"
    if age > stale:
        return False, "stale-handshake"
    if probe_ok is False:
        return False, "probe-failed"
    return True, "ok"


def check(data_dir=None, run=None, probe=None, now=None):
    """Read saved settings and report ``(healthy, reason)``."""
    data_dir = Path(data_dir or os.getenv("PANEL_DATA", "/etc/1mobile-panel"))
    runner = run or run_command
    cfg = ops.settings(str(data_dir))
    iface = str(cfg.get("tunnel", "omawg0"))
    conf_path = RUNTIME / (iface + ".conf")
    if not conf_path.is_file():
        return False, "no-saved-config"

    pub = peer_pubkey(conf_path.read_text())
    if not pub:
        return False, "no-peer-key"

    try:
        handshakes = runner(AWG, "show", iface, "latest-handshakes")
        age = handshake_age(handshakes, pub, now)
    except Exception:
        age = None

    probe_ok = None
    if cfg.get("probe_host"):
        try:
            result = (probe or monitor.probe_once)(cfg, runner)
            probe_ok = result.get("rtt") is not None
        except Exception:
            probe_ok = False

    healthy, reason = assess(age, probe_ok, STALE)
    print("healthcheck: {} (handshake={}s probe={})".format(reason, age, probe_ok))
    return healthy, reason


def run_command(*args, timeout=15):
    return sp.check_output(
        args, text=True, stderr=sp.STDOUT, timeout=timeout
    ).strip()


if __name__ == "__main__":
    ok, _reason = check()
    sys.exit(0 if ok else 1)

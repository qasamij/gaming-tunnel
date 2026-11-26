"""System/routing helpers for the 1Mobile gaming tunnel panel.

All commands are executed with an explicit argument list (never a shell), so
user-supplied values cannot be interpreted as shell metacharacters.
"""

from __future__ import annotations

import ipaddress
import json
import re
import subprocess as sp
from pathlib import Path

# Defaults are merged with network.json so older installations keep working.
DEFAULTS = {
    "endpoint": "127.0.0.1",
    "network": "10.0.0.0/24",
    "table": 179,
    "priority": 10790,
    "client": "omclient0",
    "tunnel": "omawg0",
    "probe_host": "",
    "probe_port": 5355,
    "probe_interval": 5,
    "probe_timeout": 1.0,
    "obfuscation": {
        "Jc": 3,
        "Jmin": 40,
        "Jmax": 70,
        "S1": 32,
        "S2": 48,
        "H1": 123456789,
        "H2": 234567891,
        "H3": 345678912,
        "H4": 456789123,
    },
}

OBFUSCATION_KEYS = tuple(DEFAULTS["obfuscation"].keys())


def call(*args, timeout=12):
    """Run a command safely and return (returncode, combined_output)."""
    try:
        p = sp.run(
            args,
            text=True,
            stdout=sp.PIPE,
            stderr=sp.STDOUT,
            timeout=timeout,
            check=False,
        )
        return p.returncode, p.stdout.strip()
    except FileNotFoundError:
        return 127, "command not found: " + str(args[0])
    except sp.TimeoutExpired:
        return 124, "timeout: " + " ".join(str(a) for a in args)


def checked(*args, timeout=12):
    rc, out = call(*args, timeout=timeout)
    if rc:
        raise ValueError("Command failed: " + " ".join(str(a) for a in args) + " " + out[:300])
    return out


def settings(data_dir):
    """Return validated settings with defaults applied."""
    d = Path(data_dir)
    raw = {}
    p = d / "network.json"
    if p.is_file():
        raw = json.loads(p.read_text())

    s = dict(DEFAULTS)
    s.update({k: v for k, v in raw.items() if k != "obfuscation"})
    obf = dict(DEFAULTS["obfuscation"])
    obf.update(raw.get("obfuscation", {}))
    s["obfuscation"] = obf

    s["endpoint"] = str(ipaddress.IPv4Address(s["endpoint"]))
    s["network"] = str(ipaddress.IPv4Network(s["network"]))
    s["table"] = int(s["table"])
    s["priority"] = int(s["priority"])
    s["probe_port"] = int(s["probe_port"])
    s["probe_interval"] = max(1, int(s["probe_interval"]))
    s["probe_timeout"] = min(3.0, max(0.1, float(s["probe_timeout"])))
    for key in OBFUSCATION_KEYS:
        s["obfuscation"][key] = int(s["obfuscation"][key])
    return s


def endpoint_config(text, endpoint, port, obfuscation=None):
    """Rewrite Endpoint and (optionally) AmneziaWG obfuscation values."""
    out = re.sub(
        r"(?m)^Endpoint\s*=.*$",
        "Endpoint = {}:{}".format(endpoint, port),
        text,
    )
    if obfuscation:
        for key in OBFUSCATION_KEYS:
            if key in obfuscation:
                out = re.sub(
                    r"(?m)^" + re.escape(key) + r"\s*=.*$",
                    "{} = {}".format(key, int(obfuscation[key])),
                    out,
                )
    return out


def diagnostics():
    commands = [
        ("ip", "-br", "addr"),
        ("ip", "rule", "show"),
        ("ip", "route", "show", "table", "all"),
        ("sysctl", "net.ipv4.ip_forward"),
        ("iptables", "-S"),
        ("iptables", "-t", "nat", "-S"),
        ("awg", "show", "omawg0"),
        ("awg", "show", "omclient0"),
        ("systemctl", "is-active", "1mobile-runtime"),
        ("systemctl", "is-active", "1mobile-panel"),
    ]
    blocks = []
    for args in commands:
        rc, out = call(*args)
        blocks.append("$ " + " ".join(args) + "\n" + (out or "(no output)"))
    return "\n\n".join(blocks)


def repair(data_dir):
    """Restore the dedicated Iran routing table. Never touches firewall/NAT."""
    s = settings(data_dir)
    net = s["network"]
    table = str(s["table"])
    priority = str(s["priority"])
    client = s["client"]
    tunnel = s["tunnel"]

    checked("ip", "link", "show", client)
    checked("ip", "link", "show", tunnel)

    rules = checked("ip", "rule", "show")
    matching = [line for line in rules.splitlines() if line.startswith(priority + ":")]
    wanted = "from {} lookup {}".format(net, table)
    if matching and not any(wanted in line for line in matching):
        raise ValueError("Policy priority already occupied")

    checked("sysctl", "-w", "net.ipv4.ip_forward=1")
    checked("ip", "route", "replace", "unreachable", "default", "metric", "32767", "table", table)
    checked("ip", "route", "replace", net, "dev", client, "table", table)
    checked("ip", "route", "replace", "default", "dev", tunnel, "metric", "0", "table", table)
    if not matching:
        checked("ip", "rule", "add", "priority", priority, "from", net, "lookup", table)
    return diagnostics()

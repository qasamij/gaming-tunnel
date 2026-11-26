"""Dependency-free helpers for importing AmneziaWG keys.

Used by ``scripts/keys.sh`` so that key validation and config rewriting can be
unit-tested without bash. No third-party dependencies: a WG key is simply
32 raw bytes encoded as 44 base64 characters (the last one is ``=``).
"""

import base64
import copy
import ipaddress
import json
import re
import secrets
from pathlib import Path

_KEY_RE = re.compile(r"^[A-Za-z0-9+/]{43}=$")
OBFUSCATION_KEYS = ("Jc", "Jmin", "Jmax", "S1", "S2", "H1", "H2", "H3", "H4")
SHARED_PREFIX = "OMAWG_SHARED="
SHARED_DEFAULTS = {
    "endpoint": "0.0.0.0",
    "network": "10.7.0.0/24",
    "table": 179,
    "priority": 10790,
    "client": "omclient0",
    "tunnel": "omawg0",
    "probe_host": "",
    "probe_port": 5355,
    "probe_interval": 5,
    "probe_timeout": 1.0,
    "obfuscation": {
        "Jc": 3, "Jmin": 40, "Jmax": 70, "S1": 32, "S2": 48,
        "H1": 0, "H2": 0, "H3": 0, "H4": 0,
    },
}


def clean_key(value):
    """Validate and normalise a WireGuard/AmneziaWG key string."""
    text = str(value).strip()
    if not _KEY_RE.fullmatch(text):
        raise ValueError("کلید باید دقیقاً ۴۴ کاراکتر Base64 باشد")
    try:
        raw = base64.b64decode(text, validate=True)
    except Exception:
        raise ValueError("کلید معتبری نیست")
    if len(raw) != 32:
        raise ValueError("کلید باید ۳۲ بایت باشد")
    return text


def rewrite_conf(text, private=None, peer_public=None):
    """Replace PrivateKey and/or the [Peer] PublicKey in a saved config.

    The config keeps all its other lines (Address, ListenPort, obfuscation,
    AllowedIPs, Endpoint, ...) intact, so importing a key never loses the
    routing/pairing information that makes the tunnel survive a reboot.
    """
    out = str(text)
    if private is not None:
        private = clean_key(private)
        if not re.search(r"(?m)^PrivateKey\s*=", out):
            raise ValueError("خط PrivateKey در کانفیگ وجود ندارد")
        out = re.sub(r"(?m)^PrivateKey\s*=.*$",
                     "PrivateKey = " + private, out, count=1)
    if peer_public is not None:
        peer_public = clean_key(peer_public)
        if not re.search(r"(?m)^PublicKey\s*=", out):
            raise ValueError("خط PublicKey مربوط به Peer در کانفیگ وجود ندارد")
        out = re.sub(r"(?m)^PublicKey\s*=.*$",
                     "PublicKey = " + peer_public, out, count=1)
    return out


def merge_peers(base_text, live_text):
    """Append live [Peer] blocks missing from ``base_text``.

    ``awg setconf`` replaces the whole peer list. When we re-apply a saved
    config to a *live* interface we must not silently delete clients that
    were added by the panel after that config was saved.
    """
    def peer_blocks(text):
        blocks, current = [], []
        for line in str(text).splitlines():
            stripped = line.strip()
            if stripped == "[Peer]":
                if current:
                    blocks.append(current)
                current = [line]
            elif stripped.startswith("[") and stripped.endswith("]"):
                if current:
                    blocks.append(current)
                    current = []
            elif current:
                current.append(line)
        if current:
            blocks.append(current)
        return blocks

    def pubkey_of(block):
        match = re.search(r"(?m)^PublicKey\s*=\s*(\S+)", "\n".join(block))
        return match.group(1) if match else None

    base = str(base_text)
    known = {p for p in (pubkey_of(b) for b in peer_blocks(base)) if p}
    additions = []
    for block in peer_blocks(live_text):
        pub = pubkey_of(block)
        if pub and pub not in known:
            additions.append("\n".join(block).strip("\n"))
            known.add(pub)
    if not additions:
        return base
    return base.rstrip("\n") + "\n\n" + "\n\n".join(additions) + "\n"


def obfuscation_lines(value):
    """Normalise obfuscation values into one ``Key = value`` line per key.

    Accepts either the ``obfuscation`` dict from network.json or a pasted
    string such as ``Jc=3 Jmin = 40 H1=123 ...``. This is deliberately not
    produced by ``tr ' ' '\\n'``: that would split ``Jc = 3`` into three
    separate lines, which AmneziaWG cannot parse.
    """
    if isinstance(value, dict):
        found = {str(k).strip().upper(): v for k, v in value.items()}
    else:
        text = str(value)
        pairs = re.findall(r"([A-Za-z][A-Za-z0-9]*)\s*=\s*(\d+)", text)
        found = {k.upper(): v for k, v in pairs}
    missing = [k for k in OBFUSCATION_KEYS if k.upper() not in found]
    if missing:
        raise ValueError("مقادیر مبهمسازی ناقصاند: " + ", ".join(missing))
    lines = []
    for key in OBFUSCATION_KEYS:
        try:
            number = int(found[key.upper()])
        except (TypeError, ValueError):
            raise ValueError("مقدار نامعتبر برای " + key)
        lines.append("{} = {}".format(key, number))
    return "\n".join(lines)


def new_shared_config(junk_count=3):
    """Build the settings both servers and all clients must share.

    This is deliberately a separate, offline step: `fresh exit` used to need
    obfuscation values that `fresh iran` had not generated yet.
    """
    cfg = copy.deepcopy(SHARED_DEFAULTS)
    try:
        junk = int(junk_count)
    except (TypeError, ValueError):
        raise ValueError("JUNK_COUNT باید عدد باشد")
    if junk < 0:
        raise ValueError("JUNK_COUNT نمیتواند منفی باشد")
    cfg["obfuscation"]["Jc"] = junk
    for key in ("H1", "H2", "H3", "H4"):
        cfg["obfuscation"][key] = secrets.randbelow(0xFFFFFFFF) + 1
    return cfg


def shared_line(cfg):
    """Encode a shared config into one copy-pasteable line."""
    raw = json.dumps(cfg, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return SHARED_PREFIX + base64.b64encode(raw).decode("ascii")


def parse_shared_line(line):
    """Decode and validate a line produced by :func:`shared_line`."""
    text = str(line or "").strip()
    if text.startswith(SHARED_PREFIX):
        text = text[len(SHARED_PREFIX):]
    try:
        cfg = json.loads(base64.b64decode(text, validate=True).decode("utf-8"))
    except Exception:
        raise ValueError("خط تنظیمات مشترک نامعتبر است")
    if not isinstance(cfg, dict):
        raise ValueError("تنظیمات مشترک باید یک شیء JSON باشد")
    obfuscation_lines(cfg.get("obfuscation"))
    if "network" in cfg:
        try:
            ipaddress.IPv4Network(str(cfg["network"]), strict=False)
        except ValueError:
            raise ValueError("سابنت تنظیمات مشترک نامعتبر است")
    return cfg


def write_shared_config(cfg, path):
    """Atomically store the shared config as `network.json`."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(cfg, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(target)


def read_shared_config(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


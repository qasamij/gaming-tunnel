"""Dependency-free helpers for importing AmneziaWG keys.

Used by ``scripts/keys.sh`` so that key validation and config rewriting can be
unit-tested without bash. No third-party dependencies: a WG key is simply
32 raw bytes encoded as 44 base64 characters (the last one is ``=``).
"""

import base64
import re

_KEY_RE = re.compile(r"^[A-Za-z0-9+/]{43}=$")
OBFUSCATION_KEYS = ("Jc", "Jmin", "Jmax", "S1", "S2", "H1", "H2", "H3", "H4")


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

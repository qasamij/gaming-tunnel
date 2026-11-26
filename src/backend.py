"""User management, accounting and safe command wrappers.

State lives in /etc/1mobile-panel (override with PANEL_DATA for tests).
Every write is atomic: write a sibling .tmp file then os.replace().
"""

from __future__ import annotations

import base64
import html
import ipaddress
import json
import os
import re
import secrets
import shutil
import subprocess as sp
import threading
import time
from pathlib import Path

import monitor
import ops

VERSION = "1.4.0"
os.umask(0o077)

D = Path(os.getenv("PANEL_DATA", "/etc/1mobile-panel"))
D.mkdir(mode=0o700, parents=True, exist_ok=True)
DB = D / "users.json"
CLIENT = Path(os.getenv("CLIENT_DATA", "/etc/1mobile-client"))
RUNTIME = Path(os.getenv("RUNTIME_DATA", "/etc/1mobile-runtime"))
AWG = os.getenv("AWG_BIN", "/usr/local/bin/awg")

LOCK = threading.RLock()
LEGACY_TOKEN = secrets.token_urlsafe(32)  # only used by the retired v0.4 panel

_NAME_RE = re.compile(r"[A-Za-z0-9_-]{1,32}")
_CIDR_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}/32\b")


def password():
    return (D / "password").read_text().strip()


def totp_secret():
    return base64.b32decode((D / "totp-secret").read_text().strip())


def run(*args, data=None, timeout=15):
    return sp.check_output(
        args, input=data, text=True, stderr=sp.STDOUT, timeout=timeout
    ).strip()


def load():
    return json.loads(DB.read_text()) if DB.is_file() else {}


def save(obj):
    tmp = DB.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True))
    tmp.replace(DB)


def esc(value):
    return html.escape(str(value), quote=True)


def valid(name):
    if not _NAME_RE.fullmatch(str(name)):
        raise ValueError("Invalid name")
    return str(name)


def conf(name):
    return D / (valid(name) + ".conf")


def snapshot():
    """Persist the live AWG interface config for the supervisor."""
    try:
        text = run(AWG, "showconf", "omclient0") + "\n"
    except Exception:
        return False
    RUNTIME.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = RUNTIME / "omclient0.conf"
    tmp = target.with_suffix(".conf.tmp")
    tmp.write_text(text)
    tmp.replace(target)
    return True


def counters(iface="omclient0"):
    """Return {pubkey: rx + tx} from `awg show <iface> transfer`."""
    result = {}
    try:
        text = run(AWG, "show", iface, "transfer")
    except Exception:
        return result
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 3:
            try:
                result[parts[0]] = int(parts[1]) + int(parts[2])
            except ValueError:
                continue
    return result


def reconcile():
    """Apply usage accounting and remove expired / over-quota peers."""
    with LOCK:
        users = load()
        counts = counters()
        changed = False
        for user in users.values():
            if not user.get("enabled"):
                continue
            pub = user.get("pub")
            now = counts.get(pub, 0)
            old = int(user.get("last", 0))
            user["used"] = int(user.get("used", 0)) + (now - old if now >= old else now)
            user["last"] = now
            expiry = int(user.get("expires", 0) or 0)
            quota = int(user.get("quota", 0) or 0)
            if (expiry and time.time() >= expiry) or (quota and user["used"] >= quota):
                try:
                    run(AWG, "set", "omclient0", "peer", pub, "remove")
                except Exception:
                    pass
                user["enabled"] = False
                user["last"] = 0
                changed = True
        save(users)
        if changed:
            snapshot()
        return changed


def _listen_port():
    try:
        return run(AWG, "show", "omclient0", "listen-port")
    except Exception:
        return "51820"


def _server_pubkey():
    path = CLIENT / "server.pub"
    if not path.is_file():
        raise ValueError("Missing " + str(path))
    return path.read_text().strip()


def _client_config(key, address, pub, settings):
    obf = settings["obfuscation"]
    endpoint = settings["endpoint"]
    port = _listen_port()
    return (
        "[Interface]\n"
        "PrivateKey = {key}\n"
        "Address = {ip}\n"
        "DNS = 1.1.1.1\n"
        "MTU = 1280\n"
        "Jc = {Jc}\n"
        "Jmin = {Jmin}\n"
        "Jmax = {Jmax}\n"
        "S1 = {S1}\n"
        "S2 = {S2}\n"
        "H1 = {H1}\n"
        "H2 = {H2}\n"
        "H3 = {H3}\n"
        "H4 = {H4}\n\n"
        "[Peer]\n"
        "PublicKey = {server_pub}\n"
        "AllowedIPs = 0.0.0.0/0, ::/0\n"
        "Endpoint = {endpoint}:{port}\n"
        "PersistentKeepalive = 25\n"
    ).format(key=key, ip=address, server_pub=pub, endpoint=endpoint, port=port, **obf)


def create(q):
    name = valid(q.get("name", ""))
    settings = ops.settings(D)
    users = load()
    if name in users or conf(name).exists():
        raise ValueError("Name exists")

    net = ipaddress.IPv4Network(settings["network"])
    occupied = {ipaddress.ip_interface(u["ip"]).ip for u in users.values()}
    try:
        live = run(AWG, "show", "omclient0", "allowed-ips")
        occupied.update(
            ipaddress.ip_interface(match).ip for match in _CIDR_RE.findall(live)
        )
    except Exception:
        pass

    address = None
    for host in list(net.hosts())[1:]:
        if host != net.broadcast_address - 1 and host not in occupied:
            address = str(host) + "/32"
            break
    if address is None:
        raise ValueError("Subnet exhausted")

    days = int(q.get("days", 0) or 0)
    quota = int(q.get("quota", 0) or 0)
    if not 0 <= days <= 3650 or not 0 <= quota <= 100000:
        raise ValueError("Invalid limits")

    key = run(AWG, "genkey")
    pub = run(AWG, "pubkey", data=key + "\n")
    config = _client_config(key, address, _server_pubkey(), settings)

    with LOCK:
        users = load()
        if name in users or conf(name).exists():
            raise ValueError("Name exists")
        conf(name).write_text(config)
        users[name] = {
            "pub": pub,
            "ip": address,
            "enabled": False,
            "created": time.time(),
            "expires": time.time() + days * 86400 if days else 0,
            "quota": quota * 1024 ** 3,
            "used": 0,
            "last": 0,
        }
        save(users)
        try:
            run(AWG, "set", "omclient0", "peer", pub, "allowed-ips", address)
            users[name]["enabled"] = True
            save(users)
            snapshot()
        except Exception:
            # Keep the user disabled so it can be retried from the panel.
            save(users)
            raise


def action(q):
    """Dispatch a validated panel action. Always called while holding LOCK."""
    act = q.get("action", "")
    if act == "diagnose":
        return ops.diagnostics()
    if act == "repair":
        with LOCK:
            return ops.repair(D)
    if act == "endpoint":
        endpoint = str(ipaddress.IPv4Address(q.get("endpoint", "")))
        with LOCK:
            settings = ops.settings(D)
            settings["endpoint"] = endpoint
            path = D / "network.json"
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(settings, indent=2, sort_keys=True))
            tmp.replace(path)
        return "Endpoint updated for new downloads and QR codes"
    if act == "create":
        create(q)
        return "Created"
    if act == "test":
        target = str(ipaddress.IPv4Address(q.get("target", "")))
        out = run("ping", "-n", "-c", "5", "-i", "0.2", "-W", "1", target, timeout=15)
        return out
    if act == "probe":
        result = monitor.probe_once(ops.settings(D), run)
        return json.dumps(result, indent=2)
    if act == "backup":
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = D / "backup" / stamp
        backup.mkdir(mode=0o700, parents=True)
        for path in [DB, D / "network.json"] + list(D.glob("*.conf")):
            if path.is_file():
                shutil.copy2(path, backup / path.name)
        return "Local private backup saved: " + str(backup)

    reconcile()
    users = load()
    name = valid(q.get("name", ""))
    if name not in users:
        raise ValueError("Unknown user")
    user = users[name]
    pub = user.get("pub")

    if act in ("disable", "delete"):
        try:
            run(AWG, "set", "omclient0", "peer", pub, "remove")
        except Exception:
            pass
        user["enabled"] = False
        user["last"] = 0
        if act == "delete":
            users.pop(name, None)
            conf(name).unlink(missing_ok=True)
    elif act == "enable":
        expiry = int(user.get("expires", 0) or 0)
        quota = int(user.get("quota", 0) or 0)
        if (expiry and time.time() >= expiry) or (quota and user["used"] >= quota):
            raise ValueError("Limit reached")
        if not user.get("enabled"):
            try:
                run(AWG, "set", "omclient0", "peer", pub, "allowed-ips", user["ip"])
            except Exception:
                raise ValueError("Could not add peer")
            user["enabled"] = True
            user["last"] = 0
    else:
        raise ValueError("Unknown action")

    save(users)
    snapshot()
    return "Saved"


def worker(interval=15):
    while True:
        try:
            reconcile()
        except Exception as exc:
            print("Accounting:", type(exc).__name__, flush=True)
        time.sleep(interval)

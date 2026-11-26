"""Low-overhead telemetry.

Counters and RTT probes run in background threads. HTTP handlers only read an
in-memory snapshot, so opening the panel never executes `awg` or `ping`.
"""

from __future__ import annotations

import ipaddress
import json
import re
import socket
import struct
import subprocess as sp
import threading
import time
from collections import deque

VERSION = "1.4.2"
IFACES = ("omclient0", "omawg0")

lock = threading.RLock()
history = deque(maxlen=120)          # 120 samples x 2s = 4 minutes
latest = {}
latency = {"rtt": None, "avg": None, "min": None, "max": None,
           "jitter": None, "loss": None, "target": "", "mode": "udp", "t": 0}
_samples = deque(maxlen=30)          # successful RTTs only
_attempts = deque(maxlen=20)         # every probe, successful or not


def parse(text):
    """Parse `awg show <iface> transfer` into {pubkey: (rx, tx)}."""
    result = {}
    for line in str(text).splitlines():
        parts = line.split()
        if len(parts) == 3:
            try:
                result[parts[0]] = (int(parts[1]), int(parts[2]))
            except ValueError:
                continue
    return result


def sample(key, rx, tx, now):
    """Return (upload_bps, download_bps) from counter deltas.

    On the server: rx = bytes received from peer = peer upload;
    tx = bytes sent to peer = peer download.
    """
    old = _previous.get(key)
    _previous[key] = (rx, tx, now)
    if not old or now <= old[2] or rx < old[0] or tx < old[1]:
        return None, None
    elapsed = now - old[2]
    return (rx - old[0]) * 8 / elapsed, (tx - old[1]) * 8 / elapsed


_previous = {}


def collect(run, awg, settings=None):
    now = time.monotonic()
    data = {}
    for iface in IFACES:
        try:
            counts = parse(run(awg, "show", iface, "transfer", timeout=3))
            handshakes = dict(
                line.split() for line in
                run(awg, "show", iface, "latest-handshakes", timeout=3).splitlines()
                if len(line.split()) == 2
            )
            allowed = dict(
                line.split(maxsplit=1) for line in
                run(awg, "show", iface, "allowed-ips", timeout=3).splitlines()
                if len(line.split(maxsplit=1)) == 2
            )
            rows = []
            for pub, (rx, tx) in counts.items():
                up, down = sample((iface, pub), rx, tx, now)
                try:
                    handshake = int(handshakes.get(pub, 0))
                except (TypeError, ValueError):
                    handshake = 0
                rows.append({
                    "pub": pub,
                    "ip": allowed.get(pub, ""),
                    "rx": rx,
                    "tx": tx,
                    "up": up,
                    "down": down,
                    "handshake": handshake,
                })
            data[iface] = rows
        except Exception:
            data[iface] = None

    with lock:
        latest.clear()
        latest.update(data)
        rows = data.get("omclient0")
        if rows:
            usable = [r for r in rows if r["up"] is not None and r["down"] is not None]
            complete = len(usable) == len(rows)
        else:
            usable, complete = [], False
        history.append({
            "t": time.time(),
            "up": sum(r["up"] for r in usable) if complete else None,
            "down": sum(r["down"] for r in usable) if complete else None,
        })


def _icmp_probe(settings, run=None):
    """Fallback RTT probe over the tunnel when no UDP echo peer is configured."""
    result = {"rtt": None, "target": "", "mode": "icmp", "t": time.time()}
    if run is None:
        return result
    try:
        iface = settings.get("tunnel", "omawg0")
        info = json.loads(run("ip", "-j", "-4", "addr", "show", "dev", iface))
        address = ipaddress.ip_interface(info[0]["addr_info"][0]["local"] + "/" +
                                         str(info[0]["addr_info"][0]["prefixlen"]))
        hosts = [str(h) for h in address.network.hosts() if h != address.ip]
        if not hosts:
            return result
        target = hosts[0]
        out = sp.run(
            ["ping", "-n", "-I", iface, "-c", "3", "-i", "0.2", "-W", "1", target],
            capture_output=True, text=True, timeout=8,
        )
        match = re.search(r"= [\d.]+/([\d.]+)/[\d.]+/([\d.]+) ms", out.stdout)
        loss = re.search(r"([\d.]+)% packet loss", out.stdout)
        result.update({
            "target": target,
            "rtt": float(match.group(1)) if match else None,
            "jitter": float(match.group(2)) if match else None,
            "loss": float(loss.group(1)) if loss else None,
        })
    except Exception:
        pass
    return result


def probe_once(settings, run=None):
    """One UDP round trip to the exit echo service; no clock sync required."""
    host = str(settings.get("probe_host", "") or "").strip()
    if not host:
        return _icmp_probe(settings, run)
    port = int(settings.get("probe_port", 5355))
    timeout = float(settings.get("probe_timeout", 1.0))
    token = struct.pack("!Q", time.monotonic_ns())
    payload = token + b"1mobile"
    result = {"rtt": None, "target": "{}:{}".format(host, port),
              "mode": "udp", "t": time.time()}

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        if hasattr(socket, "SO_BINDTODEVICE"):
            try:
                iface = str(settings.get("tunnel", "omawg0")).encode()[:15]
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, iface)
            except OSError:
                pass
        sock.settimeout(timeout)
        sent = time.monotonic_ns()
        sock.sendto(payload, (host, port))
        reply, _ = sock.recvfrom(128)
        if reply[:8] == token:
            result["rtt"] = (time.monotonic_ns() - sent) / 1_000_000
    except Exception:
        pass
    finally:
        sock.close()
    return result


def loss_percent(attempts):
    """Loss over a window of boolean probe results (None when empty)."""
    values = list(attempts)
    if not values:
        return None
    return 100.0 * (1.0 - sum(values) / len(values))


def probe_worker(settings, run=None, interval=5):
    """Background RTT loop.

    ``settings`` may be a dict or a callable returning one. ``run`` is only
    used for the ICMP fallback, never from an HTTP request.
    """
    while True:
        cfg = {}
        try:
            cfg = settings() if callable(settings) else settings
            result = probe_once(cfg, run)
        except Exception:
            result = {"rtt": None, "mode": "udp", "t": time.time(),
                      "target": str(cfg.get("probe_host", "")), "error": "probe failed"}
        with lock:
            ok = result.get("rtt") is not None
            _attempts.append(ok)
            if ok:
                _samples.append(result["rtt"])
                values = list(_samples)
                average = sum(values) / len(values)
                result.update({
                    "avg": average,
                    "min": min(values),
                    "max": max(values),
                    "jitter": sum(abs(v - average) for v in values) / len(values),
                })
            if result.get("mode") == "udp":
                # Packet loss is measured over a window of real attempts;
                # a single successful reply must never report 0% loss.
                result["loss"] = loss_percent(_attempts)
                result["probes"] = len(_attempts)
                result["ok"] = sum(_attempts)
            latency.clear()
            latency.update(result)
        delay = cfg.get("probe_interval", interval) if isinstance(cfg, dict) else interval
        time.sleep(max(1, int(delay)))


def collect_worker(run, awg, settings, interval=2):
    while True:
        collect(run, awg, settings)
        time.sleep(interval)


def snapshot(users=None):
    """Return everything the browser needs. No subprocess calls here."""
    users = users or {}
    enriched = {}
    for pub, user in users.items():
        enriched[pub] = {
            "name": user.get("name", ""),
            "used": int(user.get("used", 0)),
            "enabled": bool(user.get("enabled")),
            "expires": int(user.get("expires", 0) or 0),
            "quota": int(user.get("quota", 0) or 0),
        }
    with lock:
        return {
            "version": VERSION,
            "now": time.time(),
            "interfaces": {k: (list(v) if v is not None else None)
                           for k, v in latest.items()},
            "history": list(history),
            "latency": dict(latency),
            "users": enriched,
        }

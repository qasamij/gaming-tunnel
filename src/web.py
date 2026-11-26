"""HTTPS control panel for the 1Mobile gaming tunnel.

Design goal: zero blocking system calls on page load / metrics refresh.
All counters and RTT values come from monitor's background threads.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import ssl
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import backend as b
import monitor
import ops

VERSION = "1.4.0"
BASE = Path(__file__).resolve().parent
STATIC = BASE / "static"

sessions = {}       # sid -> [csrf, sliding_expiry, hard_expiry]
attempts = {}       # ip -> [failures, window_end]
lock = threading.RLock()
last_otp = -1

COOKIE_ATTRS = "Secure; HttpOnly; SameSite=Strict; Path=/"


def totp(secret, counter):
    digest = hmac.new(secret, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 1000000).zfill(6)


def _pub_users():
    with b.LOCK:
        return {
            user["pub"]: dict(user, name=name)
            for name, user in b.load().items()
            if user.get("pub")
        }


def _listen_port():
    try:
        return b.run(b.AWG, "show", "omclient0", "listen-port")
    except Exception:
        return "51820"


LOGIN_HTML = """<!doctype html><html lang="fa" dir="rtl"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ورود | 1Mobile Gaming</title><link rel="stylesheet" href="/static/style.css"></head>
<body class="login-page"><main class="login"><section class="card">
<h1>1Mobile Gaming</h1><p>ورود امن مدیریت</p><p class="msg">{msg}</p>
<form method="post" action="/login"><input type="password" name="password" placeholder="رمز عبور" required autocomplete="current-password">
<input name="otp" inputmode="numeric" pattern="[0-9]{{6}}" maxlength="6" placeholder="کد شش رقمی" required autocomplete="one-time-code">
<button type="submit">ورود</button></form>
<small>نسخه {version} • رمز + کد یکبارمصرف</small></section></main></body></html>"""


def shell_html(csrf):
    token = html.escape(csrf, quote=True)
    return """<!doctype html><html lang="fa" dir="rtl"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="csrf" content="{token}"><title>1Mobile Gaming</title>
<link rel="stylesheet" href="/static/style.css"><script src="/static/app.js" defer></script></head>
<body><div class="layout"><aside><h1>1Mobile</h1><nav>
<button class="nav active" data-tab="overview">نمای کلی</button>
<button class="nav" data-tab="users">کاربران</button>
<button class="nav" data-tab="tunnel">تانل و لتنسی</button>
<button class="nav" data-tab="tools">ابزارها</button>
<button class="nav" data-tab="settings">تنظیمات</button>
</nav><form method="post" action="/action" id="logout-form"><input type="hidden" name="csrf" value="{token}">
<input type="hidden" name="action" value="logout"><button class="nav danger" type="submit">خروج</button></form>
<small>نسخه {version}</small></aside><main>
<header><div><h2>پنل تانل گیمینگ</h2><small id="updated">در انتظار داده...</small></div><span id="toast"></span></header>

<section class="tab" id="tab-overview"><div class="tiles">
<div class="tile"><span>دانلود کل</span><strong id="total-down">—</strong></div>
<div class="tile"><span>آپلود کل</span><strong id="total-up">—</strong></div>
<div class="tile"><span>کاربران فعال</span><strong id="active-users">—</strong></div>
<div class="tile"><span>لتنسی UDP</span><strong id="rtt">—</strong></div>
<div class="tile"><span>نوسان (jitter)</span><strong id="jitter">—</strong></div>
<div class="tile"><span>اتلاف بسته</span><strong id="loss">—</strong></div>
</div><section class="card"><h3>ترافیک چهار دقیقه اخیر</h3>
<canvas id="traffic" height="190"></canvas><small>سبز: دانلود • آبی: آپلود</small></section></section>

<section class="tab hidden" id="tab-users"><section class="card"><h3>ساخت کاربر</h3>
<form id="create-form"><input name="name" placeholder="client04" required pattern="[A-Za-z0-9_-]{{1,32}}">
<input name="days" type="number" min="0" max="3650" value="0" title="اعتبار به روز؛ صفر نامحدود">
<input name="quota" type="number" min="0" max="100000" value="0" title="حجم GiB؛ صفر نامحدود">
<button type="submit">ساخت</button></form></section>
<section class="card"><h3>لیست کاربران</h3><div class="table-wrap"><table id="users-table"><thead><tr>
<th>نام</th><th>IP</th><th>وضعیت</th><th>دانلود</th><th>آپلود</th><th>مصرف</th><th>اعتبار / سهمیه</th><th>مدیریت</th>
</tr></thead><tbody></tbody></table></div></section></section>

<section class="tab hidden" id="tab-tunnel"><div class="tiles" id="latency-tiles"></div>
<section class="card"><h3>پینگ و لتنسی تانل</h3><div id="latency-detail"></div></section>
<div id="interfaces"></div></section>

<section class="tab hidden" id="tab-tools"><section class="card"><h3>تست شبکه</h3>
<form id="test-form"><input name="target" placeholder="IPv4" required><button type="submit">Ping</button></form>
<button data-action="probe">تست UDP RTT</button><button data-action="diagnose">گزارش کامل شبکه</button>
<button data-action="repair">ترمیم مسیر ایران</button><button data-action="backup">بکاپ محلی</button>
<pre id="tool-output"></pre></section></section>

<section class="tab hidden" id="tab-settings"><section class="card"><h3>IP کانفیگها</h3>
<form id="endpoint-form"><input name="endpoint" id="endpoint-input" placeholder="_public IPv4_" required><button type="submit">ذخیره</button></form>
<small>تنها دانلود و QR جدید را تحت تأثیر قرار میدهد. کاربران نصب شده باید کانفیگ را دوباره وارد کنند.</small></section></section>
</main></div><div id="toast-box"></div></body></html>""".format(token=token, version=VERSION)


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "1MobilePanel/" + VERSION
    sys_version = ""

    def log_message(self, fmt, *args):
        return

    def setup(self):
        self.request.settimeout(12)
        super().setup()

    def reply(self, body, status=200, typ="text/html; charset=utf-8",
              cookie=None, filename=None):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Permissions-Policy", "geolocation=(), camera=(), microphone=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'self'; script-src 'self'; "
            "connect-src 'self'; img-src 'self'; form-action 'self'; "
            "frame-ancestors 'none'; base-uri 'none'",
        )
        if cookie:
            self.send_header("Set-Cookie", cookie)
        if filename:
            self.send_header("Content-Disposition",
                             'attachment; filename="{}"'.format(filename))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def json_reply(self, obj, status=200, cookie=None):
        self.reply(json.dumps(obj), status, "application/json; charset=utf-8", cookie)

    def fail(self, status, message):
        self.reply(html.escape(message), status, "text/plain; charset=utf-8")

    def read_body(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("bad length")
        if not 0 < size < 8192:
            raise ValueError("bad length")
        return {k: v[0] for k, v in parse_qs(
            self.rfile.read(size).decode("utf-8")).items()}

    def session(self):
        match = re.search(r"(?:^|;\s*)sid=([A-Za-z0-9_-]+)",
                          self.headers.get("Cookie", ""))
        sid = match.group(1) if match else ""
        now = time.time()
        with lock:
            entry = sessions.get(sid)
            if entry and now < entry[1] and now < entry[2]:
                entry[1] = now + 900
                return sid, entry[0]
            sessions.pop(sid, None)
        return None

    def login(self, msg="", status=200):
        self.reply(LOGIN_HTML.format(msg=html.escape(msg), version=VERSION), status)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in ("/favicon.ico",):
            return self.reply(b"", 204)
        if path in ("/static/app.js", "/static/style.css"):
            target = STATIC / Path(path).name
            if not target.is_file():
                return self.fail(404, "Not found")
            typ = "application/javascript" if path.endswith(".js") else "text/css"
            return self.reply(target.read_bytes(), 200, typ)
        if not self.session():
            return self.login()
        if path == "/metrics":
            data = monitor.snapshot(_pub_users())
            data["endpoint"] = ops.settings(b.D)["endpoint"]
            return self.json_reply(data)
        match = re.fullmatch(r"/(download|qr)/([A-Za-z0-9_-]{1,32})", path)
        if match:
            source = b.conf(match.group(2))
            if not source.is_file():
                return self.fail(404, "Not found")
            s = ops.settings(b.D)
            cfg = ops.endpoint_config(source.read_text(), s["endpoint"],
                                      _listen_port(), s["obfuscation"])
            if match.group(1) == "download":
                return self.reply(cfg, 200, "application/octet-stream",
                                  filename=source.name)
            try:
                png = b.sp.check_output(
                    ["qrencode", "-t", "PNG", "-o", "-"],
                    input=cfg.encode(), timeout=10,
                )
                return self.reply(png, 200, "image/png")
            except Exception:
                return self.fail(500, "qrencode unavailable")
        return self.reply(shell_html(self.session()[1]))

    def do_POST(self):
        global last_otp
        try:
            q = self.read_body()
        except Exception:
            return self.fail(400, "Invalid request")

        if self.path == "/login":
            now = time.time()
            with lock:
                attempts.clear()
                attempts.update({k: v for k, v in attempts.items() if v[1] > now})
                ip = self.client_address[0]
                count, end = attempts.get(ip, (0, now + 300))
                total = sum(v[0] for v in attempts.values())
                if count >= 5 or total >= 30:
                    return self.login("تلاش زیاد؛ پنج دقیقه بعد امتحان کنید", 429)
                tick = int(now // 30)
                used = next(
                    (t for t in (tick - 1, tick, tick + 1)
                     if t > last_otp and hmac.compare_digest(
                         totp(b.totp_secret(), t), q.get("otp", ""))),
                    None,
                )
                try:
                    password_ok = hmac.compare_digest(
                        b.password().encode(), q.get("password", "").encode())
                except Exception:
                    password_ok = False
                if not password_ok or used is None:
                    attempts[ip] = (count + 1, end)
                    return self.login("رمز یا کد نامعتبر", 401)
                last_otp = used
                attempts.pop(ip, None)
                sid = secrets.token_urlsafe(32)
                sessions[sid] = [secrets.token_urlsafe(32), now + 900, now + 28800]
            cookie = "sid={}; {}".format(sid, COOKIE_ATTRS)
            self.send_response(303)
            self.send_header("Location", "/")
            self.send_header("Content-Length", "0")
            self.send_header("Set-Cookie", cookie)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            return

        session = self.session()
        if not session:
            return self.fail(403, "Session expired")
        sid, csrf = session
        if not hmac.compare_digest(q.get("csrf", ""), csrf):
            return self.fail(403, "Invalid CSRF token")

        if q.get("action") == "logout":
            with lock:
                sessions.pop(sid, None)
            return self.json_reply(
                {"ok": True, "msg": "خارج شدید"},
                cookie="sid=; Max-Age=0; " + COOKIE_ATTRS,
            )

        try:
            with b.LOCK:
                msg = b.action(q)
            self.json_reply({"ok": True, "msg": msg})
        except ValueError as exc:
            self.json_reply({"ok": False, "msg": str(exc)}, 400)
        except Exception as exc:
            self.json_reply({"ok": False, "msg": type(exc).__name__}, 500)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False
    request_queue_size = 128


def main():
    host = os.getenv("LISTEN", "0.0.0.0")
    port = int(os.getenv("PORT", "9443"))
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(b.D / "tls.crt", b.D / "tls.key")

    server = Server((host, port), H)
    server.socket = ctx.wrap_socket(server.socket, server_side=True,
                                    do_handshake_on_connect=False)
    settings = lambda: ops.settings(b.D)
    threading.Thread(target=b.worker, daemon=True).start()
    threading.Thread(target=monitor.collect_worker,
                     args=(b.run, b.AWG, settings), daemon=True).start()
    threading.Thread(target=monitor.probe_worker,
                     args=(settings, b.run), daemon=True).start()
    print("1Mobile panel listening on https://{}:{}/".format(host, port), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

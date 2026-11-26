# API

همه endpointها بهجز `/login` و فایلهای static نیاز به کوکی نشست معتبر دارند.

## GET `/`

صفحه HTML پنل. فقط HTML ثابت + meta CSRF برمیگرداند، بدون فراخوانی سیستم.

## GET `/metrics`

پاسخ نمونه:

```json
{
  "version": "1.4.0",
  "now": 1764163200.12,
  "endpoint": "203.0.113.10",
  "history": [
    {"t": 1764163198.1, "down": 12500000.0, "up": 3200000.0}
  ],
  "interfaces": {
    "omclient0": [
      {"pub": "PUBKEY", "ip": "10.7.0.2/32", "rx": 1000, "tx": 9000,
       "up": 800.0, "down": 7200.0, "handshake": 1764163100}
    ],
    "omawg0": null
  },
  "latency": {
    "rtt": 18.4, "avg": 19.1, "min": 17.2, "max": 22.0,
    "jitter": 1.3, "loss": 0.0, "target": "10.9.0.1:5355",
    "mode": "udp", "t": 1764163195.0
  },
  "users": {
    "PUBKEY": {"name": "client01", "used": 10485760, "enabled": true,
               "expires": 0, "quota": 0}
  }
}
```

| فیلد | معنی |
|---|---|
| `history[].down` | کل دانلود کاربران بیت بر ثانیه |
| `history[].up` | کل آپلود کاربران بیت بر ثانیه |
| `row.down` / `row.up` | دانلود/آپلود همان peer |
| `row.rx` / `row.tx` | شمارنده تجمعی AWG (rx = آپلود کاربر، tx = دانلود کاربر) |
| `latency.avg` | میانگین 30 RTT آخر |
| `latency.jitter` | میانگین انحراف مطلق از میانگین |

## POST `/login`

فورم: `password`, `otp`. در موفقیت `303` + cookie. در شکست `401`/`429`.

## POST `/action`

فورم: `csrf` + یکی از actionهای زیر:

| action | پارامترها | توضیح |
|---|---|---|
| `create` | `name`, `days`, `quota` | ساخت کاربر و peer |
| `enable` | `name` | فعال کردن |
| `disable` | `name` | قطع بدون حذف |
| `delete` | `name` | حذف peer و فایل کانفیگ |
| `endpoint` | `endpoint` | تغییر IP دانلود/QR |
| `test` | `target` | 5 ping به IPv4 |
| `probe` | — | یک UDP RTT آزمایشی |
| `diagnose` | — | خروجی ip/iptables/awg/systemctl |
| `repair` | — | ترمیم جدول 179 و `ip_forward` |
| `backup` | — | کپی محلی امن به `backup/<timestamp>/` |
| `logout` | — | حذف نشست |

پاسخ موفق:

```json
{"ok": true, "msg": "Saved"}
```

پاسخ خطا: `400` برای اعتبارسنجی، `403` برای CSRF/nشت، `500` برای خطای داخلی (فقط نوع exception، بدون traceback).

## GET `/download/<name>` و `/qr/<name>`

کانفیگ با Endpoint و مقادیر obfuscation فعلی بازنویسی میشود. QR همان متن را به PNG تبدیل میکند.

## GET `/static/app.js`, `/static/style.css`

فایلهای frontend بدون احراز هویت (برای صفحه login هم لازماند). CSP فقط اجرای اسکریپت از self را اجازه میدهد.

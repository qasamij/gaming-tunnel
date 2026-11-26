# چهار تست عملی قبل از انتشار

> **هشدار:** این تستها فقط روی **دو VPS آزمایشی تازه** اجرا میشوند. نصب فعلی روی سرورهای کاری دستنخورده میماند. دستور `fresh` را روی سرور فعال اجرا نکنید.

هدف: تأیید اینکه نسخهٔ فعلی واقعاً «پایدار و بدون قطعی» است، نه فقط از نظر بررسی سورس. قبل از اضافه کردن قابلیت جدید (مانند تفکیک سرویس مدیریتی)، این چهار تست باید انجام شوند.

## آمادگی

- دو VPS تازه با Debian/Ubuntu، شمارهٔ ۱: Iran، شمارهٔ ۲: Exit.
- از هر دو اسنapshot بگیرید.
- روی هر دو: `sudo INSTALL_AWG=1 bash scripts/install.sh deps` سپس `sudo bash scripts/install.sh awg-check` (تأیید عملکرد واقعی موتور حتی اگر باینری `wg` نام دارد).
- **ایمنی آزمایش AWG:** قبل از آزمایش، `ip -br link | grep awgchk` خالی باشد؛ بعد از دو بار اجرای `awg-check` هم خالی بماند (بار دوم از cache استفاده میکند و نباید لینک موقت بسازد). مطمئن شوید هیچ لینک دیگری `down`/حذف نشده است.
- یک کلاینت AmneziaWG تستی (موبایل یا لپتاپ) برای تست شمارهٔ ۴.

## تست ۱ — نصب از صفر روی دو VPS

1. تنظیمات مشترک را **قبل از هر نصب** بسازید: روی Iran `sudo JUNK_COUNT=0 bash scripts/install.sh fresh-config init` و خط چاپشدهٔ `OMAWG_SHARED=...` را عیناً روی Exit با `sudo bash scripts/install.sh fresh-config import 'OMAWG_SHARED=...'` وارد کنید. با `fresh-config show` روی هر دو، خطها برابر باشد.
2. روی Iran: `sudo bash scripts/install.sh keygen iran` و `keys show`.
3. روی Exit: `sudo bash scripts/install.sh keygen exit` و `keys show`.
4. کلید `omawg0.pub` را جابهجا کنید؛ سپس `fresh exit` و بعد `fresh iran` (ترتیب این دو دلخواه است).
5. **تست محافظ:** دوباره `fresh exit` را اجرا کنید. انتظار میرود با پیام «existing tunnel detected» متوقف شود، نه اینکه Peerها بازنویسی شوند. (فقط در آزمایشگاه با `FORCE_FRESH=1` میشود دور زد.)

**معیار قبولی:** هر دو اینترفیس `up` و دارای آدرساند؛ `awg show omawg0 latest-handshakes` تازهای دارد؛ پنل باز میشود؛ از Iran `python3 /opt/1mobile-web-v13/healthcheck.py` وضعیت `ok` میدهد.

## تست ۲ — بستن SSH

1. وارد پنل شوید، سپس تمام نشستهای SSH را ببندید (`exit`) و ۱۰ دقیقه صبر کنید.
2. از کلاینت تستی، اتصال به اینترنت از طریق تانل را چک کنید.
3. دوباره SSH بزنید و بررسی کنید:

```bash
systemctl is-active 1mobile-runtime 1mobile-panel
sudo python3 /opt/1mobile-web-v13/healthcheck.py
sudo journalctl -u 1mobile-runtime -n 50 --no-pager
```

**معیار قبولی:** ترافیک قطع نشده، سرویسها `active` و handshake تازه است؛ هیچ خطای `apply-iface` در لاگ نیست.

## تست ۳ — ریبوت هر دو سرور

1. `sudo reboot` روی **Exit**، صبر کنید تا بالا بیاید؛ handshake و UDP echo را چک کنید.
2. `sudo reboot` روی **Iran**، صبر کنید تا بالا بیاید؛ پنل و تانل را چک کنید.
3. هیچ دستور دستی اجرا نکنید:

```bash
sudo ip addr show dev omawg0
sudo ip addr show dev omclient0      # Iran
sudo ip route show table 179         # Iran
sudo ip route show | grep 10.9.0.2   # Exit
sudo python3 /opt/1mobile-web-v13/healthcheck.py
```

**معیار قبولی:** آدرسها و routeها خودبهخود برگشتاند، لینک `up` است، RTT از پنل غیرخالی است، و کلاینت تستی بدون دخالت دستی کار میکند.

همچنین بررسی کنید supervisor خرابی «زنده ولی قطع» را تشخیص میدهد: روی Exit `sudo ip link set omawg0 down` بزنید، ۳ دقیقه صبر کنید، لاگ supervisor را ببینید (`Health repair`) و دوباره `up` شدن را تأیید کنید. سپس همان را با مسدود کردن موقت UDP/5355 شبیهسازی probe-failed کنید و مطمئن شوید بعد از ۳ strike تعمیر نرم انجام میشود (نه حذف Peerها).

## تست ۴ — ساخت کاربر از پنل و تأیید اینترنت خروجی

1. با رمز + TOTP وارد پنل شوید.
2. تب **کاربران** → ساخت کاربر با اعتبار و سهمیهٔ آزمایشی → دانلود کانفیگ و QR.
3. کانفیگ را در کلاینت تستی وارد کنید و connect کنید.
4. از داخل تانل خروجی اینترنت را تأیید کنید (مثلاً `curl -4 https://ifconfig.me` روی کلاینت یا باز کردن یک سایت).
5. در پنل: شمارندههای rx/tx کاربر، handshake، RTT/jitter/loss را ببینید؛ سهمیه و انقضاء را تغییر دهید و حذف/غیرفعال کردن را تست کنید.
6. Peer کاربر حذفشده را مجدداً بررسی کنید: `awg show omclient0` نباید آن pubkey را نشان دهد.

**معیار قبولی:** ترافیک واقعی از Exit خارج میشود، شمارندهها بالا میروند، وضعیت کاربر با وضعیت Peer هماهنگ است و حذف Peer شکستخورده، کاربر را ناسازگار نمیکند.

## جمعآوری لاگ در صورت شکست

```bash
sudo journalctl -u 1mobile-runtime -n 200 --no-pager
sudo journalctl -u 1mobile-panel -n 200 --no-pager
sudo awg show all latest-handshakes
sudo ip -br addr; sudo ip rule show; sudo ip route show table all
curl -k https://127.0.0.1:9443/metrics     # با کوکی نشست معتبر
```

## جدول نتایج

| تست | تاریخ | نتیجه | مشاهده/لینک لاگ |
|---|---|---|---|
| ۱ — نصب صفر | | | |
| ۲ — بستن SSH | | | |
| ۳ — ریبوت دو سرور | | | |
| ۴ — کاربر + اینترنت خروجی | | | |

پس از چهار «_ok_»، مرحلهٔ بعدی [`docs/PRIVILEGE-SEPARATION.md`](PRIVILEGE-SEPARATION.md) است.

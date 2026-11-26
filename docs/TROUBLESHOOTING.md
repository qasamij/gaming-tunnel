# عیبیابی

## پنل بالا نمیآید

```bash
sudo journalctl -u 1mobile-panel -n 80 --no-pager
sudo ss -tlnp | grep 9443
sudo ls -l /etc/1mobile-panel/{tls.crt,tls.key,password,totp-secret}
```

علتهای رایج:

- فایل TLS یا رمز وجود ندارد → `install.sh bootstrap` را دوباره با `FORCE=1` اجرا کنید (با حفظ کلیدها).
- آدرس `/etc/1mobile-panel/network.json` معتبر نیست → `python3 -m json.tool` روی آن اجرا کنید.
- پورت 9443 توسط سرویس دیگری گرفته شده → `PORT` را در override systemd تغییر دهید.

## `awg: command not found`

پیشنیاز AmneziaWG نصب نشده:

```bash
sudo INSTALL_AWG=1 bash scripts/install.sh deps
```

## کاربر ساخته شده ولی connect نمیشود

1. بررسی peer:

```bash
sudo awg show omclient0 | head -40
sudo awg show omclient0 latest-handshakes
```

2. اگر handshake وجود ندارد: Endpoint/IP یا پورت را چک کنید و کانفیگ را دوباره دانلود کنید (پنل Endpoint فعلی را مینویسد).
3. اگر handshake هست ولی ترافیکی نیست: جدول 179 را بررسی کنید:

```bash
ip rule show | grep 179
ip route show table 179
```

4. ترمیم:

```bash
sudo bash scripts/install.sh monitor   # یا دکمه repair در پنل
sudo /opt/1mobile-runtime/runtime.sh
```

## سرعتها `—` است

- worker تازه شروع شده و دو نمونه هنوز جمع نشدهاند (حدود 4 ثانیه صبر کنید).
- Peer بازسازی شده و شمارنده صفر شده است؛ یک دوره `null` میماند.
- `awg show ... transfer` را دستی اجرا کنید تا مطمئن شوید خروجی سه ستونه است.

## RTT / jitter `—` است

1. روی Exit:

```bash
sudo systemctl status 1mobile-udp-echo
sudo ss -lnup | grep 5355
```

2. روی Iran:

```bash
python3 -c 'import json; print(json.load(open("/etc/1mobile-panel/network.json"))["probe_host"])'
```

باید `10.9.0.1` (آدرس omawg0 Exit) باشد.

3. تست دستی:

```bash
sudo -u root python3 - <<'PY'
import sys; sys.path.insert(0,'/opt/1mobile-web-v13')
import monitor, ops
print(monitor.probe_once(ops.settings('/etc/1mobile-panel')))
PY
```

اگر `probe_host` خالی باشد، پنل به ICMP تانل برمیگردد و ممکن است با `/32` بودن omawg0 عددی نشان ندهد.

## تانل بعد از ریبوت / بستن SSH بالا نیست

```bash
sudo bash scripts/install.sh persist
sudo ls -l /etc/1mobile-runtime/*.addr /etc/1mobile-runtime/*.conf
sudo bash /opt/1mobile-runtime/apply-iface.sh omawg0
sudo bash /opt/1mobile-runtime/runtime.sh
sudo ip addr show dev omawg0
sudo ip link show dev omawg0
```

`persist` سرویسها را دوباره `enable` میکند و فایلهای ذخیرهشده را چک میکند. اگر `.addr` گم شده باشد، `install.sh runtime` آن را از اینترفیس زنده میخواند؛ در غیر این صورت `keys import <role>` یا `fresh <role>` را اجرا کنید. جزئیات: [docs/KEYS.md](KEYS.md).

## خطای `awg setconf` هنگام نصب fresh

قالب جدید مقادیر مبهمسازی را بررسی کنید:

```bash
cat /etc/1mobile-runtime/obfuscation.txt
```

باید نه خط، هر خط به شکل `Jc = 3` و شامل ۹ کلید `Jc..H4` باشد. اگر مقادیر را با فاصله حول `=` چسباندهاید اشکالی ندارد؛ تابع `obfuscation_lines` آنها را نرمال میکند. خطوط جداگانهٔ `=` یا عدد تنها نباید وجود داشته باشند.

## Loss همیشه صفر یا غیرواقعی است

`latency.loss` اکنون از پنجرهٔ آخرین ۲۰ تلاش UDP محاسبه میشود. فیلدهای `probes` و `ok` در `/metrics` تعداد تلاشها و پاسخهای موفق را نشان میدهند. اگر `probes` کوچک است، worker تازه راهاندازی شده است. `loss=100` یعنی سرور echo روی Exit یا route برگشتی `10.9.0.2/32` مشکل دارد.

## رمز قدیمی پس از ارتقا کار میکند؟

بله. محتوای فایل `password` اگر با `argon2id$` یا `scrypt$` شروع نشود، به عنوان رمز قدیمی پذیرفته و پس از اولین ورود موفق خودبهخود هش میشود.

## Supervisor وارد restart loop شده

پیام:

```text
Interface omclient0 exists but AWG is unavailable; refusing destructive removal
```

یعنی اینترفیس هست ولی socket AWG از بین رفته. این رفتار عمدی است تا کانفیگ زنده حذف نشود:

```bash
sudo ip link del omclient0
sudo systemctl restart 1mobile-runtime
```

سپس supervisor آن را از `/etc/1mobile-runtime/omclient0.conf` بازسازی میکند.

## خروجی diagnose را میخواهم گزارش بدهم

گزارش شامل قوانین iptables و کلیدهای عمومی است. قبل از ارسال:

- IP عمومی و نام کاربران را جایگزین کنید.
- TLS, رمز و TOTP را هرگز ارسال نکنید.
- ترجیحاً فقط قسمت مربوطه را کپی کنید.

## برگشت سریع

```bash
sudo bash scripts/install.sh rollback
sudo bash scripts/install.sh rollback-runtime
```

# امنیت

## مدل تهدید

پنل روی **root** اجرا میشود چون باید `awg`، `ip`، `sysctl` و `iptables` را اجرا کند. بنابراین هر نقص در پنل معادل دسترسی root به سرور Iran است.

### آنچه پیاده شده

- رمز عبور + TOTP (حداقل 10 کاراکتر، ذخیره شده با مجوز 600).
- anti-replay برای TOTP: هر کد 30 ثانهای فقط یک بار قابل استفاده است.
- محدودیت 5 تلاش در 5 دقیقه به ازای IP و 30تلاش کلی.
- session چرخان: 15 دقیقه idle، حداکثر 8 ساعت، cookie با `Secure; HttpOnly; SameSite=Strict`.
- CSRF token جداگانه در هر نشست.
- CSP سختگیرانه، `nosniff`، `no-referrer`، `frame-ancestors 'none'`.
- تمام فرمانها با لیست آرگومان اجرا میشوند، بدون shell.
- تمام ورودیها validate میشوند: نام `[A-Za-z0-9_-]{1,32}`، IP با `ipaddress`.
- نوشتن فایلها atomic است (`.tmp` سپس `replace`) و `umask 077`.
- gateway `.1` و آخرین آدرس قابل استفاده رزرواند تا با routing تداخل نکنند.

### محدودیتهای شناختهشده

1. **گواهی self-signed**. با تغییر IP سرور بایدtls.crt/tls.key دوباره ساخته شوند.
2. **ACL قدیمی `admin-network` در پنل v1.3 حذف شده بود**. در این نسخه هم پنل فقط به username/password/TOTP تکیه میکند. جداره واقعی باید فایروال باشد.
3. **AmneziaWG obfuscation یک لایه مخفیسازی است، نه رمزنگاری اضافی.** مقادیر `H1-H4` و `S1/S2` باید در دو سر تانل و کلاینتها یکسان باشند، بنابراین تمام کانفیگها یک امضای مشترک دارند.
4. `Jc > 0` بستههای junk اضافه میکند. اینها فقط هنگام handshakeاند، ولی مصرف پهنای باند و latency handshake را بالا میبرند.
5. **گزارش diagnose شامل قوانین iptables و کلیدهای عمومی است.** آن را در GitHub/issues قرار ندهید.

## چک لیست سختسازی

```bash
# فقط IP administrator اجازه دسترسی به پنل داشته باشد
sudo iptables -I INPUT -p tcp --dport 9443 -s YOUR_IP/32 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 9443 -j DROP

# فقط همسایه تانل اجازه UDP echo داشته باشد
sudo iptables -I INPUT -p udp --dport 5355 -s 10.9.0.2/32 -j ACCEPT
sudo iptables -A INPUT -p udp --dport 5355 -j DROP

# بررسی مجوزها
sudo stat -c '%a %n' /etc/1mobile-panel /etc/1mobile-panel/* | head -20
```

همچنین:

- TOTP را در یک authenticator ذخیره و از چت/ایمیل حذف کنید.
- بکاپ `/etc/1mobile-panel/backup/` شامل کانفیگهای خصوصی است؛ آن را به GitHub پوش نکنید.
- لاگها و خروجی diagnose را قبل از اشتراکگذاری پاک کنید.
- پورت 9443 را پشت فایروال بگذارید، حتی اگر TLS دارد.

## گنجاندن در GitHub

در repository فقط کد، مستندات و فایلهای `.example` قرار دارند. هیچ کلید خصوصی، رمز، TOTP یا کانفیگ کاربر وجود ندارد. `.gitignore` الگوهای مربوطه را پوشش میدهد.

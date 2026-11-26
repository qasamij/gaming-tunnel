# نصب از صفر

این مسیر دو VPS را فرض میکند:

| نقش | وظیفه | اینترفیسها |
|---|---|---|
| **Iran** | کلاینتها به آن وصل میشوند و ترافیک وارد تانل میشود | `omclient0` (/24), `omawg0` (/30) |
| **Exit** | ترافیک از تانل خارج و NAT میشود | `omawg0` (/30) |

پورت پیشفرض کلاینتها `51820/udp`، پورت تانل Iran→Exit معمولاً `51821/udp` و پورت UDP echo برابر `5355/udp` است.

## 0) پیشنیازها

روی Debian/Ubuntu 20.04+:

```bash
sudo apt-get update
sudo apt-get install -y git
git clone https://github.com/qasamij/gaming-tunnel.git
cd gaming-tunnel
sudo INSTALL_AWG=1 bash scripts/install.sh deps
```

`INSTALL_AWG=1` کد رسمی [`amneziawg-tools`](https://github.com/amnezia-vpn/amneziawg-tools) و [`amneziawg-go`](https://github.com/amnezia-vpn/amneziawg-go) را clone و build میکند. اگر از قبل نصباند، مرحله deps را سادهتر اجرا کنید.

## 1) تبادل کلیدها

روی **هر دو** سرور:

```bash
sudo bash scripts/install.sh keygen iran   # فقط روی Iran
sudo bash scripts/install.sh keygen exit   # فقط روی Exit
```

خروجی مثال:

```text
[iran] public keys (copy these to the other server):
omawg0        AAAA...
omclient0     BBBB...
```

- `omawg0.pub` مربوط به Iran را یادداشت کنید و موقع نصب Exit وارد کنید.
- `omawg0.pub` مربوط به Exit را یادداشت کنید و موقع نصب Iran وارد کنید.
- `omclient0.pub` همان کلیدی است که در کانفیگ کلاینتها به عنوان `PublicKey` سرور استفاده میشود (پنل آن را از `/etc/1mobile-client/server.pub` میخواند؛ در نصب fresh بهطور خودکار کپی نمیشود — مرحله 4 را ببینید).

> نکته: کلیدهای خصوصی در `/etc/1mobile-runtime/keys/` با مجوز `600` میمانند و از سرور خارج نمیشوند.

برای وارد کردن سادهٔ کلیدها روی هر سرور (مثلاً بعد از تعویض VPS)، به جای تکرار مراحل دستی از این دستورها استفاده کنید:

```bash
sudo bash scripts/install.sh keys show              # کلیدهای عمومی این سرور
sudo bash scripts/install.sh keys import iran       # یا: import exit
sudo bash scripts/install.sh persist                # بررسی پایداری بعد از ریبوت
```

جزئیات کامل: [docs/KEYS.md](KEYS.md). رمز ادمین نیز به صورت هش Argon2id/scrypt ذخیره میشود، نه متن ساده.

## 2) Exit را پیکربندی کنید

```bash
sudo bash scripts/install.sh fresh exit
```

سؤالات:

1. IP عمومی Iran
2. `omawg0.pub` مربوط به Iran
3. پورت تانل Iran (`51821` پیشفرض)
4. سابنت کلاینتها (`10.7.0.0/24` پیشفرض)
5. خط مبهمسازی Iran (`Jc=... H1=...`) — فقط اگر `network.json` را کپی نکردهاید؛ یک بار پرسیده و ذخیره میشود.

اسکریپت:

- `omawg0` با آدرس `10.9.0.1/30` میسازد و لینک را `up` میکند.
- در `AllowedIPs` peer Iran علاوه بر سابنت کلاینتها، `10.9.0.2/32` را هم میگذارد تا پاسخ UDP probe برگردد.
- routeهای `10.7.0.0/24` و `10.9.0.2/32` را به سمت `omawg0` اضافه میکند.
- `ip_forward` و MASQUERADE را به رابط default route اضافه میکند.
- سرویس UDP echo را روی `10.9.0.1:5355` نصب میکند.
- supervisor را با `role=exit` نصب میکند.

فایروال: فقط `UDP/51821` از IP Iran و `UDP/5355` از `10.9.0.2` باز کنید.

## 3) Iran را پیکربندی کنید

```bash
sudo bash scripts/install.sh fresh iran
```

سؤالات:

1. IP عمومی Iran (همان چیزی که کلاینتها به عنوان Endpoint میبینند)
2. IP عمومی Exit
3. `omawg0.pub` مربوط به Exit
4. رمز ادمین (حداقل 10 کاراکتر)

اسکریپت:

- `omawg0` با `10.9.0.2/30` و peer Exit،
- `omclient0` با `10.7.0.1/24` و بدون peer (پنل بعداً اضافه میکند)،
- جدول routing شماره `179` با rule `from 10.7.0.0/24 lookup 179`،
- پنل HTTPS و supervisor را نصب میکند.

برای کمترین latency handshake:

```bash
sudo JUNK_COUNT=0 bash scripts/install.sh fresh iran
```

## 4) کلید سرور در پنل (خودکار)

پنل هنگام ساخت کاربر، فایل `/etc/1mobile-client/server.pub` را میخواند. نصب fresh و `keys import iran` آن را از `omclient0.pub` کپی میکنند. اگر سرور قدیمی است یا کلید را عوض کردهاید، دستی:

```bash
sudo install -d -m 700 /etc/1mobile-client
sudo install -m 644 /etc/1mobile-runtime/keys/omclient0.pub /etc/1mobile-client/server.pub
sudo systemctl restart 1mobile-panel
```

## 5) ورود و اولین کاربر

1. `https://<IRAN-IP>:9443/` را باز کنید (گواهی self-signed است).
2. رمز و کد TOTP را وارد کنید (TOTP هنگام نصب چاپ شد).
3. تب **کاربران** → نام کاربر، اعتبار (روز) و سهمیه (GiB) → **ساخت**.
4. لینک **کانفیگ** یا **QR** را بگیرید و در کلاینت AmneziaWG وارد کنید.

## پایداری بعد از ریبوت و بستن SSH

تانل توسط سرویس systemd اداره میشود و به نشست SSH وابسته نیست. آدرسها در `/etc/1mobile-runtime/<iface>.addr` و تنظیمات در `<iface>.conf` ذخیرهاند؛ supervisor بعد از ریبوت اینترفیسها را میسازد، آدرسها را میدهد، لینک را `up` میکند و مسیرها/NAT را دوباره اعمال میکند.

بررسی و ترمیم یک مرحلهای:

```bash
sudo bash scripts/install.sh persist
```

این دستور سرویسها را `enable` میکند، وجود فایلهای ذخیرهشده را چک میکند و وضعیت نهایی را نشان میدهد. جزئیات: [docs/KEYS.md](KEYS.md).

## ارتقا از نصب قدیمی

اگر از قبل پنل v1.0/v1.1 و اینترفیسها وجود دارند:

```bash
sudo bash scripts/install.sh monitor
sudo bash scripts/install.sh runtime   # اگر supervisor قدیمی است
```

پشتیبانها در `/etc/1mobile-panel/backup/upgrade-<timestamp>/` ذخیره میشوند.

## برگشت

```bash
sudo bash scripts/install.sh rollback           # unit پنل قدیمی
sudo bash scripts/install.sh rollback-runtime   # unit supervisor قدیمی
```

حذف کامل: `sudo CONFIRM=1 bash scripts/install.sh uninstall`

## چک لیست بعد از نصب

```bash
sudo awg show omclient0
sudo awg show omawg0
sudo ip rule show | grep 179
sudo systemctl status 1mobile-panel 1mobile-runtime
sudo bash scripts/install.sh persist        # بررسی enable/active و فایلهای ذخیرهشده
curl -k https://127.0.0.1:9443/metrics      # با کوکی نشت نیاز به ورود دارد
```

در پنل، تب **تانل و لتنسی** باید RTT، jitter و Loss را نشان دهد. اگر `—` دیدید، بررسی کنید که `probe_host` در `network.json` برابر `10.9.0.1` و سرویس echo روی Exit فعال است.

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

## 2) Exit را پیکربندی کنید

```bash
sudo bash scripts/install.sh fresh exit
```

سؤالات:

1. IP عمومی Iran
2. `omawg0.pub` مربوط به Iran
3. پورت تانل Iran (`51821` پیشفرض)
4. سابنت کلاینتها (`10.7.0.0/24` پیشفرض)

اسکریپت:

- `omawg0` با آدرس `10.9.0.1/30` میسازد.
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

## 4) کلید سرور را به پنل معرفی کنید

پنل هنگام ساخت کاربر، فایل `/etc/1mobile-client/server.pub` را میخواند. در نصب fresh آن کلید همان `omclient0.pub` است:

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
curl -k https://127.0.0.1:9443/metrics      # با کوکی نشت نیاز به ورود دارد
```

در پنل، تب **تانل و لتنسی** باید RTT، jitter و Loss را نشان دهد. اگر `—` دیدید، بررسی کنید که `probe_host` در `network.json` برابر `10.9.0.1` و سرویس echo روی Exit فعال است.

# نصب آسان با یک دستور — طرح طراحی

> **وضعیت: پیشنهاد است، پیادهسازی نشده است.** فایل `scripts/quick-install.sh` در مخزن فعلی وجود ندارد.
> طبق توافق قبلی، پیادهسازی فقط **بعد از** چهار تست عملی [`docs/TEST-PLAN.md`](TEST-PLAN.md) آغاز میشود.
> این سند فقط طراحی را ثبت میکند؛ هیچ سرور یا فایل اجرایی فعلی تغییر نمیکند.

## ۱) تجربی که کاربر میبیند

دستور پیشنهادی شما:

```bash
curl -fsSL https://raw.githubusercontent.com/qasamij/gaming-tunnel/main/scripts/quick-install.sh -o quick-install.sh
sudo bash quick-install.sh
```

دو اصلاح ایمنی برای نسخهٔ نهایی:

```bash
curl -fsSL https://raw.githubusercontent.com/qasamij/gaming-tunnel/v1.5.0/scripts/quick-install.sh -o quick-install.sh
echo '<SHA256>  quick-install.sh' | sha256sum -c -
sudo bash quick-install.sh
```

- از `main` به تگ ثابت (`v1.5.0`) استفاده میشود چون `main` قابل تغییر است.
- فایل ابتدا دانلود و چکـسام میشود، سپس اجرا میگردد؛ هرگز `curl | bash` نشود.
- اسکریپت قبل از هر کاری نسخهٔ خود و هش اسکریپتهای فراخوانی شده را چاپ میکند.

### پیشنمایش منو

```text
1Mobile Setup Wizard  (v1.5.0)

۱) 🇮🇷 سرور ایران — پنل و اتصال کاربران
۲) 🌍 سرور خارج — خروجی اینترنت

انتخاب [۱/۲]:
```

هدف نهایی همانطور که پیشنهاد کردید: کاربر فقط روی **سرور ایران** نصب را آغاز میکند، IP و اطلاعات دسترسی سرور خارج را وارد میکند و نصبکننده از طریق SSH رمزنگاریشده سمت خارج را هم تنظیم میکند. حالت منو تکی سرور برای بازیابی اضطراری هم باقی میماند.

## ۲) چه چیزهایی خودکار میشوند

| # | مورد | پیادهسازی |
|---|---|---|
| ۱ | تشخیص Ubuntu، IP عمومی، کارت شبکه و منابع | `src/wizard.py` (stdlib): `os-release`، `ip -j route/addr`، `/proc/meminfo`، `nproc`؛ بدون فراخوانی سرویس خارجی |
| ۲ | نصب و آزمایش AmneziaWG | فراخوانی `install.sh deps` و `install.sh awg-check` موجود (آزمایش عملی با `Jc/H1..H4`) |
| ۳ | تولید کلیدها و تنظیمات مشترک | `fresh-config init` + `keygen iran|exit` موجود؛ فقط `.pub`ها و خط `OMAWG_SHARED=...` رد و بدل میشوند |
| ۴ | سرویسهای دائمی و بازیابی بعد از ریبوت | `install.sh runtime` و `persist` موجود |
| ۵ | بررسی Routing، NAT، Handshake و اینترنت | `healthcheck.py` موجود + `awg show` + بررسی خروجی واقعی از Exit |
| ۶ | پنل گرافیکی با رمز و ورود دومرحلهای | `bootstrap-panel.sh` موجود؛ رمز هش Argon2id/scrypt و TOTP تکبار چاپ میشود |
| ۷ | بکاپ قبل از ارتقا و Rollback | اسنپشات خودکار + فراخوانی `rollback.sh` / `rollback-runtime.sh` موجود |

هیچ منطقی کپی نمیشود: `quick-install.sh` یک منوی نازک است و تمام کارها را از اسکریپتهای فعلی میخواند.

## ۳) امنیت ارتباط با سرور خارج

- ارتباط فقط از طریق `ssh` با **کلید** و `BatchMode=yes`؛ رمز عبور در مخزن، لاگ یا متغیر محیطی ذخیره نمیشود.
- قبل از اولین اتصال، اثر انگشت host به کاربر نشان داده میشود و تأیید او لازم است؛ سپس در `/root/.ssh/known_hosts` با مجوز ۶۰۰ ثبت میشود.
- کاربر میتواند کلید خصوصی موجود خود (`~/.ssh/id_ed25519`) را بدهد، یا نصبکننده یک کلید موقت `ed25519` در `mktemp -d` میسازد و کلید عمومی آن را چاپ میکند تا یک بار در `authorized_keys` سرور خارج اضافه شود. کلید موقت بعد از اتمام حذف میشود.
- تمام فراخوانیها با argv و `subprocess.run(..., shell=False)` انجام میشوند؛ هیچ رشتهای به shell داده نمیشود.
- خروجی `ssh` در لاگ پاک میشود تا کلیدها، رمزها و TOTP چاپ نشوند.

**چیزی که هرگز در GitHub ذخیره نمیشود:** کلید خصوصی AmneziaWG، `H1..H4`، رمز ادمین، TOTP، کلید خصوصی SSH و IPهای کاربران.

## ۴) پیشنمایش قبل از اعمال تغییرات — الزامی

پیشفرض wizard حالت `dry-run` است. خروجی مثال:

```text
=== PREVIEW (dry-run) — هیچ تغییری اعمال نشده ===

سرور ایران: 203.0.113.10   iface=eth0   RAM=1.8GiB
سرور خارج: 198.51.100.20  SSH=key     fingerprint=SHA256:...

شبنت کلاینت      10.7.0.0/24
تانل             10.9.0.0/30  (Iran .2 / Exit .1)
پورت کلاینت      51820/udp
پورت تانل        51821/udp
UDP probe        5355/udp  -> 10.9.0.1
Jc              0          (کمترین latency handshake)

تغییراتی که قرار است اعمال شود:
  + IN  tcp  <IP مبدا SSH فعلی>/32  -> port 22     (قبل از هر چیز)
  + IN  udp  198.51.100.20          -> port 51821
  + IN  udp  10.9.0.2/32            -> port 5355
  + ip addr add 10.9.0.1/30 dev omawg0
  + ip route 10.7.0.0/24 dev omawg0
  + MASQUERADE روی eth0 (فقط سابنت کلاینتها)

بکاپ: /root/1mobile-snapshots/20261126-101500/
بازگشت: sudo bash quick-install.sh rollback --snapshot 20261126-101500

برای اعمال، دقیقاً تایپ کنید: APPLY
```

قواعد سختگیرانه:

1. قبل از اولین تغییر iptables/routing، IP مبدا SSH فعلی در INPUTwhitelist میشود.
2. هیچ `iptables -F`، `ip link del` روی لینکهای موجود و هیچ restart networking وجود ندارد.
3. اگر سرور دارای `role`، `.conf` یا اینترفیس زنده باشد، wizard متوقف میشود؛ دور زدن فقط با `FORCE_FRESH=1` در آزمایشگاه.
4. Peerهای زنده با `merge_peers()` حفظ میشوند.
5. یک «قفل امانت» systemd نصب میشود: اگر نصبکننده ظرف ۱۰ دقیقه heartbeat ندهد، `iptables-restore` و routeهای ذخیرهشده برگردانده میشوند تا SSH باز بماند. پس از موفقیت، قفل خلع سلاح و حذف میشود.

## ۵) ترتیب اجرا

| مرحله | عملیاتی که اجرا میشود | در صورت شکست |
|---|---|---|
| ۱ | تشخیص منابع و IPها، نمایش fingerprint SSH | توقف بدون تغییر |
| ۲ | پیشنمایش + بکاپ دو سرور | توقف بدون تغییر |
| ۳ | `deps` + `awg-check` روی هر دو | Rollback مرحلهٔ ۲ |
| ۴ | `fresh-config init` روی Iran و `fresh-config import` روی Exit از طریق SSH | Rollback |
| ۵ | `keygen` دو سرور، تبادل فقط `.pub` | Rollback |
| ۶ | پیکربندی Exit از راه دور، سپس Iran | Rollback + قفل امانت |
| ۷ | `healthcheck` دو طرف، بررسی handshake و UDP RTT | Rollback |
| ۸ | پنل + رمز هششده + TOTP، سپس `persist` | Rollback |
| ۹ | تست ساخت کاربر و تأیید اینترنت خروجی طبق TEST-PLAN | علامتگذاری failure در جدول تست |

## ۶) ساختار فایلهای پیشنهادی

```text
scripts/quick-install.sh   منو و orchestrator نازک
src/wizard.py              تشخیص، پیشنمایش، state machine (stdlib)
src/sshctl.py              پوشش ssh/scp با argv، بدون secret logging
docs/QUICK-INSTALL.md      همین سند
```

اسکریپتهای موجود (`fresh-config.sh`، `fresh-keygen.sh`، `install-deps.sh`، `install-fresh.sh`، `apply-iface.sh`، `runtime.sh`، `healthcheck.py`، `persist.sh`، `rollback*.sh`) بدون تغییر فراخوانی میشوند.

## ۷) معیار قبولی خود wizard

- اجرای بدون `APPLY` هیچ فایلی و هیچ قانون iptables/routeای را تغییر ندهد.
- اسنپشات شامل تنظیمات کامل شبکه و unitها از هر دو سرور باشد.
- `rollback --snapshot ...` شبکه را دقیقاً به وضعیت قبل برگرداند و SSH بدون وقفه بماند.
- لاگ wizard حاوی هیچ کلید خصوصی، رمز یا TOTP نباشد.
- پس از اتمام install، دستور `python3 /opt/1mobile-web-v13/healthcheck.py` روی Iran وضعیت `ok` دهد.

## ۸) سوالات باز قبل از پیادهسازی

1. آیا کلید SSH کاربر از agent استفاده شود یا مسیر صریح کلید خصوصی؟ (پیشنهاد: مسیر صریح + `BatchMode`).
2. آیا ارتقا از نصب قدیمی هم وارد wizard شود یا همان `install.sh monitor` باقی بماند؟ (پیشنهاد: باقی بماند).
3. آیا wizard اولین کاربر را هم بسازد؟ (پیشنهاد: خیر؛ کاربر از پنل ساخته شود تا تست شمارهٔ ۴ معتبر بماند).

پس از تأیید این سند و تکمیل چهار تست عملی، نسخهٔ `1.5.0` و `docs/INSTALL.md` و `CHANGELOG.md` بهروز میشوند.

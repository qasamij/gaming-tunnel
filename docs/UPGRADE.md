# ارتقا و برگشت

## ارتقا از v1.0 / v1.1 به v1.4

پنل قدیمی را دستی حذف نکنید. اسکریپت ارتقا خودش بکاپ میگیرد:

```bash
cd 1mobile-gaming-tunnel
sudo bash scripts/install.sh monitor
sudo bash scripts/install.sh runtime   # تنها در صورتی که supervisor قدیمی دارید
```

### چه چیزی حفظ میشود

- رمز، TOTP و گواهی TLS موجود (مگر اینکه `FORCE=1` بدهید).
- `users.json` و تمام کانفیگهای کلاینتها.
- کلیدها و اینترفیسهای زنده AWG (دست نخوردهاند).
- مقادیر obfuscation در `network.json` (باید با طرف مقابل تانل یکسان بماند).

### بکاپ

قبل از هر تغییر، پشتیبان در این مسیر ساخته میشود:

```text
/etc/1mobile-panel/backup/upgrade-<timestamp>/
```

همچنین میتوانید هر زمان بصورت دستی بگیرید:

```bash
sudo bash scripts/install.sh backup
```

## برگشت

```bash
sudo bash scripts/install.sh rollback           # واحد systemd پنل قدیمی
sudo bash scripts/install.sh rollback-runtime   # واحد supervisor قدیمی
```

پس از برگشت:

```bash
sudo systemctl daemon-reload
sudo systemctl status 1mobile-panel
```

> اگر نصب قدیمی اصلاً systemd نداشت، rollback فقط فایل واحد جدید را حذف میکند؛ پنل متوقف میشود تا دوباره بصورت دستی راهاندازی شود.

## حذف کامل

```bash
sudo CONFIRM=1 bash scripts/install.sh uninstall
```

این دستور سرویسها، کد پنل،DATA_DIR و کلیدها را حذف میکند. حتماً قبل از آن بکاپ بگیرید.

## تغییر نسخه بعدی

1. tag بزنید: `git tag -a v1.4.0 -m "Release 1.4.0"` و `git push --tags`.
2. فایلها را در سرور بهروز کنید و دوباره `install.sh monitor` بزنید.
3. تستها را اجرا کنید: `make test`.

## هشدار

هرگز `network.json` را در سرور Iran و Exit ناسازگار نکنید. `H1-H4`، `S1`، `S2`، `Jc`، `Jmin` و `Jmax` باید در هر دو سرور و در کانفیگ تمام کلاینتها یکسان باشند، وگرنه handshake برقرار نمیشود.

# تفکیک عملیات مدیریتی از پنل (طرح، اجرا بعد از تستهای عملی)

## وضعیت فعلی

پنل (`1mobile-panel.service`) با کاربر `root` اجرا میشود، چون مستقیم `awg`، `ip`، `sysctl` و `iptables` را فراخوانی میکند. رمز هششده، TOTP، CSRF و محدودیت تلاش خطر ورود غیرمجاز را کم میکنند، ولی każdy اشکال در handlerهای HTTP در عمل دسترسی root به سرور میدهد. این برای انتشار عمومی مناسب نیست.

## طراحی پیشنهادی

یک سرویس جداگانهٔ `1mobile-ops.service` مسئول تمام فرمانهای privileged میشود:

```text
browser --HTTPS--> 1mobile-panel.service (غیر root)
                        |
                        | Unix socket /run/1mobile-ops/ops.sock (0660)
                        v
                  1mobile-ops.service (تنها CAP_NET_ADMIN مجاز است)
                        |
                        +--awg / ip / sysctl / iptables (argv ثابت، بدون shell)
```

### اصول الزامی

- پنل بهطور کامل غیر root اجرا شود و فقط به سوکت و فایلهایی که نیاز دارد دسترسی داشته باشد.
- سرویس ops فقط از طریق Unix socket قابل دسترسی است، نه TCP؛ مالکیت `1mobile-panel:1mobile-ops` و مجوز `0660`.
- پروتکل: JSON خطی با طول مشخص، شامل `action` و آرگومانها. **هیچ رشتهٔ shell و هیچ `eval`**.
- لیست سفید ثابت اکشنها: `user.create`, `user.remove`, `user.disable`, `peer.list`, `metrics`, `diagnostics`, `repair`. هر اکشن schemaٔ خودش را validate میکند (نام `[A-Za-z0-9_-]{1,32}`، pubkey base64 دقیقاً ۴۴ کاراکتر، CIDR معتبر، اعتبار/سهمیهٔ عددی).
- تمام فرمانها با لیست argv و `timeout` اجرا میشوند (همان الگوی فعلی `ops.call` / `backend.run`) و خروجیها در audit log با timestamp نوشته میشوند.
- سختگیری systemd: `NoNewPrivileges=true`, `PrivateTmp=true`, `ProtectSystem=strict`, `ProtectHome=true`, `ReadOnlyPaths=...`, `CapabilityBoundingSet=CAP_NET_ADMIN`, `RestrictAddressFamilies=AF_UNIX AF_INET`.
- workerهای مانیتورینگ (`collect_worker`) و healthcheck نیز به جای فراخوانی مستقیم `awg`، از همان سرویس ops با اکشن خواندنی `peer.list` استفاده میکنند.

### مراحل مهاجرت (بعد از تستعملی)

1. چهار تست [`docs/TEST-PLAN.md`](TEST-PLAN.md) روی VPS آزمایشی انجام و ثبت شوند.
2. سرویس ops و یونیت پنل غیر root در همان سرور آزمایشی نصب و تست شوند؛ مسیر برگشت به سرویس قدیمی آماده باشد.
3. پنل به تدریج به سمت socket ops منتقل شود: ابتدا اکشنهای خواندنی، سپس ساخت/حذف کاربر.
4. تست مجدد چهار سناریو با معیار همان جدول، سپس انتشار.

## چرا الان اجرا نشد؟

این تغییر، سطح حمله و مسیر اجرا را کاملاً جابهجا میکند و بدون تست واقعیِ ریبوت/SSH/کاربر نمیتوان مطمئن شد که «بدون قطعی» باقی میماند. مطابق پیشنهاد شما، قبل از اضافه کردن این قابلیت، ابتدا نصب صفر، بستن SSH، ریبوت و ساخت کاربر را روی دو VPS آزمایشی تأیید میکنیم.

## وضعیت کوتاهمدت

تا مهاجرت کامل: TCP/9443 را در معرض عموم نگذارید؛ از SSH tunnel یا فایروال محدودکنندهٔ موقتی استفاده کنید و مطابق [`docs/SECURITY.md`](SECURITY.md) برای IP متغیر قانون `DROP` دائمی ننویسید.

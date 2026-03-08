# Payment Distribution System — Django REST Framework

## Structure

```
payments/
├── models.py                          # All DB models
├── views.py                           # DRF API endpoints
├── urls.py                            # URL routing
├── admin.py                           # Django admin
├── services/
│   ├── split_calculator.py            # Split logic + ledger
│   ├── sale_service.py                # Init → complete → refund
│   └── withdrawal_service.py         # Withdrawal + balance
└── management/commands/
    ├── nightly_batch.py               # 11PM batch transfer
    └── reconcile.py                   # 6AM reconciliation
```

---

## Setup

### 1. Install dependencies
```bash
pip install djangorestframework requests django-environ
```

### 2. settings.py additions
```python
INSTALLED_APPS = [..., "rest_framework", "payments"]

AUTH_USER_MODEL = "payments.User"

PAYSTACK_SECRET_KEY = env("PAYSTACK_SECRET_KEY")
LEDGER_HASH_SALT    = env("LEDGER_HASH_SALT")

MIN_WITHDRAWAL_DRIVER   = 100000   # ₦1,000 in kobo
MIN_WITHDRAWAL_BUSINESS = 200000   # ₦2,000 in kobo
MIN_WITHDRAWAL_REFERRAL = 50000    # ₦500 in kobo
```

### 3. .env file
```env
PAYSTACK_SECRET_KEY=sk_live_xxxxxxxxxxxxxxxx
LEDGER_HASH_SALT=<run: python -c "import secrets; print(secrets.token_hex(32))">
```

### 4. Migrate + seed config
```bash
python manage.py makemigrations payments
python manage.py migrate

# Seed platform split config
python manage.py shell
>>> from payments.models import PlatformConfig
>>> configs = [
...   ("platform_cut_percent",       "10"),
...   ("driver_cut_percent",         "60"),
...   ("business_owner_cut_percent", "25"),
...   ("referral_cut_percent",       "5"),
... ]
>>> for k, v in configs:
...     PlatformConfig.objects.get_or_create(key=k, defaults={"value": v})
```

### 5. Include URLs
```python
# project/urls.py
urlpatterns = [
    path("api/", include("payments.urls")),
    path("admin/", admin.site.urls),
]
```

---

## Cron Jobs (schedule both)

```bash
# 11PM — nightly batch payouts
0 23 * * * cd /app && python manage.py nightly_batch

# 6AM — reconcile last night vs Paystack
0 6  * * * cd /app && python manage.py reconcile
```

On **Railway**: add two cron services pointing to the same repo.
On **Render**: use Render Cron Jobs (free tier available).

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/sales/initialize/` | Create payment + get Paystack URL |
| POST | `/api/sales/<id>/complete/` | Mark service done, credit ledgers |
| POST | `/api/sales/<id>/refund/` | Refund user, reverse ledger |
| GET  | `/api/wallet/balance/` | Get balance summary |
| POST | `/api/wallet/withdraw/` | Queue withdrawal request |
| GET  | `/api/wallet/withdrawals/` | Withdrawal history |
| POST | `/api/webhooks/paystack/` | Paystack webhook receiver |

---

## Full Payment Flow

```
1. POST /api/sales/initialize/     → get payment URL
2. User pays on Paystack
3. Paystack → POST /api/webhooks/paystack/ (charge.success)
   → sale marked 'in_escrow'
4. Service performed
5. POST /api/sales/<id>/complete/  → ledgers credited
6. Driver/Business/Referral → POST /api/wallet/withdraw/
7. 11PM: python manage.py nightly_batch
   → bulk transfer sent to Paystack
8. Paystack → POST /api/webhooks/paystack/ (transfer.success/failed)
   → marked complete or re-queued
9. 6AM: python manage.py reconcile
   → verifies everything matches Paystack
```

---

## Security Checklist

- [ ] `LEDGER_HASH_SALT` in env — never in code or DB
- [ ] `LedgerEntry.save()` raises if row already exists (immutable)
- [ ] `LedgerEntry.delete()` always raises
- [ ] Webhook signature verified via HMAC-SHA512 before processing
- [ ] Reconciliation mismatches alert admin (add Slack/email hook)
- [ ] DB backups enabled
- [ ] Admin `has_delete_permission = False` on ledger + webhook log

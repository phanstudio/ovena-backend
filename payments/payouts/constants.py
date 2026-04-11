from django.conf import settings

DAILY_WITHDRAWAL_LIMIT_COUNT = int(getattr(settings, "DAILY_WITHDRAWAL_LIMIT_COUNT", 5))
DAILY_WITHDRAWAL_LIMIT_AMOUNT = int(getattr(settings, "DAILY_WITHDRAWAL_LIMIT_AMOUNT_KOBO", 50_000_000))
WITHDRAWAL_COOLDOWN_HOURS = int(getattr(settings, "WITHDRAWAL_COOLDOWN_HOURS", 2))

MINIMUM_BY_ROLE = {
    "driver": int(getattr(settings, "MIN_WITHDRAWAL_DRIVER", 100_000)),
    "business_owner": int(getattr(settings, "MIN_WITHDRAWAL_BUSINESS", 200_000)),
    "referral": int(getattr(settings, "MIN_WITHDRAWAL_REFERRAL", 50_000)),
}

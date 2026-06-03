from django.db import models
from menu.models import MenuCategory, MenuItem
from accounts.models import Business
from django.conf import settings


class Coupons(models.Model):
    """
    Two coupon modes, controlled by is_reward:

    is_reward=False  (marketing coupon)
        - Distributed as a code (SMS, promo banner, etc.)
        - uses_count increments on every redemption.
        - Redeemed by submitting coupon_code on an order.

    is_reward=True  (reward coupon)
        - Awarded to individual users via the spin wheel.
        - uses_count increments at award time (not at redemption).
        - Once uses_count >= max_uses the coupon is removed from the wheel.
        - Redeemed by submitting the wallet_entry_id on an order;
          redemption marks the UserCouponWallet row is_used=True.
    """

    TYPE_CHOICES = [
        ("delivery", "Free-delivery"),
        ("itemdiscount", "Amount-off-an-Item"),
        ("categorydiscount", "Amount-off-a-category"),
        ("BxGy", "Buy-X-Get-Y"),
    ]

    SCOPE_CHOICES = [
        ("global", "Platform-wide"),
        ("business", "Business-only"),
    ]

    DISCOUNT_CHOICES = [("percent", "Percent"), ("amount", "Fixed-amount")]

    code = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=255, blank=True)

    coupon_type = models.CharField(max_length=30, choices=TYPE_CHOICES, default="delivery")

    # categorydiscount
    category = models.ForeignKey(
        MenuCategory, on_delete=models.CASCADE, null=True, blank=True, related_name="coupons"
    )
    # itemdiscount
    item = models.ForeignKey(
        MenuItem, on_delete=models.CASCADE, null=True, blank=True, related_name="coupons"
    )

    # BxGy
    buy_amount = models.PositiveIntegerField(default=0)
    get_amount = models.PositiveIntegerField(default=0)
    buy_item = models.ForeignKey(
        MenuItem, on_delete=models.CASCADE, null=True, blank=True, related_name="buy_coupons"
    )
    get_item = models.ForeignKey(
        MenuItem, on_delete=models.CASCADE, null=True, blank=True, related_name="get_coupons"
    )

    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, default="business")
    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, null=True, blank=True, related_name="coupons"
    )

    discount_type = models.CharField(max_length=10, choices=DISCOUNT_CHOICES, default="percent")
    discount_value = models.DecimalField(max_digits=8, decimal_places=2, default=0.0)

    max_uses = models.PositiveIntegerField(null=True, blank=True)
    uses_count = models.PositiveIntegerField(default=0)

    # False → marketing coupon (code-based, uses_count tracks redemptions)
    # True  → reward coupon  (wallet-based, uses_count tracks awards)
    is_reward = models.BooleanField(
        default=False,
        help_text=(
            "Reward coupons are awarded via the spin wheel and redeemed through the "
            "user's wallet. Marketing coupons are distributed as codes."
        ),
    )

    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        kind = "reward" if self.is_reward else "marketing"
        return f"[{kind}] {self.code}"


class CouponWheel(models.Model):
    # Only reward coupons (is_reward=True) should be assigned here.
    coupons = models.ManyToManyField(Coupons)
    max_entries_amount = models.SmallIntegerField(default=6)
    is_active = models.BooleanField(default=False)


class UserCouponWallet(models.Model):
    """
    Tracks reward coupons awarded to users (from wheel spins, promotions, etc.)
    before they are redeemed on an order.

    Lifecycle:
        awarded  → is_used=False, used_at=None
        redeemed → is_used=True,  used_at=<timestamp>
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="coupon_wallet",
    )
    coupon = models.ForeignKey(
        "coupons_discount.Coupons",
        on_delete=models.CASCADE,
        related_name="user_wallets",
    )

    awarded_at = models.DateTimeField(auto_now_add=True)
    awarded_from_wheel_spin = models.BooleanField(default=False)

    is_used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "user_coupon_wallet"
        indexes = [
            models.Index(fields=["user", "is_used"]),
            models.Index(fields=["coupon", "is_used"]),
        ]

    def __str__(self):
        status = "Used" if self.is_used else "Available"
        return f"{self.user} - {self.coupon.code} - {status}"

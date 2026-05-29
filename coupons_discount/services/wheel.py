from django.db import transaction
from django.db.models import F

from coupons_discount.models import Coupons, UserCouponWallet
from .helper import eligible_coupon_for_wheel_q

# ---------------------------------------------------------------------------
# Wheel / award service
# ---------------------------------------------------------------------------

class WheelService:
    """Handles awarding reward coupons from the spin wheel."""

    @staticmethod
    def award_coupon_to_user(coupon: Coupons, user, from_spin: bool = True) -> "UserCouponWallet | None":
        """
        Award a reward coupon to a user:
          1. Atomically increment uses_count (acts as the award counter).
          2. If uses_count reached max_uses, remove coupon from the wheel
             so it can no longer be landed on.
          3. Create a UserCouponWallet entry for the user.

        Returns the wallet entry on success, None if the coupon is exhausted
        (race condition: another spin claimed the last slot).
        """
        if not coupon.is_reward:
            raise ValueError("award_coupon_to_user called on a non-reward coupon.")

        with transaction.atomic():
            # Claim one slot atomically.
            updated = (
                Coupons.objects
                .filter(pk=coupon.pk)
                .filter(eligible_coupon_for_wheel_q())
                .update(uses_count=F("uses_count") + 1)
            )
            if updated == 0:
                # Slot was already exhausted (race condition) or coupon is invalid.
                return None

            # Refresh to get the new uses_count value.
            coupon.refresh_from_db(fields=["uses_count", "max_uses"])

            # If fully exhausted, remove from all wheels.
            # if coupon.max_uses is not None and coupon.uses_count >= coupon.max_uses:
            #     from coupons_discount.models import CouponWheel  # avoid circular at module level
            #     for wheel in CouponWheel.objects.filter(coupons=coupon):
            #         wheel.coupons.remove(coupon)
            # the above is unnecessary because the coupon won't show;

            wallet_entry = UserCouponWallet.objects.create(
                user=user,
                coupon=coupon,
                awarded_from_wheel_spin=from_spin,
            )

        return wallet_entry

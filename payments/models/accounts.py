from __future__ import annotations

from abc import abstractmethod

from django.db import models

# from accounts.models import User  # adjust import to your actual User path


class AbstractPayoutAccount(models.Model):
    """
    Shared base for all payout account types.

    Concrete subclasses must implement `get_recipient_code()` so the
    withdrawal pipeline can resolve a Paystack recipient without knowing
    which account model it is talking to.
    """

    paystack_recipient_code = models.CharField(max_length=100, blank=True)
    bank_code = models.CharField(max_length=10, blank=True)
    bank_account_number = models.CharField(max_length=20, blank=True)
    bank_account_name = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    @abstractmethod
    def get_recipient_code(self) -> str:
        """Return the Paystack recipient code for this payout account."""
        raise NotImplementedError


# class UserAccount(AbstractPayoutAccount):
#     """
#     Payment-specific extension of the core User model.
#     Used for individual actors: drivers, referral users, etc.
#     """

#     user = models.OneToOneField(
#         User,
#         on_delete=models.CASCADE,
#         related_name="payment_account",
#     )

#     class Meta:
#         db_table = "payments_user_account"

#     def get_recipient_code(self) -> str:
#         return self.paystack_recipient_code or ""

#     def __str__(self) -> str:
#         return f"{self.bank_account_name} ({self.bank_code})"
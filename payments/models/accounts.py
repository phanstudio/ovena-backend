from __future__ import annotations
from abc import abstractmethod
from django.db import models

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
    paystack_customer_code = models.CharField(max_length=100, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    @abstractmethod
    def get_recipient_code(self) -> str:
        """Return the Paystack recipient code for this payout account."""
        raise NotImplementedError

from __future__ import annotations

from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from accounts.models.business import BusinessPayoutAccount
from accounts.models.driver import DriverBankAccount
from payments.models import UserAccount
from payments.payouts.tasks import ensure_paystack_recipient_for_driver
from payments.payouts.tasks import ensure_paystack_recipient_for_business_admin


@receiver(pre_save, sender=DriverBankAccount)
def _cache_previous_bank_state(sender, instance: DriverBankAccount, **kwargs):
    if not instance.pk:
        instance._was_verified = False
        return
    prev = DriverBankAccount.objects.filter(pk=instance.pk).values_list("is_verified", flat=True).first()
    instance._was_verified = bool(prev)


@receiver(post_save, sender=DriverBankAccount)
def _create_paystack_recipient_on_verified(sender, instance: DriverBankAccount, created: bool, **kwargs):
    if not instance.is_verified:
        return
    if getattr(instance, "_was_verified", False):
        return
    account = UserAccount.objects.filter(user=instance.driver.user).first()
    if account and account.paystack_recipient_code:
        return
    ensure_paystack_recipient_for_driver.delay(instance.driver_id)


@receiver(post_save, sender=BusinessPayoutAccount)
def _sync_business_admin_paystack_recipient(sender, instance: BusinessPayoutAccount, created: bool, **kwargs):
    admin = getattr(instance.business, "admin", None)
    if not admin:
        return
    if not instance.bank_code or not instance.account_number or not instance.account_name:
        return
    ensure_paystack_recipient_for_business_admin.delay(admin.id)

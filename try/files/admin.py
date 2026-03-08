from django.contrib import admin
from payments.models import (
    User, PlatformConfig, Sale, LedgerEntry,
    Withdrawal, PaystackWebhookLog, ReconciliationLog
)


@admin.register(PlatformConfig)
class PlatformConfigAdmin(admin.ModelAdmin):
    list_display = ("key", "value", "description", "updated_at")
    search_fields = ("key",)


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display  = ("reference", "payer", "total_amount_ngn", "status", "created_at")
    list_filter   = ("status",)
    search_fields = ("reference", "paystack_reference")
    readonly_fields = ("split_snapshot", "created_at", "updated_at")

    def total_amount_ngn(self, obj):
        return f"₦{obj.total_amount / 100:.2f}"


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display  = ("user", "role", "type", "amount_ngn", "balance_after_ngn", "hash_valid", "created_at")
    list_filter   = ("type", "role")
    search_fields = ("user__username",)
    readonly_fields = ("row_hash", "created_at")

    def amount_ngn(self, obj):
        return f"₦{obj.amount / 100:.2f}"

    def balance_after_ngn(self, obj):
        return f"₦{obj.balance_after / 100:.2f}"

    def hash_valid(self, obj):
        return "✅" if obj.verify_hash() else "❌ TAMPERED"
    hash_valid.short_description = "Hash"

    def has_change_permission(self, request, obj=None):
        return False  # read-only in admin too

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Withdrawal)
class WithdrawalAdmin(admin.ModelAdmin):
    list_display  = ("user", "amount_ngn", "status", "batch_date", "retry_count", "requested_at")
    list_filter   = ("status", "batch_date")
    search_fields = ("user__username", "paystack_transfer_ref")
    readonly_fields = ("ledger_entry", "requested_at")

    def amount_ngn(self, obj):
        return f"₦{obj.amount / 100:.2f}"


@admin.register(PaystackWebhookLog)
class WebhookLogAdmin(admin.ModelAdmin):
    list_display = ("event_type", "paystack_reference", "signature_valid", "processed", "received_at")
    list_filter  = ("event_type", "signature_valid", "processed")
    readonly_fields = ("payload", "received_at")

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ReconciliationLog)
class ReconciliationLogAdmin(admin.ModelAdmin):
    list_display = ("run_date", "status", "total_checked", "mismatches", "ran_at")
    list_filter  = ("status",)
    readonly_fields = ("mismatch_details",)

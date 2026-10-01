from django.contrib import admin
from referrals.models import ProfileReferral, ReferralPayout


@admin.register(ProfileReferral)
class ProfileReferralAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "referrer_user",
        "referee_user",
        "referrer_role",
        "referee_role",
        "fraud_status",
        "converted_at",
        "is_consumed",
        "created_at",
    )
    list_filter = ("referrer_role", "referee_role", "fraud_status", "is_consumed")
    search_fields = (
        "referrer_user__email",
        "referee_user__email",
        "referrer_user__phone_number",
        "referee_user__phone_number",
        "referee_device_id",
        "referee_ip_address",
    )


@admin.register(ReferralPayout)
class ReferralPayoutAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "units_paid", "conversion_rate", "amount", "created_at")
    search_fields = ("user__email", "user__phone_number")

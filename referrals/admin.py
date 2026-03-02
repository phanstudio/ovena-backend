from django.contrib import admin
from referrals.models import ProfileReferral


@admin.register(ProfileReferral)
class ProfileReferralAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "referrer_user",
        "referee_user",
        "created_at",
        "converted_at",
    )
    search_fields = ("referrer_user__email", "referee_user__email")

from django.contrib import admin

from driver_api.models import (
    DriverLedgerEntry,
    DriverNotification,
    DriverWallet,
    DriverWithdrawalRequest,
    SupportFAQCategory,
    SupportFAQItem,
)


admin.site.register(DriverWallet)
admin.site.register(DriverLedgerEntry)
admin.site.register(DriverWithdrawalRequest)
admin.site.register(DriverNotification)
admin.site.register(SupportFAQCategory)
# add faqa from here
admin.site.register(SupportFAQItem)


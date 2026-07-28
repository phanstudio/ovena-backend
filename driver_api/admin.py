from django.contrib import admin

from driver_api.models import (
    SupportFAQCategory,
    SupportFAQItem,
)


admin.site.register(SupportFAQCategory)
# add faqa from here
admin.site.register(SupportFAQItem)


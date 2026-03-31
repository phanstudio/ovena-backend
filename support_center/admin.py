from django.contrib import admin

from support_center.models import SupportTicket, SupportTicketMessage


admin.site.register(SupportTicket)
admin.site.register(SupportTicketMessage)

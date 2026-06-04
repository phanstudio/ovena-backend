from django.db import models

class OrderStatus(models.TextChoices):
    PAYMENT_PENDING = "payment_pending", "Payment Pending"
    PENDING = "pending", "Pending"
    CONFIRMED = "confirmed", "Confirmed"
    PREPARING = "preparing", "Preparing"
    READY = "ready", "Ready for Pickup"
    DRIVER_ASSIGNED = "driver_assigned", "Driver Assigned"
    PICKED_UP = "picked_up", "Picked Up"
    ON_THE_WAY = "on_the_way", "On the Way"
    DELIVERED = "delivered", "Delivered"
    CANCELLED = "cancelled", "Cancelled"


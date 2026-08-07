from django.db import models

class OrderStatus(models.TextChoices):
    AWAITING_PAYMENT_METHOD = "awaiting_payment_method", "Awaiting Payment Method"  # NEW
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
    PAYMENT_INITIALIZATION_FAILED = "payment_initialization_failed", "Payment Initialization Failed"

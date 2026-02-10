from django.db import models
from .main import (
    MenuCategory, MenuItem, Restaurant, BaseItemAvailability, 
    CustomerProfile, MenuItemAddon, VariantOption, Branch
)
from accounts.models import (
    DriverProfile, User
)
from .payment import Payment

from coupons_discount.models import Coupons, CouponWheel


"""
Updated models with GIS support and WebSocket fields
Add these to your existing models.py
"""
from django.contrib.gis.db import models as gis_models
from django.contrib.gis.geos import Point
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.measure import D
from django.db import models
from django.utils import timezone


# ===== UPDATE EXISTING MODELS =====

class Order(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),  # waiting for branch confirmation
        ("confirmed", "Confirmed"),  # branch accepted, waiting payment
        ("payment_pending", "Payment Pending"),  # payment URL generated
        ("preparing", "Preparing"),  # payment confirmed, cooking
        ("ready", "Ready for Pickup"),  # food ready, finding driver
        ("driver_assigned", "Driver Assigned"),  # driver notified
        ("picked_up", "Picked Up"),  # driver has food
        ("on_the_way", "On the Way"),  # heading to customer
        ("delivered", "Delivered"),  # completed
        ("cancelled", "Cancelled"),
    ]

    orderer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="orders")
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="orders")
    driver = models.ForeignKey(DriverProfile, on_delete=models.CASCADE, related_name="orders", blank=True, null=True)
    
    # Pricing
    delivery_price = models.DecimalField(decimal_places=2, max_digits=10, default=0)
    ovena_commission = models.DecimalField(max_digits=5, decimal_places=2, default=10)
    coupons = models.ForeignKey(Coupons, on_delete=models.CASCADE, related_name="orders", blank=True, null=True)
    
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Payment
    payment = models.OneToOneField('Payment', on_delete=models.CASCADE, related_name="order", null=True, blank=True)
    payment_reference = models.CharField(max_length=200, blank=True, null=True)
    payment_initialized_at = models.DateTimeField(blank=True, null=True)
    payment_completed_at = models.DateTimeField(blank=True, null=True)
    
    # Delivery verification
    delivery_secret_hash = models.CharField(max_length=200)
    delivery_verified = models.BooleanField(default=False)
    delivery_verified_at = models.DateTimeField(blank=True, null=True)
    
    # Order tracking
    order_number = models.IntegerField(default=0)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="pending")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(blank=True, null=True)
    assigned_at = models.DateTimeField(blank=True, null=True)
    picked_up_at = models.DateTimeField(blank=True, null=True)
    delivered_at = models.DateTimeField(blank=True, null=True)
    last_modified_at = models.DateTimeField(auto_now=True)
    
    # WebSocket group management
    websocket_group_name = models.CharField(max_length=100, blank=True, null=True)
    
    # Estimated times
    estimated_prep_time = models.IntegerField(default=0, help_text="Minutes")
    estimated_delivery_time = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['driver', 'status']),
            models.Index(fields=['branch', 'status']),
        ]
    
    def __str__(self):
        return f"Order #{self.order_number} - {self.status}"
    
    def save(self, *args, **kwargs):
        if not self.websocket_group_name:
            self.websocket_group_name = f"order_{self.id}" if self.id else None
        super().save(*args, **kwargs)
    
    # @property
    # def websocket_group_name(self):
    #     return f"order_{self.pk}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete= models.CASCADE, related_name= "items")
    menu_item = models.ForeignKey(MenuItem, on_delete= models.CASCADE, related_name= "orders")

    line_total = models.DecimalField(decimal_places= 5, max_digits= 12, default= 0)
    price = models.DecimalField(decimal_places= 5, max_digits= 12, default= 0)
    added_total = models.DecimalField(decimal_places= 5, max_digits= 12, default= 0) # is this needed
    discount_amount = models.DecimalField(decimal_places= 5, max_digits= 12, default= 0)

    # we can create a snap shot of the entire process but we will use a json instead addon, variant, price
    addons = models.ManyToManyField(MenuItemAddon) 
    variants = models.ManyToManyField(VariantOption)
    quantity = models.SmallIntegerField(default=1)
    is_available = models.BooleanField(default=True)

    menu_availability = models.ForeignKey( # should be automatic sha
        BaseItemAvailability, on_delete=models.SET_NULL,
        related_name="order_items", null=True, blank=True
    )

    def calculate_addon_price(self): # breaks if no addons or valiants
        """Only used once on creation."""
        addon_total = 0
        variant_total = 0
        if self.variants:
            variant_total = sum(v.price_diff for v in self.variants.all()) # this feels wrong could be improved
        if self.addons:
            addon_total = sum(a.price for a in self.addons.all())
        return addon_total + variant_total
    
    def save(self, *args, **kwargs): # validate coupons in views # breaks if no menu avalibility
        # Only calculate when creating a new record
        if not self.pk:
            # self.price = #self.menu_availability.effective_price
            # self.added_total = self.calculate_addon_price()
            # self.line_total = (self.price + self.added_total)* self.quantity
            ...
        super().save(*args, **kwargs)


# ===== NEW MODELS =====

class OrderEvent(models.Model):
    """Audit log for order state changes"""
    EVENT_TYPES = [
        ('created', 'Order Created'),
        ('confirmed', 'Branch Confirmed'),
        ('rejected', 'Branch Rejected'),
        ('payment_pending', 'Payment Pending'),
        ('payment_completed', 'Payment Completed'),
        ('payment_failed', 'Payment Failed'),
        ('preparing', 'Preparing Food'),
        ('ready', 'Ready for Pickup'),
        ('driver_searching', 'Searching for Driver'),
        ('driver_assigned', 'Driver Assigned'),
        ('driver_rejected', 'Driver Rejected'),
        ('picked_up', 'Order Picked Up'),
        ('in_transit', 'In Transit'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]
    
    ACTOR_TYPES = [
        ('customer', 'Customer'),
        ('driver', 'Driver'),
        ('branch', 'Branch'),
        ('system', 'System'),
    ]
    
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='events')
    event_type = models.CharField(max_length=50, choices=EVENT_TYPES)
    
    # Who triggered this event
    actor_type = models.CharField(max_length=20, choices=ACTOR_TYPES)
    actor_id = models.IntegerField(null=True, blank=True)
    
    # State transition
    old_status = models.CharField(max_length=30, blank=True, null=True)
    new_status = models.CharField(max_length=30, blank=True, null=True)
    
    # Additional context
    metadata = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['order', '-timestamp']),
        ]
    
    def __str__(self):
        return f"{self.order.order_number} - {self.event_type} @ {self.timestamp}"


class ChatMessage(models.Model):
    """Private messaging between order participants"""
    SENDER_TYPES = [
        ('customer', 'Customer'),
        ('driver', 'Driver'),
        ('branch', 'Branch'),
    ]
    
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='messages')
    
    # Sender
    sender_type = models.CharField(max_length=20, choices=SENDER_TYPES)
    sender_id = models.IntegerField()
    
    # Recipient
    recipient_type = models.CharField(max_length=20, choices=SENDER_TYPES)
    recipient_id = models.IntegerField()
    
    # Message
    message = models.TextField()
    
    # Status
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['order', 'created_at']),
            models.Index(fields=['sender_type', 'sender_id']),
        ]
    
    def __str__(self):
        return f"{self.sender_type} to {self.recipient_type}: {self.message[:50]}"

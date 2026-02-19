from django.db import models
from menu.models import MenuCategory, MenuItem
from accounts.models import Business


class Coupons(models.Model): # are coupons for the entire order or a single order item 
    #build coupon view
    # use coupon is in order 
    
    TYPE_CHOICES = [
        ("delivery", "Free-delivery"),
        ("itemdiscount", "Amount-off-an-Item"),
        ("categorydiscount", "Amount-off-a-category"),
        ("BxGy", "Buy-X-Get-Y")
    ]

    SCOPE_CHOICES = [
        ("global", "Platform-wide"),
        ("restaurant", "Restaurant-only"),
    ]
    DISCOUNT_CHOICES = [("percent", "Percent"), ("amount", "Fixed-amount")]

    code = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=255, blank=True)

    coupon_type = models.CharField(max_length=30, choices=TYPE_CHOICES, default="delivery")
    # categorydiscount
    category = models.ForeignKey(MenuCategory, on_delete=models.CASCADE, null=True, blank=True, related_name= "coupons")
    # itemdiscount
    item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, null=True, blank=True, related_name= "coupons")

    # BxGy
    buy_amount = models.PositiveIntegerField(default=0)
    get_amount = models.PositiveIntegerField(default=0)
    buy_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, null=True, blank=True, related_name="buy_coupons")
    get_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, null=True, blank=True, related_name="get_coupons")

    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, default="restaurant")
    business = models.ForeignKey(Business, on_delete=models.CASCADE, null=True, blank=True, related_name="coupons")

    discount_type = models.CharField(max_length=10, choices=DISCOUNT_CHOICES, default="percent")
    discount_value = models.DecimalField(max_digits=8, decimal_places=2, default=0.0)

    # min_order_value = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    max_uses = models.PositiveIntegerField(null=True, blank=True)
    uses_count = models.PositiveIntegerField(default=0)

    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField(blank=True, null= True)
    is_active = models.BooleanField(default=True)

class CouponWheel(models.Model):
    coupons = models.ManyToManyField(Coupons)
    max_entries_amount = models.SmallIntegerField(default=6)
    is_active = models.BooleanField(default=False)
    

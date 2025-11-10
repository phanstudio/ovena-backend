from django.db import models
from .main import (
    MenuCategory, MenuItem, Restaurant, BaseItemAvailability, 
    CustomerProfile, MenuItemAddon, VariantOption, Branch
)
from accounts.models import (
    DriverProfile
)
from .payment import Payment

# appliing checking and attaching said coupons
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
    category = models.ForeignKey(MenuCategory, on_delete=models.CASCADE, null=True, blank=True, related_name= "coupons")
    item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, null=True, blank=True, related_name= "coupons")
    # get = models.ForeignKey(MenuItem, on_delete=models.CASCADE, null=True, blank=True, related_name= "coupons")
    # get is for a case where we want to buy buger get something else.
    buy_amount = models.PositiveIntegerField(default=0)
    get_amount = models.PositiveIntegerField(default=0)

    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, default="restaurant")
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, null=True, blank=True, related_name="coupons")

    discount_type = models.CharField(max_length=10, choices=DISCOUNT_CHOICES, default="percent")
    discount_value = models.DecimalField(max_digits=8, decimal_places=2, default=0.0)

    # min_order_value = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    max_uses = models.PositiveIntegerField(null=True, blank=True)
    uses_count = models.PositiveIntegerField(default=0)

    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField(blank=True, null= True)
    is_active = models.BooleanField(default=True)

# calculate the distance to get the drivers amount
# create a way to pick from the closest branch
# order -> accepted -> pay -> accepted by driver -> ontheway -> delived -> cancelled
class Order(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"), # order
        ("confirmed", "Confirmed"), # accepted by rest,  can cancle
        ("pay", "Pay"), # if pay not made cancle the order
        ("preparing", "Preparing"), # 
        ("ready", "Ready for Pickup"), # accept for driver
        ("on_the_way", "On the Way"), # 
        ("delivered", "Delivered"), # ("Completed", "completed"),
        ("cancelled", "Cancelled"),
    ]

    orderer = models.ForeignKey(CustomerProfile, on_delete= models.CASCADE, related_name="orders")
    branch = models.ForeignKey(Branch, on_delete= models.CASCADE, related_name= "orders")
    
    driver = models.ForeignKey(DriverProfile, on_delete= models.CASCADE, related_name= "orders", blank=True, null= True)
    delivery_price = models.DecimalField(decimal_places= 5, max_digits= 10, default= 0)
    ovena_commision = models.DecimalField(max_digits=5, decimal_places=2, default= 10)
    coupons = models.ForeignKey(Coupons, on_delete= models.CASCADE, related_name= "coupons", blank=True, null= True)
    payment = models.OneToOneField(Payment, on_delete= models.CASCADE, related_name="order", null= True, blank= True)

    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)        # sum(line_total)
    discount_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)  # sum(discount_amount)
    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)     # subtotal - discount_total + delivery

    # if it is zero then delivery fee is should show free delivery
    # coupons = models.ForeignKey(Coupons, on_delete= models.CASCADE, related_name= "coupons") # feels wrong
    # we can use a signal to set the coupons used parameter
    # or we can apply it in the view
    order_number = models.IntegerField(default= 0) # randomily generate the code
    status = models.CharField(max_length= 30, choices= STATUS_CHOICES, default= "pending")
    created_at = models.DateTimeField(auto_now_add=True)
    last_modified_at = models.DateTimeField(auto_now=True)

    # new for verification
    # payment_reference = models.CharField(max_length= 200) # for saving the payment refrence to get find the order
    delivery_secret_hash = models.CharField(max_length= 200)
    delivery_verified = models.BooleanField(default= False)
    delivery_verified_at = models.DateTimeField(blank=True, null=True)
    
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

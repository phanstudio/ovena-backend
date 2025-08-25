from django.db import models
from accounts.models import (
    Restaurant, Branch
)

class Menu(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name="menus")
    name = models.CharField(max_length=255)  # e.g., "Lunch Menu", "Weekend Specials"
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.restaurant.company_name} - {self.name}"

class MenuCategory(models.Model):
    menu = models.ForeignKey(Menu, on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(max_length=255)  # e.g., "Burgers", "Drinks", "Desserts"
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order"]

    def __str__(self):
        return f"{self.menu.name} - {self.name}"

class MenuItem(models.Model):
    category = models.ForeignKey(MenuCategory, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=255)   # e.g., "Cheeseburger"
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(upload_to="menu/items/", null=True, blank=True)
    is_available = models.BooleanField(default=True) # remove this

    def __str__(self):
        return self.name

# extras, what about (addon and variant) availability?
class VariantGroup(models.Model):
    item = models.ForeignKey("MenuItem", on_delete=models.CASCADE, related_name="variant_groups")
    name = models.CharField(max_length=100)  # e.g., "Size", "Style"
    is_required = models.BooleanField(default=True)

class VariantOption(models.Model):
    group = models.ForeignKey(VariantGroup, on_delete=models.CASCADE, related_name="options")
    name = models.CharField(max_length=100)  # e.g., "Small", "Large", "Crunchy", "Grilled"
    price_diff = models.DecimalField(max_digits=10, decimal_places=2, default=0)

class MenuItemAddonGroup(models.Model):
    item = models.ForeignKey("MenuItem", on_delete=models.CASCADE, related_name="addon_groups")
    name = models.CharField(max_length=100)  # e.g., "Extras", "Toppings"
    is_required = models.BooleanField(default=False)
    max_selection = models.PositiveIntegerField(default=0)  # 0 = unlimited

    def __str__(self):
        return f"{self.item.name} - {self.name}"

class MenuItemAddon(models.Model):
    group = models.ForeignKey(MenuItemAddonGroup, on_delete=models.CASCADE, related_name="addons")
    name = models.CharField(max_length=100)  # e.g., "Cheese", "Fries"
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.group.name} - {self.name}"

class MenuItemAvailability(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="availabilities")
    item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, related_name="branch_availabilities") # this should be one to one

    is_available = models.BooleanField(default=True)
    override_price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("branch", "item")

    def __str__(self):
        return f"{self.item.name} @ {self.branch.name} - {'Available' if self.is_available else 'Out'}"
    
    def main_price(self): # a way to calculate once with signals # but use a lession to teach me don't write the code for me
        return self.item.price if self.override_price == None else self.override_price

class Customer(models.Model):
    name = models.CharField(max_length= 100)

class Driver(models.Model):
    name = models.CharField(max_length= 100)

# appliing checking and attaching said coupons
class Coupons(models.Model): # are coupons for the entire order or a single order item
    
    TYPE_CHOICES = [
        ("delivery", "Free-delivery"),
        # ("orderoff", "Amount-off-orders"),
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
    
    # quality = models.SmallIntegerField(default= 0) not as useful since we are calculating the coupons effect
    
    # single_item_use = models.BooleanField(default=False) # order level

    def apply_discount(self, price: float, added_price:float, delivery_price:float, quality: int, category: str) -> float:
        # self.coupons. # get the orders check all the orders 
        new_price = price + added_price + delivery_price
        
        match self.discount_type:
            case "FreeDelivery":
                return self.apply_quality(quality, new_price, price + added_price)
            case "DiscountPercent":
                return self.apply_quality(quality, new_price, new_price * (1-(1*self.percent)))
            case "CategoryDiscount":
                if category == self.category:
                    return self.apply_quality(quality, new_price, new_price * (1-(1*self.percent)))
                else:
                    return new_price
            case _:
                return new_price
    
    def apply_quality(self, quality, price, discount_price):
        if self.quality == 0:
            return discount_price * quality
        else:
            return (discount_price * min(quality, self.quality)) + (price * max(quality - self.quality, 0))
    
    # def is_valid_for(self, order:MenuItem):# self is the coupon
    #     """Check if coupon is usable for a given order."""
    #     from django.utils.timezone import now
    #     if not self.is_active:
    #         return False
    #     if self.valid_from > now() or self.valid_until < now():
    #         return False
    #     if self.max_uses and self.uses_count >= self.max_uses:
    #         return False
    #     # if self.min_order_value and order.subtotal < self.min_order_value:
    #     #     return False
    #     if self.scope == "restaurant" and order.branch.restaurant != self.restaurant:
    #         return False
    #     if self.coupon_type == "itemdiscount":
    #         if not self.item or self.item.id == order.:
        
    #     return True

    def apply_discount(self, subtotal):
        if self.discount_type == "percent":
            return subtotal - (subtotal * (self.discount_value / 100))
        return subtotal - self.discount_value


# calculate the distance to get the drivers amount
# create a way to pick from the closest branch

class Order(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("confirmed", "Confirmed"),
        ("preparing", "Preparing"),
        ("ready", "Ready for Pickup"),
        ("on_the_way", "On the Way"),
        ("delivered", "Delivered"), # ("Completed", "completed"),
        ("cancelled", "Cancelled"),
    ]

    orderer = models.ForeignKey(Customer, on_delete= models.CASCADE, related_name="orders")
    branch = models.ForeignKey(Branch, on_delete= models.CASCADE, related_name= "orders")
    
    driver = models.ForeignKey(Driver, on_delete= models.CASCADE, related_name= "orders")
    delivery_price = models.DecimalField(decimal_places= 5, max_digits= 10, default= 0)
    ovena_commision = models.DecimalField(max_digits=5, decimal_places=2, default= 10)
    coupons = models.ForeignKey(Coupons, on_delete= models.CASCADE, related_name= "coupons", blank=True, null= True)

    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)        # sum(line_total)
    discount_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)  # sum(discount_amount)
    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)     # subtotal - discount_total + delivery

    # if it is zero then delivery fee is should show free delivery
    # coupons = models.ForeignKey(Coupons, on_delete= models.CASCADE, related_name= "coupons") # feels wrong
    # we can use a signal to set the coupons used parameter
    # or we can apply it in the view
    
    status = models.CharField(max_length= 30, choices= STATUS_CHOICES, default= "pending")
    created_at = models.DateTimeField(auto_now_add=True)
    last_modified_at = models.DateTimeField(auto_now=True)
    

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

    menu_availability = models.ForeignKey(
        MenuItemAvailability, on_delete=models.SET_NULL,
        related_name="order_items", null=True, blank=True
    )

    def calculate_addon_price(self):
        """Only used once on creation."""
        variant_total = sum(v.price_diff for v in self.variants.all()) # this feels wrong could be improved
        addon_total = sum(a.price for a in self.addons.all())
        return addon_total + variant_total
    
    def save(self, *args, **kwargs): # validate coupons in views
        # Only calculate when creating a new record
        if not self.pk:
            self.price = (
                self.menu_availability.override_price
                if self.menu_availability and self.menu_availability.override_price is not None
                else self.menu_item.price
            )
            self.added_total = self.calculate_addon_price()
            self.line_total = (self.price + self.added_total)* self.quantity
        super().save(*args, **kwargs)

# does coupons apply to the addons
# if multiple coupons then we use for loop then
# coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
# delivery_address = models.ForeignKey("Address", on_delete=models.SET_NULL, null=True, blank=True)
from django.db import models
from accounts.models import (
    Business, Branch, CustomerProfile
)

# for the name and the price where we have the base price and menu system we want ot uae the check for poverrid
#  if no override than we and to get the base or lower level, second same for price the system needs revaming

class BaseItem(models.Model):
    """
    Canonical definition of an item (e.g., Coke, Cheese, Burger Patty). Changed to represent the finish product might be revised
    Not sold directly. Always wrapped as MenuItem or Addon.
    """
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="base_items", null=True, blank=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    default_price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(upload_to="base/items/", null=True, blank=True)

    @property
    def restaurant(self):
        return self.business

    @restaurant.setter
    def restaurant(self, value):
        self.business = value

    def __str__(self):
        return f"{self.business.business_name} - {self.name}"
    
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["business", "name"], name="unique_name_per_business")
        ]

class Menu(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="menus", null=True, blank=True)
    name = models.CharField(max_length=255)  # e.g., "Lunch Menu", "Weekend Specials"
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    @property
    def restaurant(self):
        return self.business

    @restaurant.setter
    def restaurant(self, value):
        self.business = value

    def __str__(self):
        return f"{self.business.business_name} - {self.name}"

class MenuCategory(models.Model):
    menu = models.ForeignKey(Menu, on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(max_length=255)  # e.g., "Burgers", "Drinks", "Desserts"
    sort_order = models.PositiveIntegerField(default=0) # auto add

    class Meta:
        ordering = ["sort_order"]

    def __str__(self):
        return f"{self.menu.name} - {self.name}"

class MenuItemManager(models.Manager):
    def available(self, branch):
        """
        Return only MenuItems whose BaseItems are available in this branch.
        """
        return self.get_queryset().filter(
            base_item__branch_availabilities__branch=branch,
            base_item__branch_availabilities__is_available=True
        )

# description, image removal
class MenuItem(models.Model):
    category = models.ForeignKey(MenuCategory, on_delete=models.CASCADE, related_name="items")
    base_item = models.ForeignKey(BaseItem, on_delete=models.CASCADE, related_name="menu_items")
    custom_name = models.CharField(max_length=255)   # e.g., "Cheeseburger"
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(upload_to="menu/items/", null=True, blank=True)
    favorite = models.ManyToManyField(CustomerProfile) # check

    # objects = MenuItemManager()  # attach the custom manager

    def __str__(self):
        return self.custom_name or self.base_item.name

    @property
    def effective_price(self):
        return self.price if self.price is not None else self.base_item.default_price
    
    @property
    def effective_image(self):
        return self.image if self.image else self.base_item.image

# extras, what about (addon and variant) availability?
class VariantGroup(models.Model):
    item = models.ForeignKey("MenuItem", on_delete=models.CASCADE, related_name="variant_groups")
    name = models.CharField(max_length=100)  # e.g., "Size", "Style"
    is_required = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.item.custom_name} - {self.name}"

class VariantOption(models.Model):
    group = models.ForeignKey(VariantGroup, on_delete=models.CASCADE, related_name="options")
    name = models.CharField(max_length=100)  # e.g., "Small", "Large", "Crunchy", "Grilled"
    price_diff = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    def __str__(self):
        return f"{self.group.item.custom_name} - {self.name}"

class MenuItemAddonGroup(models.Model):
    item = models.ForeignKey("MenuItem", on_delete=models.CASCADE, related_name="addon_groups")
    name = models.CharField(max_length=100)  # e.g., "Extras", "Toppings"
    is_required = models.BooleanField(default=False)
    max_selection = models.PositiveIntegerField(default=0)  # 0 = unlimited

    def __str__(self):
        return f"{self.item.custom_name} - {self.name}"

class MenuItemAddonManager(models.Manager):
    def available(self, branch):
        """
        Return only Addons whose BaseItems are available in this branch.
        """
        return self.get_queryset().filter(
            base_item__branch_availabilities__branch=branch,
            base_item__branch_availabilities__is_available=True
        )

class MenuItemAddon(models.Model):
    groups = models.ManyToManyField("MenuItemAddonGroup", related_name="addons")
    base_item = models.ForeignKey(BaseItem, on_delete=models.CASCADE, related_name="as_addon")
    price = models.DecimalField(max_digits=10, decimal_places=2)

    objects = MenuItemAddonManager()  # attach custom manager

    def __str__(self):
        return self.base_item.name

class BaseItemAvailability(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="item_availabilities")
    base_item = models.ForeignKey(BaseItem, on_delete=models.CASCADE, related_name="branch_availabilities")

    is_available = models.BooleanField(default=True)
    override_price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("branch", "base_item")

    def __str__(self):
        return f"{self.base_item.name} @ {self.branch.name} - {'Available' if self.is_available else 'Out'}"

    #def main_price(self): # a way to calculate once with signals # but use a lession to teach me don't write the code for me
    @property
    def effective_price(self):
        return self.override_price if self.override_price is not None else self.base_item.default_price
# we need a websocket for the availiability

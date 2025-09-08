from django.db import models
from accounts.models import (
    Restaurant, Branch, CustomerProfile
)

class Category(models.Model): # common seached field # template for searching
    name = models.CharField(max_length=255)
    sort_order = models.PositiveIntegerField(default=0) # sort from time to time # auto add on save

    class Meta:
        ordering = ["sort_order"]

    def __str__(self):
        return f"{self.menu.name} - {self.name}"

class BaseItem(models.Model):
    """
    Canonical definition of an item (e.g., Coke, Cheese, Burger Patty).
    Not sold directly. Always wrapped as MenuItem or Addon.
    """
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    default_price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(upload_to="base/items/", null=True, blank=True)

    def __str__(self):
        return self.name

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

class MenuItem(models.Model):
    category = models.ForeignKey(MenuCategory, on_delete=models.CASCADE, related_name="items")
    base_item = models.ForeignKey(BaseItem, on_delete=models.CASCADE, related_name="menu_items")
    custom_name = models.CharField(max_length=255)   # e.g., "Cheeseburger"
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(upload_to="menu/items/", null=True, blank=True)
    favorite = models.ManyToManyField(CustomerProfile, blank=True, null=True) # check

    # objects = MenuItemManager()  # attach the custom manager

    def __str__(self):
        return self.custom_name or self.base_item.name

    @property
    def effective_price(self):
        return self.base_price if self.base_price is not None else self.base_item.default_price

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

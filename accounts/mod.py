from .models import *

class DeliveryAddress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    address = models.CharField(max_length=255)  # "2 Computer Village, Ikeja, Lagos, Nigeria"
    location = models.PointField()              # (lng, lat)
    created_at = models.DateTimeField(auto_now_add=True)


class Restaurant(models.Model):
    name = models.CharField(max_length=255)
    latitude = models.FloatField()
    longitude = models.FloatField()



class Menu(models.Model):
    restaurant = models.ForeignKey("RestaurantProfile", on_delete=models.CASCADE, related_name="menus")
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
    is_available = models.BooleanField(default=True)

    def __str__(self):
        return self.name


# extras
class MenuItemVariant(models.Model):
    item = models.ForeignKey("MenuItem", on_delete=models.CASCADE, related_name="variants")
    name = models.CharField(max_length=100)  # e.g., "Small", "Large", "Bottle"
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.item.name} - {self.name}"


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

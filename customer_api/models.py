from django.db import models
from accounts.models import CustomerProfile, Branch
from menu.models import MenuItem

# Create your models here.
class FavoriteMenuItem(models.Model):
    customer = models.ForeignKey(
        CustomerProfile,
        on_delete=models.CASCADE,
        related_name="favorites"
    )

    menu_item = models.ForeignKey(
        MenuItem,
        on_delete=models.CASCADE,
        related_name="favorites"
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.CASCADE,
        related_name="favorites"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "menu_item", "branch"],
                name="unique_customer_menuitem_branch_favorite"
            )
        ]

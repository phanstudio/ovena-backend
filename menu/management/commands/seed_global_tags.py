
# ============================================================
# 4. management/commands/seed_global_tags.py — starter tag list
# ============================================================
"""
Run with: python manage.py seed_global_tags
Idempotent — safe to re-run, get_or_create skips anything that exists.
Includes Nigerian/local dishes alongside the generic set since that's
the primary market; trim/extend to fit your actual business mix.
"""

SEED_TAGS = [
    # Food type
    "Burgers", "Pizza", "Sushi", "Sandwiches", "Salads", "Pasta", "Tacos",
    "Noodles", "Soups", "Seafood", "Steak", "BBQ", "Fried Chicken", "Wings",
    "Ribs", "Kebabs", "Shawarma", "Burritos", "Wraps", "Breakfast", "Brunch",
    "Desserts", "Ice Cream", "Bakery", "Pastries", "Cakes",
    # Drinks
    "Coffee", "Tea", "Smoothies", "Juices", "Cocktails", "Beer", "Wine", "Drinks",
    # Cuisine
    "Italian", "Chinese", "Japanese", "Indian", "Mexican", "Thai", "Korean",
    "Vietnamese", "Lebanese", "Turkish", "Nigerian", "Continental", "American",
    "French", "Mediterranean", "Ethiopian", "Caribbean", "Fusion",
    # Local / Nigerian dishes
    "Jollof Rice", "Suya", "Amala", "Efo Riro", "Pepper Soup", "Small Chops",
    "Fried Rice", "Pounded Yam", "Egusi", "Asun", "Moin Moin",
    # Dietary
    "Vegan", "Vegetarian", "Gluten-Free", "Halal", "Keto", "Low-Carb",
    "Organic", "Dairy-Free",
    # Service / meal style
    "Fast Food", "Fine Dining", "Casual Dining", "Buffet", "Grill",
    "Street Food", "Kids Menu", "Combo Meals", "Family Meals",
    "Party Packs", "Catering",
]

# --- management/commands/seed_global_tags.py ---
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Seed GlobalTag with a common starter set. Safe to re-run."

    def handle(self, *args, **options):
        from menu.models.categories import GlobalTag  # adjust import path to your app

        created_count = 0
        for name in SEED_TAGS:
            _, created = GlobalTag.objects.get_or_create(
                name__iexact=name,
                defaults={"name": name},
            )
            created_count += int(created)

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {created_count} new tags ({len(SEED_TAGS) - created_count} already existed)."
        ))

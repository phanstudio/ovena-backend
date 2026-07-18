# serializers.py
from rest_framework import serializers
from ..models import (
    Business, Branch, Menu, MenuCategory, MenuItem,
    BaseItem, BaseItemAvailability,
    VariantGroup, VariantOption,
    MenuItemAddonGroup, MenuItemAddon
)
from accounts.models import BusinessSubscription
from menu.utils.helper import is_branch_hours_open, get_hours, is_branch_open


# ============================================================================
# ATOMIC SERIALIZERS (bottom of the tree, no nesting)
# ============================================================================

class VariantOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = VariantOption
        fields = ["id", "name", "price_diff"]


class VariantGroupSerializer(serializers.ModelSerializer):
    options = VariantOptionSerializer(many=True, read_only=True)

    class Meta:
        model = VariantGroup
        fields = ["id", "name", "is_required", "options"]


class MenuItemAddonSerializer(serializers.ModelSerializer):
    """
    Addon name comes from base_item (FK).
    Must be used with prefetch_related('addons__base_item').
    Uses addon-level price, NOT base_item.default_price.
    Branch override price is handled at MenuItem level via BaseItemAvailability.
    """
    name = serializers.CharField(source='base_item.name', read_only=True)
    image = serializers.URLField(source='base_item.image', read_only=True)

    class Meta:
        model = MenuItemAddon
        fields = ["id", "name", "price", "image"]


class MenuItemAddonGroupSerializer(serializers.ModelSerializer):
    """
    addons reverse relation works because MenuItemAddon.groups is M2M
    with related_name="addons" — Django creates the reverse manager.
    Must prefetch: addon_groups__addons__base_item
    """
    addons = MenuItemAddonSerializer(many=True, read_only=True)

    class Meta:
        model = MenuItemAddonGroup
        fields = ["id", "name", "is_required", "max_selection", "addons"]


# ============================================================================
# MENU ITEM SERIALIZERS
# ============================================================================

class MenuItemDetailSerializer(serializers.ModelSerializer):
    """
    Full item for business detail page.
    Uses effective_price and effective_image (your model properties).
    Branch-level price override requires passing branch in context.
    """
    # Use model properties, not raw fields
    price = serializers.DecimalField(
        source='effective_price', max_digits=10, decimal_places=2, read_only=True
    )
    image = serializers.URLField(
        source='effective_image', read_only=True
    )
    variant_groups = VariantGroupSerializer(many=True, read_only=True)
    addon_groups = MenuItemAddonGroupSerializer(many=True, read_only=True)

    # Branch-aware price override
    branch_price = serializers.SerializerMethodField()
    is_available = serializers.SerializerMethodField()

    class Meta:
        model = MenuItem
        fields = [
            "id", "custom_name", "description",
            "price",          # effective_price (menu-level)
            "branch_price",   # override price for this branch (or null)
            "is_available",   # available at this branch?
            "image",          # effective_image
            "variant_groups",
            "addon_groups",
        ]

    def _get_availability(self, obj):
        """
        Looks up BaseItemAvailability for (branch, base_item).
        Requires context['availability_map'] = {base_item_id: BaseItemAvailability}
        Built once in the view, not per-item.
        """
        availability_map = self.context.get("availability_map", {})
        return availability_map.get(obj.base_item_id)

    def get_branch_price(self, obj):
        avail = self._get_availability(obj)
        if avail and avail.override_price is not None:
            return avail.override_price
        return None  # means use menu-level price

    def get_is_available(self, obj):
        avail = self._get_availability(obj)
        if avail is None:
            return True  # no record = assume available
        return avail.is_available


class MenuItemSimpleSerializer(serializers.ModelSerializer):
    """
    Name + price only. For list views / menu name views.
    No variants, no addons.
    """
    price = serializers.DecimalField(
        source='effective_price', max_digits=10, decimal_places=2, read_only=True
    )

    class Meta:
        model = MenuItem
        fields = ["id", "custom_name", "price", "image"]


class MenuItemFeaturedSerializer(serializers.ModelSerializer):
    """
    Featured items with variants + addons.
    Same as detail but filtered to is_featured=True at queryset level in view.
    """
    price = serializers.DecimalField(
        source='effective_price', max_digits=10, decimal_places=2, read_only=True
    )
    image = serializers.URLField(source='effective_image', read_only=True)
    variant_groups = VariantGroupSerializer(many=True, read_only=True)
    addon_groups = MenuItemAddonGroupSerializer(many=True, read_only=True)

    class Meta:
        model = MenuItem
        fields = [
            "id", "custom_name", "description",
            "price", "image", "variant_groups", "addon_groups"
        ]


# ============================================================================
# MENU / CATEGORY SERIALIZERS
# ============================================================================

class MenuCategoryDetailSerializer(serializers.ModelSerializer):
    items = MenuItemDetailSerializer(many=True, read_only=True)

    class Meta:
        model = MenuCategory
        fields = ["id", "name", "sort_order", "items"]


class MenuDetailSerializer(serializers.ModelSerializer):
    categories = MenuCategoryDetailSerializer(many=True, read_only=True)

    class Meta:
        model = Menu
        fields = ["id", "name", "description", "is_active", "categories"]


class MenuSimpleSerializer(serializers.ModelSerializer):
    """
    Menu with flat list of item names only. No nesting beyond items.
    Requires prefetch: menus__categories__items
    """
    items = serializers.SerializerMethodField()

    class Meta:
        model = Menu
        fields = ["id", "name", "items"]

    def get_items(self, obj):
        # Flat list across all categories
        # Uses prefetched data - no extra queries
        result = []
        for category in obj.categories.all():
            for item in category.items.all():
                result.append({
                    "id": item.id,
                    "name": item.custom_name,
                    "price": float(item.effective_price),
                })
        return result


# ============================================================================
# BRANCH SERIALIZER (inline, for list views)
# ============================================================================

class NearestBranchSerializer(serializers.Serializer):
    """
    Not a ModelSerializer — built from annotated fields on Business
    plus the bulk-loaded branch object.
    """
    id = serializers.IntegerField()
    name = serializers.CharField()
    distance_km = serializers.FloatField()


class BaseWithAddressMixin():
    def get_lat(self, obj):
        return obj.location.y if obj.location else None  # y = latitude

    def get_long(self, obj):
        return obj.location.x if obj.location else None  # x = longitude


class BaseWithNearestSerializer(serializers.ModelSerializer, BaseWithAddressMixin):
    nearest_branch = serializers.SerializerMethodField()
    
    def get_nearest_branch(self, obj):
        branches_by_id = self.context.get("branches_by_id", {})
        branch: Branch = branches_by_id.get(obj.nearest_branch_id)
        if not branch:
            return None
        return {
            "id": branch.id,
            "name": branch.name,
            "distance_km": round(obj.nearest_branch_distance.km, 2),
            "lat": self.get_lat(branch),
            "long": self.get_long(branch),
            "address": branch.address,
            "is_open": is_branch_open(branch),   # ← add this
        }



# ============================================================================
# BUSINESS SERIALIZERS
# ============================================================================

class BusinessListSerializer(BaseWithNearestSerializer):
    """
    Ultra-lightweight. Infinite scroll homepage list.
    2 queries total for 20 businesses.
    """

    class Meta:
        model = Business
        fields = [
            "id", "business_name", "business_type",
            "business_logo", "avg_rating", "rating_count",
            "nearest_branch", "business_image"
        ]


class BusinessBannerSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessSubscription
        fields = ["id", "banner_info"]


class BusinessCarouselSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessSubscription
        fields = [
            "id", "carousel_image"
        ]


class BusinessWithMenuNamesSerializer(BaseWithNearestSerializer):
    """
    Business + flat item names per menu. NO variants/addons.
    Requires prefetch: menus__categories__items
    """
    menus = MenuSimpleSerializer(many=True, read_only=True)

    class Meta:
        model = Business
        fields = [
            "id", "business_name", "business_type",
            "business_logo", "avg_rating", "rating_count",
            "nearest_branch", "menus",
        ]


class BusinessFeaturedSerializer(BaseWithNearestSerializer):
    """
    Business with featured items.
    is_featured filtered at QUERYSET level in the view (not in Python).
    Requires prefetch with filtered queryset for items.
    """
    # featured_items = serializers.SerializerMethodField()

    class Meta:
        model = Business
        fields = [
            "id", "business_name", "business_type",
            "business_logo", "avg_rating", "rating_count",
            "nearest_branch", #"featured_items",
        ]

    # def get_featured_items(self, obj):
    #     result = []
    #     for menu in obj.menus.all():
    #         for category in menu.categories.all():
    #             for item in category.items.all():
    #                 # No is_featured check — just take first items found
    #                 result.append(MenuItemFeaturedSerializer(item, context=self.context).data)
    #                 if len(result) >= 3:
    #                     return result
    #     return result


class BusinessDetailSerializer(serializers.ModelSerializer, BaseWithAddressMixin):
    """
    Full detail page serializer. Branch-aware pricing and availability.
    Requires context['availability_map'] built in view.
    Passes context down so MenuItemDetailSerializer can use it.
    """
    menus = serializers.SerializerMethodField()
    nearest_branch = serializers.SerializerMethodField()

    class Meta:
        model = Business
        fields = [
            "id", "business_name", "business_type",
            "business_logo", "business_image", #"banner_image",
            "avg_rating", "rating_count",
            "nearest_branch", "menus", #"description",
        ]

    def get_menus(self, obj):
        return MenuDetailSerializer(
            obj.menus.all(),
            many=True,
            context=self.context  # passes availability_map down
        ).data

    def get_nearest_branch(self, obj):
        branch:Branch = self.context.get("branch")
        if not branch:
            return None
        distance = self.context.get("distance")
        hours = get_hours(branch)
        return {
            "id": branch.id,
            "name": branch.name,
            "distance_km": round(distance.km, 2) if distance else None,
            "lat": self.get_lat(branch),
            "long": self.get_long(branch),
            "address": branch.address,
            "average_prep_time": branch.average_prep_time,
            "is_open": is_branch_hours_open(hours),   # ← add this
            "open_time": getattr(hours, "open_time", None),
            "close_time": getattr(hours, "close_time", None),
            "delivery_method": branch.delivery_method,
        }

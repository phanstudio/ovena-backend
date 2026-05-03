from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from django.db.models import Q
from accounts.models import BusinessAdmin
from django.shortcuts import get_object_or_404
from menu.models import (
    Menu, MenuCategory, MenuItem, VariantGroup, VariantOption,
    MenuItemAddonGroup, MenuItemAddon, BaseItem, BaseItemAvailability,
)
from authflow.permissions import IsBusinessAdmin
from authflow.authentication import CustomBAdminAuth
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers as s
import menu.serializers.input_ser.delete as delete_selerizers


def get_user_business(buisness_admin: BusinessAdmin):
    if not buisness_admin.business:
        raise ValueError("no_business")
    return buisness_admin.business


def _cleanup_orphaned_base_items(business, base_item_ids: list):
    """
    For each base_item_id in the list, check if it is still referenced by
    any MenuItem or MenuItemAddon within this business. If not, delete its
    BaseItemAvailability rows, then delete the BaseItem itself.

    Returns a list of base_item IDs that were fully deleted.
    """
    deleted_base_ids = []

    for bid in base_item_ids:
        still_referenced = (
            MenuItem.objects.filter(base_item_id=bid, category__menu__business=business).exists()
            or
            MenuItemAddon.objects.filter(base_item_id=bid,
                                         groups__item__category__menu__business=business).exists()
        )
        if not still_referenced:
            BaseItemAvailability.objects.filter(base_item_id=bid).delete()
            BaseItem.objects.filter(id=bid, business=business).delete()
            deleted_base_ids.append(bid)

    return deleted_base_ids


class BaseBuisAdminAPIView(GenericAPIView):
    authentication_classes = [CustomBAdminAuth]
    permission_classes = [IsBusinessAdmin]

    def get_buisnessadmn(self, request) -> BusinessAdmin:
        try:
            return request.user.business_admin
        except BusinessAdmin.DoesNotExist:
            return get_object_or_404(BusinessAdmin, user=request.user)

# ─────────────────────────────────────────────────────────────────────────────
# DELETE: Single Addon
# DELETE /menu/addon/<addon_id>/
# ─────────────────────────────────────────────────────────────────────────────


class DeleteAddonView(BaseBuisAdminAPIView):
    """
    Deletes a MenuItemAddon.
    After deletion, if the addon's BaseItem has no remaining references
    (no MenuItem or MenuItemAddon in this business), the BaseItem and its
    availability rows are also deleted.
    """
    
    @extend_schema(responses={200: delete_selerizers.DeleteAddonResponseSerializer})
    def delete(self, request, addon_id):
        try:
            buisness_admin = self.get_buisnessadmn(request)
            business = get_user_business(buisness_admin)
        except ValueError as e:
            return Response({"detail": str(e)}, status=403)

        try:
            addon = MenuItemAddon.objects.select_related("base_item").get(
                id=addon_id,
                groups__item__category__menu__business=business,
            )
        except MenuItemAddon.DoesNotExist:
            return Response({"detail": "Addon not found."}, status=404)

        base_item_id = addon.base_item_id

        with transaction.atomic():
            addon.delete()
            deleted_base_ids = _cleanup_orphaned_base_items(business, [base_item_id])

        return Response({
            "message": "Addon deleted.",
            "addon_id": str(addon_id),
            "base_item_deleted": base_item_id in deleted_base_ids,
        }, status=200)


# ─────────────────────────────────────────────────────────────────────────────
# DELETE: Single MenuItem
# DELETE /menu/item/<item_id>/
# ─────────────────────────────────────────────────────────────────────────────

class DeleteMenuItemView(BaseBuisAdminAPIView):
    """
    Deletes a MenuItem along with all its child VariantGroups, VariantOptions,
    AddonGroups, and Addons (cascade).
    After deletion, checks if any referenced BaseItems are now orphaned and
    cleans them up (BaseItemAvailability + BaseItem).
    """

    @extend_schema(responses={200: delete_selerizers.DeleteMenuItemResponseSerializer})
    def delete(self, request, item_id):
        try:
            buisness_admin = self.get_buisnessadmn(request)
            business = get_user_business(buisness_admin)
        except ValueError as e:
            return Response({"detail": str(e)}, status=403)

        try:
            item = MenuItem.objects.select_related("base_item").get(
                id=item_id,
                category__menu__business=business,
            )
        except MenuItem.DoesNotExist:
            return Response({"detail": "Menu item not found."}, status=404)

        # Collect all base_item IDs referenced by this item and its addons
        # before deletion so we can check orphans afterwards
        base_item_ids = {item.base_item_id}
        addon_base_ids = list(
            MenuItemAddon.objects.filter(groups__item=item)
            .values_list("base_item_id", flat=True)
            .distinct()
        )
        base_item_ids.update(addon_base_ids)

        with transaction.atomic():
            item.delete()  # cascades to VariantGroups, AddonGroups, Addons via FK on_delete
            deleted_base_ids = _cleanup_orphaned_base_items(business, list(base_item_ids))

        return Response({
            "message": "Menu item deleted.",
            "item_id": str(item_id),
            "base_items_deleted": [str(bid) for bid in deleted_base_ids],
        }, status=200)


# ─────────────────────────────────────────────────────────────────────────────
# DELETE: MenuCategory
# DELETE /menu/category/<category_id>/
# ─────────────────────────────────────────────────────────────────────────────

class DeleteMenuCategoryView(BaseBuisAdminAPIView):
    """
    Deletes a MenuCategory and all its descendant MenuItems (cascade).
    Cleans up orphaned BaseItems afterwards.
    """
    

    @extend_schema(responses={200: delete_selerizers.DeleteCategoryResponseSerializer})
    def delete(self, request, category_id):
        try:
            buisness_admin = self.get_buisnessadmn(request)
            business = get_user_business(buisness_admin)
        except ValueError as e:
            return Response({"detail": str(e)}, status=403)

        try:
            category = MenuCategory.objects.get(
                id=category_id,
                menu__business=business,
            )
        except MenuCategory.DoesNotExist:
            return Response({"detail": "Category not found."}, status=404)

        # Collect all base_item IDs referenced by items + addons in this category
        item_qs = MenuItem.objects.filter(category=category)
        item_count = item_qs.count()

        base_item_ids = set(item_qs.values_list("base_item_id", flat=True))
        addon_base_ids = list(
            MenuItemAddon.objects.filter(groups__item__category=category)
            .values_list("base_item_id", flat=True)
            .distinct()
        )
        base_item_ids.update(addon_base_ids)

        with transaction.atomic():
            category.delete()  # cascades to MenuItems -> variants/addons
            deleted_base_ids = _cleanup_orphaned_base_items(business, list(base_item_ids))

        return Response({
            "message": "Category deleted.",
            "category_id": str(category_id),
            "items_deleted": item_count,
            "base_items_deleted": [str(bid) for bid in deleted_base_ids],
        }, status=200)


# ─────────────────────────────────────────────────────────────────────────────
# DELETE: Entire Menu
# DELETE /menu/<menu_id>/
# ─────────────────────────────────────────────────────────────────────────────

class DeleteMenuView(BaseBuisAdminAPIView):
    """
    Deletes an entire Menu and all its descendant Categories, Items,
    Variants, AddonGroups, and Addons (cascade).
    Cleans up orphaned BaseItems afterwards.
    """
    

    @extend_schema(responses={200: delete_selerizers.DeleteMenuResponseSerializer})
    def delete(self, request, menu_id):
        try:
            buisness_admin = self.get_buisnessadmn(request)
            business = get_user_business(buisness_admin)
        except ValueError as e:
            return Response({"detail": str(e)}, status=403)

        try:
            menu = Menu.objects.get(id=menu_id, business=business)
        except Menu.DoesNotExist:
            return Response({"detail": "Menu not found."}, status=404)

        # Count descendants before deletion for informative response
        category_count = MenuCategory.objects.filter(menu=menu).count()
        item_qs = MenuItem.objects.filter(category__menu=menu)
        item_count = item_qs.count()

        # Collect all base_item IDs referenced in this menu
        base_item_ids = set(item_qs.values_list("base_item_id", flat=True))
        addon_base_ids = list(
            MenuItemAddon.objects.filter(groups__item__category__menu=menu)
            .values_list("base_item_id", flat=True)
            .distinct()
        )
        base_item_ids.update(addon_base_ids)

        with transaction.atomic():
            menu.delete()  # cascades to Category -> Item -> Variant/Addon
            deleted_base_ids = _cleanup_orphaned_base_items(business, list(base_item_ids))

        return Response({
            "message": "Menu deleted.",
            "menu_id": str(menu_id),
            "categories_deleted": category_count,
            "items_deleted": item_count,
            "base_items_deleted": [str(bid) for bid in deleted_base_ids],
        }, status=200)


# ─────────────────────────────────────────────────────────────────────────────
# DELETE: Bulk — delete multiple entities in one request
# POST /menu/bulk-delete/
# Body: { "menus": [...ids], "categories": [...ids], "items": [...ids], "addons": [...ids] }
# ─────────────────────────────────────────────────────────────────────────────

class BulkDeleteMenuView(BaseBuisAdminAPIView):
    """
    Bulk-delete any combination of Menus, MenuCategories, MenuItems, and MenuItemAddons
    in a single atomic transaction. After all deletions, orphaned BaseItems are
    cleaned up once (efficient: avoids redundant checks per entity).

    Request body:
        {
            "menus":      ["<menu_id>", ...],
            "categories": ["<category_id>", ...],
            "items":      ["<item_id>", ...],
            "addons":     ["<addon_id>", ...]
        }
    All fields are optional; omit or pass [] to skip that type.
    """
    serializer_class = delete_selerizers.BulkDeleteRequestSerializer

    @extend_schema(responses={200: delete_selerizers.BulkDeleteResponseSerializer})
    def post(self, request):
        try:
            buisness_admin = self.get_buisnessadmn(request)
            business = get_user_business(buisness_admin)
        except ValueError as e:
            return Response({"detail": str(e)}, status=403)
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        menu_ids     = data["menus"]
        category_ids = data["categories"]
        item_ids     = data["items"]
        addon_ids    = data["addons"]

        # ── Collect all affected base_item IDs before any deletion ────────────
        affected_base_ids = set()

        if menu_ids:
            affected_base_ids.update(
                MenuItem.objects.filter(category__menu__id__in=menu_ids,
                                        category__menu__business=business)
                .values_list("base_item_id", flat=True)
            )
            affected_base_ids.update(
                MenuItemAddon.objects.filter(groups__item__category__menu__id__in=menu_ids,
                                             groups__item__category__menu__business=business)
                .values_list("base_item_id", flat=True)
            )

        if category_ids:
            affected_base_ids.update(
                MenuItem.objects.filter(category__id__in=category_ids,
                                        category__menu__business=business)
                .values_list("base_item_id", flat=True)
            )
            affected_base_ids.update(
                MenuItemAddon.objects.filter(groups__item__category__id__in=category_ids,
                                             groups__item__category__menu__business=business)
                .values_list("base_item_id", flat=True)
            )

        if item_ids:
            affected_base_ids.update(
                MenuItem.objects.filter(id__in=item_ids,
                                        category__menu__business=business)
                .values_list("base_item_id", flat=True)
            )
            affected_base_ids.update(
                MenuItemAddon.objects.filter(groups__item__id__in=item_ids,
                                             groups__item__category__menu__business=business)
                .values_list("base_item_id", flat=True)
            )

        if addon_ids:
            affected_base_ids.update(
                MenuItemAddon.objects.filter(id__in=addon_ids,
                                             groups__item__category__menu__business=business)
                .values_list("base_item_id", flat=True)
            )

        counts = {"menus": 0, "categories": 0, "items": 0, "addons": 0}

        with transaction.atomic():
            # Order matters: delete from top of tree downwards so FK cascades
            # don't cause double-count surprises. Django cascade handles children,
            # but we delete parents explicitly to count them.

            if menu_ids:
                qs = Menu.objects.filter(id__in=menu_ids, business=business)
                counts["menus"] = qs.count()
                qs.delete()

            if category_ids:
                qs = MenuCategory.objects.filter(id__in=category_ids, menu__business=business)
                counts["categories"] = qs.count()
                qs.delete()

            if item_ids:
                qs = MenuItem.objects.filter(id__in=item_ids, category__menu__business=business)
                counts["items"] = qs.count()
                qs.delete()

            if addon_ids:
                qs = MenuItemAddon.objects.filter(
                    id__in=addon_ids,
                    groups__item__category__menu__business=business,
                )
                counts["addons"] = qs.count()
                qs.delete()

            # ── Cleanup orphaned BaseItems once ───────────────────────────────
            deleted_base_ids = _cleanup_orphaned_base_items(business, list(affected_base_ids))

        return Response({
            "message": "Bulk delete completed.",
            "deleted": counts,
            "base_items_deleted": [str(bid) for bid in deleted_base_ids],
        }, status=200)

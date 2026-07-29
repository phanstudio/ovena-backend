from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from django.db import transaction
from django.db.models import Q
from accounts.models import BusinessAdmin
from django.shortcuts import get_object_or_404
from menu.models import (
    Menu, MenuCategory, MenuItem, VariantGroup, VariantOption,
    MenuItemAddon, BaseItem
)
from authflow.permissions import IsBusinessAdmin
from authflow.authentication import CustomBAdminAuth
from drf_spectacular.utils import extend_schema
import menu.serializers.input_ser.delete as delete_selerizers
from django.db.models import Count
from image.services import BulkS3StorageService


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
    if not base_item_ids:
        return []

    # 1. Find all base_item_ids in the input list that ARE still being used
    referenced_in_menu = set(
        MenuItem.objects.filter(
            base_item_id__in=base_item_ids, 
            category__menu__business=business
        ).values_list("base_item_id", flat=True)
    )

    referenced_in_addons = set(
        MenuItemAddon.objects.filter(
            base_item_id__in=base_item_ids,
            groups__item__category__menu__business=business
        ).values_list("base_item_id", flat=True)
    )

    # Combine them to get a master set of active IDs
    still_referenced_ids = referenced_in_menu.union(referenced_in_addons)

    # 2. Determine which ones are truly orphaned
    deleted_base_ids = [bid for bid in base_item_ids if bid not in still_referenced_ids]

    # 3. Perform bulk cleanup if there are any orphans
    if deleted_base_ids:
        # Fetch target BaseItems belonging to this business to clean up S3
        qs = BaseItem.objects.filter(id__in=deleted_base_ids, business=business)
        
        # Extract images and trigger batch S3 deletion
        image_urls = list(qs.exclude(image="").values_list("image", flat=True))
        if image_urls:
            BulkS3StorageService.batch_delete_urls(image_urls)

        # Delete from DB (ON DELETE CASCADE handles BaseItemAvailability automatically)
        qs.delete()

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
        varity_ids   = data["varity"]

        # ── 1. Build dynamic Q filters for MenuItems ──────────────────────────
        item_filters = Q()
        if menu_ids:
            item_filters |= Q(category__menu__id__in=menu_ids)
        if category_ids:
            item_filters |= Q(category__id__in=category_ids)
        if item_ids:
            item_filters |= Q(id__in=item_ids)

        # ── 2. Build dynamic Q filters for MenuItemAddons ─────────────────────
        addon_filters = Q()
        if menu_ids:
            addon_filters |= Q(groups__item__category__menu__id__in=menu_ids)
        if category_ids:
            addon_filters |= Q(groups__item__category__id__in=category_ids)
        if item_ids:
            addon_filters |= Q(groups__item__id__in=item_ids)
        if addon_ids:
            addon_filters |= Q(id__in=addon_ids)

        # ── 3. Execute 2 targeted queries ─────────────────────────────────────
        affected_base_ids = set()

        if item_filters:
            affected_base_ids.update(
                MenuItem.objects.filter(
                    item_filters,
                    category__menu__business=business,
                    base_item_id__isnull=False,
                ).values_list("base_item_id", flat=True)
            )

        if addon_filters:
            affected_base_ids.update(
                MenuItemAddon.objects.filter(
                    addon_filters,
                    groups__item__category__menu__business=business,
                    base_item_id__isnull=False,
                ).values_list("base_item_id", flat=True)
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
                BulkS3StorageService.batch_delete_urls(list(qs.values_list("image", flat=True)))
                qs.delete()

            if addon_ids:
                qs = MenuItemAddon.objects.filter(
                    id__in=addon_ids,
                    groups__item__category__menu__business=business,
                )
                counts["addons"] = qs.count()
                qs.delete()
                # add delete if the addons are empty

            if varity_ids:
                qs = VariantOption.objects.filter(
                    id__in=varity_ids,
                    group__item__category__menu__business=business
                )

                counts["varity"] = qs.count()

                # collect affected groups BEFORE delete
                affected_group_ids = list(
                    VariantGroup.objects.filter(
                        options__in=qs
                    ).values_list("id", flat=True).distinct()
                )

                # delete variants
                qs.delete()

                # delete groups that now have no variants
                VariantGroup.objects.filter(
                    id__in=affected_group_ids
                ).annotate(
                    variant_count=Count("options")
                ).filter(
                    variant_count=0
                ).delete()

            # ── Cleanup orphaned BaseItems once ───────────────────────────────
            deleted_base_ids = _cleanup_orphaned_base_items(business, list(affected_base_ids))

        return Response({
            "message": "Bulk delete completed.",
            "deleted": counts,
            "base_items_deleted": [str(bid) for bid in deleted_base_ids],
        }, status=200)


class BulkDeleteMenuImagesView(BaseBuisAdminAPIView):
    """
    Bulk-delete any combination of Menus, MenuCategories, MenuItems, and MenuItemAddons
    in a single atomic transaction. After all deletions, orphaned BaseItems are
    cleaned up once (efficient: avoids redundant checks per entity).

    Request body:
        {
            "items":      ["<item_id>", ...],
            "addons":     ["<addon_id>", ...]
        }
    All fields are optional; omit or pass [] to skip that type.
    Delete shared image
    """
    serializer_class = delete_selerizers.BulkDeleteImageRequestSerializer

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

        item_ids     = data["items"]
        addon_ids    = data["addons"]

        # ── 2. Build dynamic Q filters for MenuItemAddons ─────────────────────
        addon_filters = Q()
        if addon_ids:
            addon_filters |= Q(id__in=addon_ids)

        # ── 3. Execute 2 targeted queries ─────────────────────────────────────
        affected_base_ids = set()

        if addon_filters:
            affected_base_ids.update(
                MenuItemAddon.objects.filter(
                    addon_filters,
                    groups__item__category__menu__business=business,
                    base_item_id__isnull=False,
                ).values_list("base_item_id", flat=True)
            )

        counts = {"items": 0, "addons": 0}
        images_url = set()

        with transaction.atomic():

            if item_ids:
                qs = MenuItem.objects.filter(id__in=item_ids, category__menu__business=business)
                counts["items"] = qs.count()
                images_url.update(
                    qs.exclude(image__isnull=True)
                          .exclude(image="")
                          .values_list("image", flat=True)
                )
                qs.update(image=None)
                

            if addon_ids:
                qs = BaseItem.objects.filter(
                    id__in=affected_base_ids,
                    as_addon__groups__item__category__menu__business=business,
                )
                counts["addons"] = qs.count()
                image_urls.update(
                    qs.exclude(image__isnull=True)
                        .exclude(image="")
                        .values_list("image", flat=True)
                )
                qs.update(image=None)

            transaction.on_commit(
                lambda: BulkS3StorageService.batch_delete_urls(list(images_url))
            )

        return Response({
            "message": "Bulk Image delete completed.",
            "Images deleted": counts,
        }, status=200)

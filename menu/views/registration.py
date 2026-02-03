from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from ..serializers import input_serializers as InS
from ..models import (
    Menu, MenuCategory, MenuItem, VariantGroup, VariantOption, 
    MenuItemAddonGroup, MenuItemAddon, BaseItem, BaseItemAvailability, 
)
from authflow.decorators import subuser_authentication
from authflow.permissions import ScopePermission
from django.db import transaction

from ..websocket_utils import *
from ..tasks import *
from .main import get_branch_staff


# edit permissions later
# first in order split the json into section all the branches and all the categories and etc one by one 
# bulk create each that way the is faster than a for loop-> 
@subuser_authentication
class RegisterMenusView(APIView):
    """
    Registers restaurant-level menu structure (Menu -> Categories -> Items -> Variants/Addons)
    AND bootstraps branch catalog via BaseItemAvailability for all BaseItems referenced.

    Key rules enforced:
    - BaseItem lookup/creation is scoped to (restaurant, name)
    - Availability rows are created for (branch, base_item) for anything referenced in payload
    """
    permission_classes=[ScopePermission]
    required_scopes = ["item:upload"]
    def post(self, request):
        user = request.user
        branch, error = get_branch_staff(user)
        if error:
            return error

        restaurant = branch.restaurant  # restaurant that owns the catalog

        menus_data = request.data.get("menus", [])

        # ✅ Validate everything once
        menus_serializer = InS.MenuSerializer(data=menus_data, many=True)
        menus_serializer.is_valid(raise_exception=True)
        menus_vd = menus_serializer.validated_data

        # Helper: collect all referenced BaseItem "names" from items + addons
        all_base_names = set()

        def collect_base_item_name(bi_dict):
            # BaseItemSerializer: {"name","description","price","image"}
            nm = (bi_dict.get("name") or "").strip()
            if nm:
                all_base_names.add(nm)

        for m in menus_vd:
            for c in m["categories"]:
                for it in c["items"]:
                    collect_base_item_name(it["base_item"])
                    for ag in it.get("addon_groups", []):
                        for addon in ag.get("addons", []):
                            collect_base_item_name(addon["base_item"])
        
        # cprint(all_base_names)

        if not all_base_names:
            return Response(
                {"detail": "No base items found in payload."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        created_menu_ids = []

        # Build "first seen" defaults for missing BaseItems
        defaults_by_name = {}

        def remember_defaults(bi):
            nm = (bi.get("name") or "").strip()
            if not nm:
                return
            # first seen wins
            defaults_by_name.setdefault(
                nm,
                {
                    "description": bi.get("description", "") or "",
                    "default_price": bi["price"],
                    "image": bi.get("image") or None,
                },
            )
        
        for m in menus_vd:
            for c in m["categories"]:
                for it in c["items"]:
                    remember_defaults(it["base_item"])
                    for ag in it.get("addon_groups", []):
                        for addon in ag.get("addons", []):
                            remember_defaults(addon["base_item"])
        
        # cprint(defaults_by_name)

        with transaction.atomic():
            # =========================================================
            # 1) BASE ITEMS (restaurant-scoped): fetch existing, bulk_create missing
            # =========================================================
            existing_qs = BaseItem.objects.filter(
                restaurant=restaurant,
                name__in=all_base_names,
            ).only("id", "name")

            base_by_name = {b.name: b for b in existing_qs}
            missing_names = all_base_names - set(base_by_name.keys())

            if missing_names:
                new_base_items = [
                    BaseItem(
                        restaurant=restaurant,
                        name=name,
                        description=defaults_by_name[name]["description"],
                        default_price=defaults_by_name[name]["default_price"],
                        image=defaults_by_name[name]["image"],
                    )
                    for name in missing_names
                ]

                # ignore_conflicts protects against races if another request creates same (restaurant,name)
                BaseItem.objects.bulk_create(new_base_items, ignore_conflicts=True)

                # Re-fetch to ensure we have PKs for everything
                existing_qs = BaseItem.objects.filter(
                    restaurant=restaurant,
                    name__in=all_base_names,
                ).only("id", "name", "default_price", "description", "image")
                base_by_name = {b.name: b for b in existing_qs}

            # =========================================================
            # 2) MENUS (restaurant-scoped): bulk_create
            # =========================================================
            menus_to_create = [
                Menu(
                    restaurant=restaurant,
                    name=m["name"],
                    description=m.get("description", "") or "",
                    is_active=m.get("is_active", True),
                )
                for m in menus_vd
            ]
            Menu.objects.bulk_create(menus_to_create)

            # NOTE: On PostgreSQL, PKs are populated after bulk_create.
            # If you use a backend that doesn't, you'd need a re-query strategy.
            created_menu_ids = [m.id for m in menus_to_create]

            # =========================================================
            # 3) CATEGORIES: bulk_create + map back
            # =========================================================
            categories_to_create = []
            category_key_order = []  # (menu_index, category_index)

            for mi, m in enumerate(menus_vd):
                menu_obj = menus_to_create[mi]
                for ci, c in enumerate(m["categories"]):
                    categories_to_create.append(
                        MenuCategory(
                            menu=menu_obj,
                            name=c["name"],
                            sort_order=c.get("sort_order", 0) or 0,
                        )
                    )
                    category_key_order.append((mi, ci))

            MenuCategory.objects.bulk_create(categories_to_create)
            category_by_key = {
                key: categories_to_create[i] for i, key in enumerate(category_key_order)
            }

            # =========================================================
            # 4) ITEMS: bulk_create + map back
            # =========================================================
            items_to_create = []
            item_key_order = []  # (mi, ci, ii)

            for mi, m in enumerate(menus_vd):
                for ci, c in enumerate(m["categories"]):
                    cat_obj = category_by_key[(mi, ci)]
                    for ii, it in enumerate(c["items"]):
                        base = base_by_name[it["base_item"]["name"].strip()]
                        items_to_create.append(
                            MenuItem(
                                category=cat_obj,
                                base_item=base,
                                custom_name=it.get("custom_name") or base.name,
                                description=it.get("description", "") or base.description,
                                # if not provided, fall back to base default_price
                                price=it.get("price", None) or base.default_price,
                                image=it.get("image") or None,
                            )
                        )
                        item_key_order.append((mi, ci, ii))

            MenuItem.objects.bulk_create(items_to_create)
            item_by_key = {key: items_to_create[i] for i, key in enumerate(item_key_order)}

            # =========================================================
            # 5) VARIANTS: bulk_create groups then options
            # =========================================================
            vgroups_to_create = []
            vgroup_key_order = []  # (mi, ci, ii, vgi)

            for mi, m in enumerate(menus_vd):
                for ci, c in enumerate(m["categories"]):
                    for ii, it in enumerate(c["items"]):
                        item_obj = item_by_key[(mi, ci, ii)]
                        for vgi, vg in enumerate(it.get("variant_groups", [])):
                            vgroups_to_create.append(
                                VariantGroup(
                                    item=item_obj,
                                    name=vg["name"],
                                    is_required=vg.get("is_required", True),
                                )
                            )
                            vgroup_key_order.append((mi, ci, ii, vgi))

            if vgroups_to_create:
                VariantGroup.objects.bulk_create(vgroups_to_create)
                vgroup_by_key = {
                    key: vgroups_to_create[i] for i, key in enumerate(vgroup_key_order)
                }

                voptions_to_create = []
                for mi, m in enumerate(menus_vd):
                    for ci, c in enumerate(m["categories"]):
                        for ii, it in enumerate(c["items"]):
                            for vgi, vg in enumerate(it.get("variant_groups", [])):
                                group_obj = vgroup_by_key[(mi, ci, ii, vgi)]
                                for opt in vg.get("options", []):
                                    voptions_to_create.append(
                                        VariantOption(
                                            group=group_obj,
                                            name=opt["name"],
                                            price_diff=opt.get("price_diff", 0) or 0,
                                        )
                                    )
                if voptions_to_create:
                    VariantOption.objects.bulk_create(voptions_to_create)

            # =========================================================
            # 6) ADDON GROUPS + ADDONS + through M2M: bulk_create all
            # =========================================================
            addon_groups_to_create = []
            addon_group_key_order = []  # (mi, ci, ii, agi)

            for mi, m in enumerate(menus_vd):
                for ci, c in enumerate(m["categories"]):
                    for ii, it in enumerate(c["items"]):
                        item_obj = item_by_key[(mi, ci, ii)]
                        for agi, ag in enumerate(it.get("addon_groups", [])):
                            addon_groups_to_create.append(
                                MenuItemAddonGroup(
                                    item=item_obj,
                                    name=ag["name"],
                                    is_required=ag.get("is_required", False),
                                    max_selection=ag.get("max_selection", 0) or 0,
                                )
                            )
                            addon_group_key_order.append((mi, ci, ii, agi))

            if addon_groups_to_create:
                MenuItemAddonGroup.objects.bulk_create(addon_groups_to_create)
                addon_group_by_key = {
                    key: addon_groups_to_create[i]
                    for i, key in enumerate(addon_group_key_order)
                }

                addons_to_create = []
                addon_links = []  # (addon_index, group_obj)

                for mi, m in enumerate(menus_vd):
                    for ci, c in enumerate(m["categories"]):
                        for ii, it in enumerate(c["items"]):
                            for agi, ag in enumerate(it.get("addon_groups", [])):
                                group_obj = addon_group_by_key[(mi, ci, ii, agi)]
                                for addon in ag.get("addons", []):
                                    base = base_by_name[addon["base_item"]["name"].strip()]
                                    addons_to_create.append(
                                        MenuItemAddon(
                                            base_item=base,
                                            price=addon.get("price", None)
                                            or base.default_price,
                                        )
                                    )
                                    addon_links.append((len(addons_to_create) - 1, group_obj))

                if addons_to_create:
                    MenuItemAddon.objects.bulk_create(addons_to_create)

                    # bulk insert M2M through rows
                    through_model = MenuItemAddon.groups.through
                    through_rows = [
                        through_model(
                            menuitemaddon_id=addons_to_create[addon_i].id,
                            menuitemaddongroup_id=group_obj.id,
                        )
                        for (addon_i, group_obj) in addon_links
                    ]
                    if through_rows:
                        through_model.objects.bulk_create(through_rows, ignore_conflicts=True)

            # =========================================================
            # 7) BOOTSTRAP BRANCH CATALOG (Availability rows)
            #    Create availability for ALL referenced BaseItems
            # =========================================================
            base_ids = [b.id for b in base_by_name.values()]

            availability_rows = [
                BaseItemAvailability(branch=branch, base_item_id=bid, is_available=True)
                for bid in base_ids
            ]
            BaseItemAvailability.objects.bulk_create(
                availability_rows,
                ignore_conflicts=True,  # do not overwrite existing toggles/overrides
            )

        return Response(
            {
                "message": "Menus registered successfully",
                "menus": created_menu_ids,
                "company_name": restaurant.company_name,
                "base_items_referenced": len(all_base_names),
            },
            status=status.HTTP_201_CREATED,
        )

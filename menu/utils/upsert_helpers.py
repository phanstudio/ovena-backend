from menu.models import(
    BaseItem, Menu, MenuCategory, MenuItem, 
    MenuItemAddon, MenuItemAddonGroup, VariantGroup, 
    VariantOption, BaseItemAvailability, 
)
from django.db import transaction
# ─────────────────────────────────────────────────────────────────────────────
# upsert_helpers.py  —  All bulk upsert logic
# ─────────────────────────────────────────────────────────────────────────────

def _is_new(data: dict) -> bool:
    """No `id` key at all → CREATE."""
    return "id" not in data


def _is_skip(data: dict) -> bool:
    """`id` present but no other meaningful keys → SKIP (no DB write)."""
    return "id" in data and len([k for k in data if k != "id"]) == 0


def _is_update(data: dict) -> bool:
    """`id` + at least one other field → UPDATE."""
    return "id" in data and not _is_skip(data)


def _pick(data: dict, *fields) -> dict:
    """Return only the given fields that are present in data."""
    return {f: data[f] for f in fields if f in data}


def bootstrap_base_item_availability_for_business(business, base_ids =None, batch_size=10_000, save_point=True):
    """
    Create BaseItemAvailability rows:
      (branch, base_item) => is_available=True
    for every branch in a business.

    - ignore_conflicts=True means: if a toggle already exists, we don't overwrite it.
    """

    branches = list(business.branches.all().only("id"))
    if not branches:
        return 0

    if not base_ids:
        return 0

    rows = []
    created_total = 0

    with transaction.atomic(savepoint=save_point):
        for br in branches:
            for bid in base_ids:
                rows.append(BaseItemAvailability(branch_id=br.id, base_item_id=bid, is_available=True))

                # prevent huge memory usage
                if len(rows) >= batch_size:
                    BaseItemAvailability.objects.bulk_create(rows, ignore_conflicts=True)
                    created_total += len(rows)
                    rows.clear()

        if rows:
            BaseItemAvailability.objects.bulk_create(rows, ignore_conflicts=True)
            created_total += len(rows)

    return created_total


# ─────────────────────────────────────────────────────────────────────────────
# BaseItem resolution  —  shared across MenuItem and Addon creation/update
#
# Strategy:
#   no id  → get_or_create by (business, name), then point FK at it
#   id only → skip, keep existing FK
#   id + fields → update the shared BaseItem in place (affects all references)
#
# Returns: dict mapping a stable "slot key" → BaseItem ORM object
# We use slot keys because the same base_item dict is mutated with `_base_obj`.
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_base_items(business, base_item_dicts: list[dict]):
    """
    Mutates each dict in base_item_dicts by attaching `_base_obj` (a BaseItem instance)
    or `_base_obj = None` if resolution failed (id not found).

    base_item_dicts: flat list of base_item sub-dicts from validated_data.
    """

    # ── Partition ────────────────────────────────────────────────────────────
    to_create  = [bi for bi in base_item_dicts if _is_new(bi)]
    to_update  = [bi for bi in base_item_dicts if _is_update(bi)]
    to_skip    = [bi for bi in base_item_dicts if _is_skip(bi)]

    # ── 1. UPDATE shared BaseItems in bulk ───────────────────────────────────
    if to_update:
        ids = [bi["id"] for bi in to_update]
        existing = {obj.id: obj for obj in
                    BaseItem.objects.filter(id__in=ids, business=business)}

        objs_to_bulk_update, changed_fields = [], set()
        for bi in to_update:
            obj = existing.get(bi["id"])
            if not obj:
                bi["_base_obj"] = None
                continue
            fields = _pick(bi, "name", "description", "image")
            if "price" in bi:
                fields["default_price"] = bi["price"]
            for f, v in fields.items():
                setattr(obj, f, v)
                changed_fields.add(f)
            objs_to_bulk_update.append(obj)
            bi["_base_obj"] = obj

        if objs_to_bulk_update and changed_fields:
            BaseItem.objects.bulk_update(objs_to_bulk_update, list(changed_fields))

    # ── 2. SKIP — just attach the existing FK object (lazy, batched) ─────────
    if to_skip:
        ids = [bi["id"] for bi in to_skip]
        existing = {obj.id: obj for obj in
                    BaseItem.objects.filter(id__in=ids, business=business).only("id")}
        for bi in to_skip:
            bi["_base_obj"] = existing.get(bi["id"])

    # ── 3. CREATE — get_or_create by (business, name) ────────────────────────
    if to_create:
        names = [(bi.get("name") or "").strip() for bi in to_create]
        names_set = set(n for n in names if n)

        # Fetch existing by name
        existing_by_name = {
            obj.name: obj for obj in
            BaseItem.objects.filter(business=business, name__in=names_set)
        }

        missing_names = names_set - set(existing_by_name.keys())

        if missing_names:
            # First-seen defaults win for duplicate names in same payload
            defaults: dict[str, dict] = {}
            for bi in to_create:
                nm = (bi.get("name") or "").strip()
                if nm in missing_names:
                    defaults.setdefault(nm, {
                        "description":  bi.get("description", "") or "",
                        "default_price": bi["price"],
                        "image":        bi.get("image") or None,
                    })

            new_objs = [
                BaseItem(business=business, name=nm, **defs)
                for nm, defs in defaults.items()
            ]
            BaseItem.objects.bulk_create(new_objs, ignore_conflicts=True)

            # Re-fetch to get PKs (bulk_create may not populate them on all backends)
            for obj in BaseItem.objects.filter(business=business, name__in=missing_names):
                existing_by_name[obj.name] = obj

        # Bootstrap availability for newly seen base items
        new_base_ids = [obj.id for nm, obj in existing_by_name.items() if nm in missing_names]
        if new_base_ids:
            bootstrap_base_item_availability_for_business(business, new_base_ids, save_point=False)

        for bi in to_create:
            nm = (bi.get("name") or "").strip()
            bi["_base_obj"] = existing_by_name.get(nm)

# ─────────────────────────────────────────────────────────────────────────────
# Core upsert functions  —  each follows the same pattern:
#   1. partition into new / update / skip
#   2. bulk_update (only dirty fields)
#   3. bulk_create
#   4. attach _obj to each vd dict so children can reference it
#   5. recurse into children
# ─────────────────────────────────────────────────────────────────────────────

def upsert_menus(business, menus_vd: list[dict]) -> dict:
    stats = {k: 0 for k in [
        "menus_created", "menus_updated",
        "categories_created", "categories_updated",
        "items_created", "items_updated",
        "variant_groups_created", "variant_groups_updated",
        "variant_options_created", "variant_options_updated",
        "addon_groups_created", "addon_groups_updated",
        "addons_created", "addons_updated",
    ]}

    new_m    = [m for m in menus_vd if _is_new(m)]
    update_m = [m for m in menus_vd if _is_update(m)]
    skip_m   = [m for m in menus_vd if _is_skip(m)]

    # ── UPDATE ────────────────────────────────────────────────────────────────
    if update_m:
        ids = [m["id"] for m in update_m]
        existing = {o.id: o for o in Menu.objects.filter(id__in=ids, business=business)}
        to_bulk, changed = [], set()
        for m in update_m:
            obj = existing.get(m["id"])
            if not obj:
                m["_obj"] = None; continue
            fields = _pick(m, "name", "description", "is_active")
            for f, v in fields.items():
                setattr(obj, f, v); changed.add(f)
            to_bulk.append(obj); m["_obj"] = obj
        if to_bulk and changed:
            Menu.objects.bulk_update(to_bulk, list(changed))
            stats["menus_updated"] += len(to_bulk)

    # attach _obj for skipped menus (needed to traverse their children)
    if skip_m:
        ids = [m["id"] for m in skip_m]
        existing = {o.id: o for o in Menu.objects.filter(id__in=ids, business=business)}
        for m in skip_m:
            m["_obj"] = existing.get(m["id"])

    # ── CREATE ────────────────────────────────────────────────────────────────
    if new_m:
        objs = [Menu(business=business,
                     name=m["name"],
                     description=m.get("description", "") or "",
                     is_active=m.get("is_active", True))
                for m in new_m]
        Menu.objects.bulk_create(objs)
        for m, obj in zip(new_m, objs):
            m["_obj"] = obj
        stats["menus_created"] += len(objs)

    # ── RECURSE into categories for all menus that have them ─────────────────
    menus_with_cats = [m for m in menus_vd if m.get("_obj") and "categories" in m]
    if menus_with_cats:
        _upsert_categories(business, menus_with_cats, stats)

    return stats


def _upsert_categories(business, menus_vd, stats):
    new_c, update_c, skip_c = [], [], []

    for m in menus_vd:
        menu_obj = m["_obj"]
        for c in m.get("categories", []):
            c["_menu_obj"] = menu_obj          # carry parent ref
            if _is_new(c):     new_c.append(c)
            elif _is_update(c): update_c.append(c)
            else:               skip_c.append(c)

    # ── UPDATE ────────────────────────────────────────────────────────────────
    if update_c:
        ids = [c["id"] for c in update_c]
        existing = {o.id: o for o in MenuCategory.objects.filter(id__in=ids)}
        to_bulk, changed = [], set()
        for c in update_c:
            obj = existing.get(c["id"])
            if not obj:
                c["_obj"] = None; continue
            fields = _pick(c, "name", "sort_order")
            for f, v in fields.items():
                setattr(obj, f, v); changed.add(f)
            to_bulk.append(obj); c["_obj"] = obj
        if to_bulk and changed:
            MenuCategory.objects.bulk_update(to_bulk, list(changed))
            stats["categories_updated"] += len(to_bulk)

    if skip_c:
        ids = [c["id"] for c in skip_c]
        existing = {o.id: o for o in MenuCategory.objects.filter(id__in=ids)}
        for c in skip_c:
            c["_obj"] = existing.get(c["id"])

    # ── CREATE ────────────────────────────────────────────────────────────────
    if new_c:
        objs = [MenuCategory(menu=c["_menu_obj"], name=c["name"],
                             sort_order=c.get("sort_order", 0) or 0)
                for c in new_c]
        MenuCategory.objects.bulk_create(objs)
        for c, obj in zip(new_c, objs):
            c["_obj"] = obj
        stats["categories_created"] += len(objs)

    # ── RECURSE ───────────────────────────────────────────────────────────────
    all_cats = new_c + update_c + skip_c
    cats_with_items = [c for c in all_cats if c.get("_obj") and "items" in c]
    if cats_with_items:
        _upsert_items(business, cats_with_items, stats)


def _upsert_items(business, cats_vd, stats):
    new_it, update_it, skip_it = [], [], []

    for c in cats_vd:
        cat_obj = c["_obj"]
        for it in c.get("items", []):
            it["_cat_obj"] = cat_obj
            if _is_new(it):      new_it.append(it)
            elif _is_update(it): update_it.append(it)
            else:                skip_it.append(it)

    # Resolve ALL base_items in one batched round-trip
    all_items_with_bi = [it for it in new_it + update_it + skip_it if "base_item" in it]
    if all_items_with_bi:
        _resolve_base_items(business, [it["base_item"] for it in all_items_with_bi])
        for it in all_items_with_bi:
            it["_base_obj"] = it["base_item"].get("_base_obj")

    # ── UPDATE ────────────────────────────────────────────────────────────────
    if update_it:
        ids = [it["id"] for it in update_it]
        existing = {o.id: o for o in MenuItem.objects.filter(id__in=ids)}
        to_bulk, changed = [], set()
        for it in update_it:
            obj = existing.get(it["id"])
            if not obj:
                it["_obj"] = None; continue
            fields = _pick(it, "custom_name", "description", "price", "image")
            if it.get("_base_obj"):
                fields["base_item"] = it["_base_obj"]
                changed.add("base_item_id")
            for f, v in fields.items():
                setattr(obj, f, v); changed.add(f)
            to_bulk.append(obj); it["_obj"] = obj
        if to_bulk and changed:
            # base_item is a FK — bulk_update needs the field name without _id suffix
            update_fields = list(changed - {"base_item_id"})
            if "base_item_id" in changed:
                update_fields.append("base_item")
            MenuItem.objects.bulk_update(to_bulk, update_fields)
            stats["items_updated"] += len(to_bulk)

    if skip_it:
        ids = [it["id"] for it in skip_it]
        existing = {o.id: o for o in MenuItem.objects.filter(id__in=ids)}
        for it in skip_it:
            it["_obj"] = existing.get(it["id"])

    # ── CREATE ────────────────────────────────────────────────────────────────
    if new_it:
        objs = []
        for it in new_it:
            base = it.get("_base_obj")
            objs.append(MenuItem(
                category=it["_cat_obj"],
                base_item=base,
                custom_name=it.get("custom_name") or (base.name if base else ""),
                description=it.get("description") or (base.description if base else ""),
                price=it["price"] if it.get("price") is not None else (base.default_price if base else 0),
                image=it.get("image") or None,
            ))
        MenuItem.objects.bulk_create(objs)
        for it, obj in zip(new_it, objs):
            it["_obj"] = obj
        stats["items_created"] += len(objs)

    # ── RECURSE ───────────────────────────────────────────────────────────────
    all_items = new_it + update_it + skip_it
    items_with_vg = [it for it in all_items if it.get("_obj") and "variant_groups" in it]
    items_with_ag = [it for it in all_items if it.get("_obj") and "addon_groups" in it]
    if items_with_vg:
        _upsert_variant_groups(items_with_vg, stats)
    if items_with_ag:
        _upsert_addon_groups(business, items_with_ag, stats)


def _upsert_variant_groups(items_vd, stats):
    new_vg, update_vg, skip_vg = [], [], []

    for it in items_vd:
        item_obj = it["_obj"]
        for vg in it.get("variant_groups", []):
            vg["_item_obj"] = item_obj
            if _is_new(vg):      new_vg.append(vg)
            elif _is_update(vg): update_vg.append(vg)
            else:                skip_vg.append(vg)

    if update_vg:
        ids = [vg["id"] for vg in update_vg]
        existing = {o.id: o for o in VariantGroup.objects.filter(id__in=ids)}
        to_bulk, changed = [], set()
        for vg in update_vg:
            obj = existing.get(vg["id"])
            if not obj:
                vg["_obj"] = None; continue
            fields = _pick(vg, "name", "is_required")
            for f, v in fields.items():
                setattr(obj, f, v); changed.add(f)
            to_bulk.append(obj); vg["_obj"] = obj
        if to_bulk and changed:
            VariantGroup.objects.bulk_update(to_bulk, list(changed))
            stats["variant_groups_updated"] += len(to_bulk)

    if skip_vg:
        ids = [vg["id"] for vg in skip_vg]
        existing = {o.id: o for o in VariantGroup.objects.filter(id__in=ids)}
        for vg in skip_vg:
            vg["_obj"] = existing.get(vg["id"])

    if new_vg:
        objs = [VariantGroup(item=vg["_item_obj"], name=vg["name"],
                             is_required=vg.get("is_required", True))
                for vg in new_vg]
        VariantGroup.objects.bulk_create(objs)
        for vg, obj in zip(new_vg, objs):
            vg["_obj"] = obj
        stats["variant_groups_created"] += len(objs)

    all_vg = new_vg + update_vg + skip_vg
    vg_with_opts = [vg for vg in all_vg if vg.get("_obj") and "options" in vg]
    if vg_with_opts:
        _upsert_variant_options(vg_with_opts, stats)


def _upsert_variant_options(vgroups_vd, stats):
    new_opt, update_opt = [], []

    for vg in vgroups_vd:
        group_obj = vg["_obj"]
        for opt in vg.get("options", []):
            opt["_group_obj"] = group_obj
            if _is_new(opt):      new_opt.append(opt)
            elif _is_update(opt): update_opt.append(opt)
            # skip-only options: nothing to do

    if update_opt:
        ids = [o["id"] for o in update_opt]
        existing = {o.id: o for o in VariantOption.objects.filter(id__in=ids)}
        to_bulk, changed = [], set()
        for opt in update_opt:
            obj = existing.get(opt["id"])
            if not obj: continue
            fields = _pick(opt, "name", "price_diff")
            for f, v in fields.items():
                setattr(obj, f, v); changed.add(f)
            to_bulk.append(obj)
        if to_bulk and changed:
            VariantOption.objects.bulk_update(to_bulk, list(changed))
            stats["variant_options_updated"] += len(to_bulk)

    if new_opt:
        objs = [VariantOption(group=opt["_group_obj"], name=opt["name"],
                              price_diff=opt.get("price_diff", 0) or 0)
                for opt in new_opt]
        VariantOption.objects.bulk_create(objs)
        stats["variant_options_created"] += len(objs)


def _upsert_addon_groups(business, items_vd, stats):
    new_ag, update_ag, skip_ag = [], [], []

    for it in items_vd:
        item_obj = it["_obj"]
        for ag in it.get("addon_groups", []):
            ag["_item_obj"] = item_obj
            if _is_new(ag):      new_ag.append(ag)
            elif _is_update(ag): update_ag.append(ag)
            else:                skip_ag.append(ag)

    if update_ag:
        ids = [ag["id"] for ag in update_ag]
        existing = {o.id: o for o in MenuItemAddonGroup.objects.filter(id__in=ids)}
        to_bulk, changed = [], set()
        for ag in update_ag:
            obj = existing.get(ag["id"])
            if not obj:
                ag["_obj"] = None; continue
            fields = _pick(ag, "name", "is_required", "max_selection")
            for f, v in fields.items():
                setattr(obj, f, v); changed.add(f)
            to_bulk.append(obj); ag["_obj"] = obj
        if to_bulk and changed:
            MenuItemAddonGroup.objects.bulk_update(to_bulk, list(changed))
            stats["addon_groups_updated"] += len(to_bulk)

    if skip_ag:
        ids = [ag["id"] for ag in skip_ag]
        existing = {o.id: o for o in MenuItemAddonGroup.objects.filter(id__in=ids)}
        for ag in skip_ag:
            ag["_obj"] = existing.get(ag["id"])

    if new_ag:
        objs = [MenuItemAddonGroup(item=ag["_item_obj"], name=ag["name"],
                                   is_required=ag.get("is_required", False),
                                   max_selection=ag.get("max_selection", 0) or 0)
                for ag in new_ag]
        MenuItemAddonGroup.objects.bulk_create(objs)
        for ag, obj in zip(new_ag, objs):
            ag["_obj"] = obj
        stats["addon_groups_created"] += len(objs)

    all_ag = new_ag + update_ag + skip_ag
    ag_with_addons = [ag for ag in all_ag if ag.get("_obj") and "addons" in ag]
    if ag_with_addons:
        _upsert_addons(business, ag_with_addons, stats)


def _upsert_addons(business, addon_groups_vd, stats):
    new_ad, update_ad = [], []

    for ag in addon_groups_vd:
        group_obj = ag["_obj"]
        for ad in ag.get("addons", []):
            ad["_group_obj"] = group_obj
            if _is_new(ad):      new_ad.append(ad)
            elif _is_update(ad): update_ad.append(ad)

    # Resolve base items for all addons in one batch
    all_ads_with_bi = [ad for ad in new_ad + update_ad if "base_item" in ad]
    if all_ads_with_bi:
        _resolve_base_items(business, [ad["base_item"] for ad in all_ads_with_bi])
        for ad in all_ads_with_bi:
            ad["_base_obj"] = ad["base_item"].get("_base_obj")

    if update_ad:
        ids = [ad["id"] for ad in update_ad]
        existing = {o.id: o for o in MenuItemAddon.objects.filter(id__in=ids)}
        to_bulk, changed = [], set()
        for ad in update_ad:
            obj = existing.get(ad["id"])
            if not obj: continue
            fields = _pick(ad, "price")
            if ad.get("_base_obj"):
                fields["base_item"] = ad["_base_obj"]
                changed.add("base_item_id")
            for f, v in fields.items():
                setattr(obj, f, v); changed.add(f)
            to_bulk.append(obj)
        if to_bulk and changed:
            update_fields = list(changed - {"base_item_id"})
            if "base_item_id" in changed:
                update_fields.append("base_item")
            MenuItemAddon.objects.bulk_update(to_bulk, update_fields)
            stats["addons_updated"] += len(to_bulk)

    if new_ad:
        objs = []
        for ad in new_ad:
            base = ad.get("_base_obj")
            objs.append(MenuItemAddon(
                base_item=base,
                price=ad.get("price") if ad.get("price") is not None else (base.default_price if base else 0),
            ))
        MenuItemAddon.objects.bulk_create(objs)

        # Wire M2M through-table
        through_model = MenuItemAddon.groups.through
        through_rows = [
            through_model(menuitemaddon_id=obj.id,
                          menuitemaddongroup_id=new_ad[i]["_group_obj"].id)
            for i, obj in enumerate(objs)
        ]
        if through_rows:
            through_model.objects.bulk_create(through_rows, ignore_conflicts=True)

        stats["addons_created"] += len(objs)


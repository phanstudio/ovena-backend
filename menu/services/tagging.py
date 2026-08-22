import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import List
from menu.models import MenuCategory
from menu.models.categories import GlobalTag
from django.db.models import Count

def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return text


def _token_overlap(a: str, b: str) -> float:
    """Jaccard similarity on word sets — catches 'Grilled Chicken' vs 'Chicken'."""
    tokens_a, tokens_b = set(a.split()), set(b.split())
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def _similarity_score(category_name: str, tag_name: str) -> float:
    a, b = _normalize(category_name), _normalize(tag_name)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.9
    ratio = SequenceMatcher(None, a, b).ratio()
    overlap = _token_overlap(a, b)
    return max(ratio, overlap)


@dataclass
class TagSuggestion:
    tag_id: int
    name: str
    score: float


def suggest_tags_for_category(
    category_name: str,
    all_tags,
    threshold: float = 0.5,
    limit: int = 3,
) -> List[TagSuggestion]:
    scored = []
    for tag in all_tags:
        score = _similarity_score(category_name, tag.name)
        if score >= threshold:
            scored.append(TagSuggestion(tag_id=tag.id, name=tag.name, score=round(score, 2)))
    scored.sort(key=lambda s: s.score, reverse=True)
    return scored[:limit]


def suggest_tags_for_business(business, threshold: float = 0.5, limit: int = 3):
    """
    Walk every MenuCategory belonging to `business` (across all its menus)
    and return, per category: its current tags + best-matching suggestions.

    Returns a list shaped for direct use in an admin review UI:
    [
      {
        "menu_id": 1, "menu_name": "Lunch Menu",
        "category_id": 5, "category_name": "Burgers",
        "current_tags": [{"id": 2, "name": "Fast Food"}],
        "suggested_tags": [{"id": 9, "name": "Burgers", "score": 1.0}, ...]
      },
      ...
    ]
    """

    all_tags = list(GlobalTag.objects.all())
    categories = (
        MenuCategory.objects
        .filter(menu__business=business)
        .select_related("menu")
        .prefetch_related("global_tags")
        .order_by("menu__name", "sort_order")
    )

    results = []
    for category in categories:
        current = list(category.global_tags.values("id", "name"))
        current_ids = {t["id"] for t in current}

        suggestions = suggest_tags_for_category(category.name, all_tags, threshold, limit)
        suggestions = [s for s in suggestions if s.tag_id not in current_ids]

        results.append({
            "menu_id": category.menu_id,
            "menu_name": category.menu.name,
            "category_id": category.id,
            "category_name": category.name,
            "current_tags": current,
            "suggested_tags": [
                {"id": s.tag_id, "name": s.name, "score": s.score} for s in suggestions
            ],
        })
    return results


def find_new_tag_candidates(threshold: float = 0.5, min_usage: int = 1, cluster_threshold: float = 0.75):
    

    existing_tags = list(GlobalTag.objects.all())

    # distinct category names platform-wide, with how many rows use each
    category_counts = (
        MenuCategory.objects
        .values("name")
        .annotate(usage_count=Count("id"))
        .order_by("-usage_count")
    )

    # keep only names that don't already match an existing tag well
    unmatched = []
    for row in category_counts:
        name, count = row["name"], row["usage_count"]
        if count < min_usage:
            continue
        best_score = max((_similarity_score(name, t.name) for t in existing_tags), default=0.0)
        if best_score < threshold:
            unmatched.append({"name": name, "usage_count": count})

    # cluster near-duplicate unmatched names together
    clusters = []
    used = set()
    for i, item in enumerate(unmatched):
        if item["name"] in used:
            continue
        cluster = {
            "suggested_name": item["name"],  # highest-usage variant becomes the display name
            "matched_category_names": [item["name"]],
            "usage_count": item["usage_count"],
        }
        used.add(item["name"])
        for other in unmatched[i + 1:]:
            if other["name"] in used:
                continue
            if _similarity_score(item["name"], other["name"]) >= cluster_threshold:
                cluster["matched_category_names"].append(other["name"])
                cluster["usage_count"] += other["usage_count"]
                used.add(other["name"])
        clusters.append(cluster)

    clusters.sort(key=lambda c: c["usage_count"], reverse=True)
    return clusters

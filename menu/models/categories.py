"""
Global category tagging — bulk suggestion + admin review flow.

This file is organized in four sections, meant to live in their
respective places in the project (models.py / services/tagging.py /
views.py / urls.py). Kept together here for easy review.

Design decisions this implements:
- MenuCategory <-> GlobalTag is many-to-many (a category can legitimately
  match more than one tag, e.g. "Grilled Chicken" -> Chicken + Grilled).
- Suggestions are business-scoped and bulk: walk every category for a
  business in one call, so the admin reviews/edits everything together
  instead of tag-by-tag.
- Already-attached tags are excluded from "suggested" so the admin only
  sees new candidates, not stuff they've already accepted.
- No external dependencies (no Postgres trigram extension required) —
  pure Python scoring so it works regardless of DB backend. If you're
  on Postgres and want faster/better fuzzy matching at scale later,
  swap _similarity_score's SequenceMatcher for TrigramSimilarity.
"""

# ============================================================
# 1. models.py  — add M2M tags to MenuCategory
# ============================================================

from django.db import models
from django.utils.text import slugify

class TagGroup(models.Model):
    """
    Platform-wide, curated taxonomy used for cross-business search/discovery.
    Not owned by any single business. Kept admin-managed to avoid
    near-duplicate sprawl (Burger / Burgers / burger).
    """
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    images = models.ImageField()

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class GlobalTag(models.Model):
    """
    Platform-wide, curated taxonomy used for cross-business search/discovery.
    Not owned by any single business. Kept admin-managed to avoid
    near-duplicate sprawl (Burger / Burgers / burger).
    """
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True, blank=True)

    group = models.ForeignKey(
        TagGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tags"
    )

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

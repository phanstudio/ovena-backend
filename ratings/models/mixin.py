from django.db import models

class RatingModelMixin(models.Model):
    rating_sum = models.IntegerField(default=0)          # total stars
    rating_count = models.PositiveIntegerField(default=0)
    avg_rating = models.FloatField(default=0.0, db_index=True)  # optional but convenient

    class Meta:
        abstract = True

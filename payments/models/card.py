from django.db import models
from accounts.models import User

class CardAuthorization(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    authorization_code = models.CharField(max_length=100, unique=True)
    last4 = models.CharField(max_length=4)
    exp_month = models.CharField(max_length=2)
    exp_year = models.CharField(max_length=4)
    brand = models.CharField(max_length=20)
    primary_card = models.BooleanField(default=False)

# use the card pk or id??
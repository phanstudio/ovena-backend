from django.db import models
from ulid import ULID # type: ignore

def generate_ulid():
    return str(ULID())
# Create your models here.
class ULIDField(models.CharField):

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_length", 26)
        kwargs.setdefault("default", generate_ulid)
        kwargs.setdefault("editable", False)
        super().__init__(*args, **kwargs)

# from django_ulid.models import ULIDField

class AbstractBaseModel(models.Model):
    id = ULIDField(primary_key=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        abstract = True

class AbstractUBaseModel(AbstractBaseModel):
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
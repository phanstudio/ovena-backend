from django.urls import path
from .. import views

prefix = "business-"
urlpatterns = [
    path("card/save/", views.BusinessSaveCardView.as_view(), name=prefix+"card-save"),
    path("card/list/", views.BusinessListCardsView.as_view(), name=prefix+"card-list"),
    path("card/setdefault/", views.BusinessSetPrimaryCardView.as_view(), name=prefix+"card-setdefualt"),
]

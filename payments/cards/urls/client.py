from django.urls import path
from .. import views

urlpatterns = [ # /client
    path("save/card/", views.SaveCardView.as_view(), name="card-save"),
]

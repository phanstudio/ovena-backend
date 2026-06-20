from django.urls import path
from .. import views

urlpatterns = [ # /admin
    path("features/bulk/", views.FeatureBulkCreateView.as_view(), name="features-bulk"),
    path("features/<int:pk>/", views.FeatureDetailView.as_view(), name="features-detail"), # you are unnessary
    path("features/", views.FeatureListCreateView.as_view(), name="features-list-create"),
    path("plan/", views.PlanListCreateView.as_view(), name="plan-list-create"),
    path("plan/<int:id>/", views.PlanDetailView.as_view(), name="plan-detail"),
    path("plan/<int:plain_id>/disable/", views.PlanDisableView.as_view(), name="plan-disable"),
]
from django.urls import path
from .. import views

urlpatterns = [ # /admin
    path("admin/features/bulk/", views.FeatureBulkCreateView.as_view(), name="features-bulk"),
    path("admin/features/<int:pk>/", views.FeatureDetailView.as_view(), name="features-detail"), # you are unnessary
    path("admin/features/", views.FeatureListCreateView.as_view(), name="features-list-create"),
    path("admin/plan/", views.PlanListCreateView.as_view(), name="plan-list-create"),
    path("admin/plan/<int:id>/", views.PlanDetailView.as_view(), name="plan-detail"),
    path("admin/plan/<int:plain_id>/disable/", views.PlanDisableView.as_view(), name="plan-disable"),
]
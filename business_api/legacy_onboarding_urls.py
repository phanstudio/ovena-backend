from django.urls import path

from menu.views import BatchGenerateUploadURLView, RegisterMenusPhase3View

from business_api import views


urlpatterns = [
    path("phase1/", views.RestaurantPhase1RegisterView.as_view(), name="legacy-business-register-phase1"),
    path("phase2/", views.RestaurantPhase2OnboardingView.as_view(), name="legacy-business-register-phase2"),
    path("phase3/", RegisterMenusPhase3View.as_view(), name="legacy-business-register-menus-ob"),
    path("batch-gen-url/", BatchGenerateUploadURLView.as_view(), name="legacy-business-batch-generate-url"),
    path("status/", views.BuisnnessOnboardingStatusView.as_view(), name="legacy-business-onboard-status"),
]

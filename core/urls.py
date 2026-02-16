from django.contrib import admin
from django.urls import path, include
from api import views
from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from django.conf import settings

docs_url = [
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]

urlpatterns = [
    path('admin/', admin.site.urls),
    path("api/", include("api.urls")),
    path('', views.index),
    path("", include(docs_url)),
]

if settings.ENABLE_METRICS:
    urlpatterns += [path("", include("django_prometheus.urls"))]

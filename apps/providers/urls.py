from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ProviderUsageViewSet, ProviderViewSet

router = DefaultRouter()
router.register(r"providers", ProviderViewSet)
router.register(r"usage", ProviderUsageViewSet)

urlpatterns = [
    path("", include(router.urls)),
]

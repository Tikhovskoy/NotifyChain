from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ProviderViewSet, ProviderUsageViewSet

router = DefaultRouter()
router.register(r'providers', ProviderViewSet)
router.register(r'usage', ProviderUsageViewSet)

urlpatterns = [
    path('api/', include(router.urls)),
]
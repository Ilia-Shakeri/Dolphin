from rest_framework.routers import DefaultRouter

from aftersales.views import AfterSalesRequestViewSet


router = DefaultRouter()
router.register("after-sales", AfterSalesRequestViewSet, basename="after-sales")
urlpatterns = router.urls

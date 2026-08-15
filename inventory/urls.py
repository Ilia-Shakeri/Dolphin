from rest_framework.routers import DefaultRouter

from inventory.views import StockItemViewSet, StockMovementViewSet, WarehouseViewSet


router = DefaultRouter()
router.register("warehouses", WarehouseViewSet, basename="warehouse")
router.register("stock-items", StockItemViewSet, basename="stock-item")
router.register("stock-movements", StockMovementViewSet, basename="stock-movement")
urlpatterns = router.urls

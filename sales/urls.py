from rest_framework.routers import DefaultRouter

from sales.views import CustomerPhoneViewSet, CustomerViewSet, InteractionViewSet, LeadViewSet, ProductCategoryViewSet, ProductViewSet, SaleViewSet, SalesDocumentViewSet


router = DefaultRouter()
router.register("customers", CustomerViewSet, basename="customer")
router.register("customer-phones", CustomerPhoneViewSet, basename="customer-phone")
router.register("leads", LeadViewSet, basename="lead")
router.register("interactions", InteractionViewSet, basename="interaction")
router.register("product-categories", ProductCategoryViewSet, basename="product-category")
router.register("products", ProductViewSet, basename="product")
router.register("sales", SaleViewSet, basename="sale")
router.register("sales-documents", SalesDocumentViewSet, basename="sales-document")
urlpatterns = router.urls

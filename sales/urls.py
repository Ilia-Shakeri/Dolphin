from django.urls import path
from rest_framework.routers import DefaultRouter

from sales.views import CustomerPhoneViewSet, CustomerViewSet, InteractionViewSet, LeadViewSet, PostProviderSettingsView, ProductCategoryViewSet, ProductViewSet, SaleViewSet, SalesDocumentViewSet, TargetAudienceMemberViewSet, TestPostProviderConnectionView


router = DefaultRouter()
router.register("customers", CustomerViewSet, basename="customer")
router.register("customer-phones", CustomerPhoneViewSet, basename="customer-phone")
router.register("leads", LeadViewSet, basename="lead")
router.register("interactions", InteractionViewSet, basename="interaction")
router.register("target-audience", TargetAudienceMemberViewSet, basename="target-audience")
router.register("product-categories", ProductCategoryViewSet, basename="product-category")
router.register("products", ProductViewSet, basename="product")
router.register("sales", SaleViewSet, basename="sale")
router.register("sales-documents", SalesDocumentViewSet, basename="sales-document")
urlpatterns = [
    path("post-provider-settings/", PostProviderSettingsView.as_view(), name="post-provider-settings"),
    path(
        "post-provider-settings/test/",
        TestPostProviderConnectionView.as_view(),
        name="post-provider-settings-test",
    ),
    *router.urls,
]

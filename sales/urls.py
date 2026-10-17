from django.urls import path
from rest_framework.routers import DefaultRouter

from sales.campaign_views import CampaignMemberViewSet, CampaignViewSet
from sales.pipeline_views import (
    LostReasonDetailView,
    LostReasonListView,
    LostReasonMoveView,
    PipelineStageDetailView,
    PipelineStageListView,
    PipelineStageMoveView,
    PipelineView,
)
from sales.returned_work_views import ResolveReturnedWorkView, ReturnedWorkView
from sales.views import CustomerCategoryViewSet, CustomerPhoneViewSet, CustomerViewSet, InteractionViewSet, LeadViewSet, PostProviderSettingsView, ProductCategoryViewSet, ProductViewSet, SaleViewSet, SalesDocumentViewSet, TargetAudienceMemberViewSet, TestPostProviderConnectionView


router = DefaultRouter()
router.register("customers", CustomerViewSet, basename="customer")
router.register("customer-phones", CustomerPhoneViewSet, basename="customer-phone")
router.register("leads", LeadViewSet, basename="lead")
router.register("interactions", InteractionViewSet, basename="interaction")
router.register("target-audience", TargetAudienceMemberViewSet, basename="target-audience")
router.register("campaigns", CampaignViewSet, basename="campaign")
router.register("campaign-members", CampaignMemberViewSet, basename="campaign-member")
router.register("customer-categories", CustomerCategoryViewSet, basename="customer-category")
router.register("product-categories", ProductCategoryViewSet, basename="product-category")
router.register("products", ProductViewSet, basename="product")
router.register("sales", SaleViewSet, basename="sale")
router.register("sales-documents", SalesDocumentViewSet, basename="sales-document")
urlpatterns = [
    path("pipeline/", PipelineView.as_view(), name="pipeline"),
    path("pipeline/stages/", PipelineStageListView.as_view(), name="pipeline-stages"),
    path("pipeline/stages/<int:pk>/", PipelineStageDetailView.as_view(), name="pipeline-stage"),
    path("pipeline/stages/<int:pk>/move/", PipelineStageMoveView.as_view(), name="pipeline-stage-move"),
    path("pipeline/lost-reasons/", LostReasonListView.as_view(), name="pipeline-lost-reasons"),
    path("pipeline/lost-reasons/<int:pk>/", LostReasonDetailView.as_view(), name="pipeline-lost-reason"),
    path("pipeline/lost-reasons/<int:pk>/move/", LostReasonMoveView.as_view(), name="pipeline-lost-reason-move"),
    path("returned-work/", ReturnedWorkView.as_view(), name="returned-work"),
    path("returned-work/resolve/", ResolveReturnedWorkView.as_view(), name="returned-work-resolve"),
    path("post-provider-settings/", PostProviderSettingsView.as_view(), name="post-provider-settings"),
    path(
        "post-provider-settings/test/",
        TestPostProviderConnectionView.as_view(),
        name="post-provider-settings-test",
    ),
    *router.urls,
]

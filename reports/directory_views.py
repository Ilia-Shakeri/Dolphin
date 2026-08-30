"""XLSX exports of the user and customer directories.

Requirements 1.9 and 2.6. Both reuse the scoping the JSON list endpoints already
apply rather than querying the models directly, so an export can never show a
row its owner could not open in the interface — the failure mode a separate
query would eventually introduce.
"""

from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.access import crm_identities
from accounts.models import User
from accounts.services import USER_ADMINS
from common.openapi import ACCESS_DENIED_RESPONSE, THROTTLED_RESPONSE
from common.permissions import FeatureGatedAPIMixin
from common.throttles import SensitiveRateThrottle
from reports.views import XLSX_CONTENT_TYPE, XLSXNegotiationRenderer
from reports.xlsx import (
    build_customer_directory_workbook,
    build_product_catalogue_workbook,
    build_user_directory_workbook,
)
from rest_framework.exceptions import ValidationError

from sales.models import Customer
from sales.selectors import customers_for, products_for


class DirectoryExportView(APIView):
    """Shared XLSX-on-success, JSON-on-error behaviour."""

    renderer_classes = [XLSXNegotiationRenderer]
    throttle_classes = [SensitiveRateThrottle]
    filename = "dolphin-directory.xlsx"

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        if isinstance(response, Response) and response.status_code >= 400:
            renderer = JSONRenderer()
            response.accepted_renderer = renderer
            response.accepted_media_type = renderer.media_type
            response.content_type = renderer.media_type
        return response

    def workbook(self, request):
        raise NotImplementedError

    def get(self, request):
        payload = self.workbook(request)
        response = HttpResponse(payload, content_type=XLSX_CONTENT_TYPE)
        response["Content-Disposition"] = f'attachment; filename="{self.filename}"'
        response["Cache-Control"] = "private, no-store"
        return response


class UserDirectoryExportView(DirectoryExportView):
    filename = "dolphin-users.xlsx"

    @extend_schema(
        responses={
            (200, XLSX_CONTENT_TYPE): OpenApiResponse(
                response=OpenApiTypes.BINARY, description="CRM user directory."
            ),
            (403, "application/json"): ACCESS_DENIED_RESPONSE,
            (429, "application/json"): THROTTLED_RESPONSE,
        },
        description="CRM user directory as XLSX. Platform Admin only, matching who may list users.",
    )
    def get(self, request):
        return super().get(request)

    def workbook(self, request):
        from rest_framework.exceptions import PermissionDenied

        if request.user.role not in USER_ADMINS:
            raise PermissionDenied("User administration is not allowed.")
        users = crm_identities(User.objects.all()).order_by("username")
        return build_user_directory_workbook(users)


class CustomerDirectoryExportView(FeatureGatedAPIMixin, DirectoryExportView):
    required_feature = "customers"
    filename = "dolphin-customers.xlsx"

    @extend_schema(
        responses={
            (200, XLSX_CONTENT_TYPE): OpenApiResponse(
                response=OpenApiTypes.BINARY, description="Customer directory in the caller's scope."
            ),
            (403, "application/json"): ACCESS_DENIED_RESPONSE,
            (429, "application/json"): THROTTLED_RESPONSE,
        },
        parameters=[
            OpenApiParameter(
                "kind",
                str,
                description=(
                    "Which customer book to export: `individual` or `legal`. "
                    "Omitted exports both. A marketer may only ever read the "
                    "individual book, whatever they ask for."
                ),
            )
        ],
        description=(
            "Customer directory as XLSX, scoped exactly like the customer list endpoint. "
            "Its header row is what POST /api/v1/customers/import-xlsx/ reads."
        ),
    )
    def get(self, request):
        return super().get(request)

    def workbook(self, request):
        customers = (
            customers_for(request.user)
            .select_related("created_by")
            .prefetch_related("phones")
            .order_by("full_name")
        )
        # Narrowing only: `customers_for` has already settled which books this
        # caller may read at all.
        kind = request.query_params.get("kind")
        if kind is not None:
            if kind not in Customer.Kind.values:
                raise ValidationError({"kind": "Select a customer kind from the list."})
            customers = customers.filter(kind=kind)
        return build_customer_directory_workbook(customers)


class ProductCatalogueExportView(FeatureGatedAPIMixin, DirectoryExportView):
    """The product catalogue, in the shape the importer reads back.

    The columns here and the columns `sales.imports` accepts are the same tuple,
    so the operator can export, write on the file, and upload it again without
    reshaping anything.
    """

    required_feature = "products"
    filename = "dolphin-products.xlsx"

    @extend_schema(
        responses={
            (200, XLSX_CONTENT_TYPE): OpenApiResponse(
                response=OpenApiTypes.BINARY,
                description="Product catalogue in the caller's scope.",
            ),
            (403, "application/json"): ACCESS_DENIED_RESPONSE,
            (429, "application/json"): THROTTLED_RESPONSE,
        },
        description=(
            "Product catalogue as XLSX, scoped exactly like the product list endpoint. "
            "Its header row is what POST /api/v1/products/import-xlsx/ reads."
        ),
    )
    def get(self, request):
        return super().get(request)

    def workbook(self, request):
        products = (
            products_for(request.user).select_related("category").order_by("name", "pk")
        )
        return build_product_catalogue_workbook(products)

from drf_spectacular.utils import OpenApiExample, OpenApiResponse
from rest_framework import serializers


class ApiErrorReferenceSerializer(serializers.Serializer):
    code = serializers.CharField()
    request_id = serializers.CharField()


class ApiErrorEnvelopeSerializer(serializers.Serializer):
    detail = serializers.JSONField(
        required=False,
        help_text="Safe error detail. Validation responses may also include field-name keys.",
    )
    error = ApiErrorReferenceSerializer()


def _error_example(name, *, code, detail):
    return OpenApiExample(
        name,
        value={
            "detail": detail,
            "error": {
                "code": code,
                "request_id": "request-id-123",
            },
        },
        response_only=True,
    )


VALIDATION_ERROR_RESPONSE = OpenApiResponse(
    response=ApiErrorEnvelopeSerializer,
    description="Request validation failed.",
    examples=[
        OpenApiExample(
            "Validation error",
            value={
                "field": ["Invalid value."],
                "error": {
                    "code": "validation_error",
                    "request_id": "request-id-123",
                },
            },
            response_only=True,
        )
    ],
)

ACCESS_DENIED_RESPONSE = OpenApiResponse(
    response=ApiErrorEnvelopeSerializer,
    description="Authentication or permission check failed.",
    examples=[
        _error_example(
            "Authentication failed",
            code="authentication_failed",
            detail="Authentication credentials were not provided.",
        ),
        _error_example(
            "Permission denied",
            code="permission_denied",
            detail="Permission denied.",
        ),
    ],
)

CSRF_OR_ACCESS_DENIED_RESPONSE = OpenApiResponse(
    response=ApiErrorEnvelopeSerializer,
    description="Authentication, permission, or CSRF check failed.",
    examples=[
        _error_example(
            "CSRF failed",
            code="csrf_failed",
            detail="CSRF check failed.",
        ),
        _error_example(
            "Authentication failed",
            code="authentication_failed",
            detail="Authentication credentials were not provided.",
        ),
    ],
)

NOT_FOUND_RESPONSE = OpenApiResponse(
    response=ApiErrorEnvelopeSerializer,
    description="The object is absent or outside actor scope.",
    examples=[
        _error_example(
            "Not found",
            code="not_found",
            detail="Not found.",
        )
    ],
)

CONFLICT_RESPONSE = OpenApiResponse(
    response=ApiErrorEnvelopeSerializer,
    description="The requested state change conflicts with current state.",
    examples=[
        _error_example(
            "Conflict",
            code="conflict",
            detail="The requested state change conflicts with current state.",
        )
    ],
)

THROTTLED_RESPONSE = OpenApiResponse(
    response=ApiErrorEnvelopeSerializer,
    description="Request rate exceeded.",
    examples=[
        _error_example(
            "Throttled",
            code="throttled",
            detail="Request was throttled.",
        )
    ],
)


_COMMON_ERROR_DETAILS = {
    "400": ("validation_error", "Request validation failed."),
    "403": ("permission_denied", "Permission denied."),
    "404": ("not_found", "Not found."),
    "409": ("conflict", "The requested state change conflicts with current state."),
    "413": ("payload_too_large", "Request body is too large."),
    "429": ("throttled", "Request was throttled."),
    "500": ("server_error", "Internal server error."),
}

_BODY_METHODS = {"post", "put", "patch"}
_OPERATIONS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


def _error_response_schema(status_code):
    error_code, detail = _COMMON_ERROR_DETAILS[status_code]
    return {
        "description": detail,
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/ApiErrorEnvelope"},
                "examples": {
                    error_code: {
                        "summary": detail,
                        "value": {
                            "detail": detail,
                            "error": {
                                "code": error_code,
                                "request_id": "request-id-123",
                            },
                        },
                    }
                },
            }
        },
    }


def _response_codes_for(path, method):
    codes = {"500"}
    if path.startswith("/api/v1/health/"):
        return codes

    codes.update({"403", "429"})
    if path.startswith(
        (
            "/api/v1/customers/",
            "/api/v1/customer-phones/",
            "/api/v1/leads/",
            "/api/v1/interactions/",
            "/api/v1/products/",
            "/api/v1/sales/",
            "/api/v1/users/",
            "/api/v1/reports/",
            "/api/v1/exports/",
        )
    ):
        codes.add("400")
    if "{" in path:
        codes.add("404")
    if method in _BODY_METHODS:
        codes.add("413")
    if method in {"post", "put", "patch", "delete"} and not path.startswith("/api/v1/auth/"):
        codes.add("409")
    return codes


def add_common_api_contract(result, generator, request, public):
    """Add the shared safe error and request-trace contract to API operations."""
    del generator, request, public
    request_id_header = {
        "description": "Sanitized request trace identifier.",
        "schema": {"type": "string", "maxLength": 64},
    }

    for path, path_item in result.get("paths", {}).items():
        for method, operation in path_item.items():
            if method not in _OPERATIONS or not isinstance(operation, dict):
                continue
            responses = operation.setdefault("responses", {})
            for status_code in _response_codes_for(path, method):
                responses.setdefault(status_code, _error_response_schema(status_code))
            for response in responses.values():
                if isinstance(response, dict) and "$ref" not in response:
                    response.setdefault("headers", {}).setdefault(
                        "X-Request-ID",
                        request_id_header,
                    )
    return result

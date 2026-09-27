"""How the public API's token authentication appears in the OpenAPI schema."""

from drf_spectacular.extensions import OpenApiAuthenticationExtension


class ApiTokenScheme(OpenApiAuthenticationExtension):
    target_class = "integrations.authentication.ApiTokenAuthentication"
    name = "dolphinApiToken"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "description": (
                "`Authorization: Bearer dol_…` (feature `public_api`). The request runs as the token's user; "
                "a `read` token is refused any unsafe method."
            ),
        }

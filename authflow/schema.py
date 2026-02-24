# authflow/schema.py
from drf_spectacular.extensions import OpenApiAuthenticationExtension


def _bearer_jwt():
    return {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }


class CustomJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    """
    This class supports BOTH Bearer and SubBearer in real life,
    but OpenAPI can only describe a single scheme per auth class.
    We'll describe it as Bearer JWT (the main one).
    """
    target_class = "authflow.authentication.CustomJWTAuthentication"
    name = "BearerJWT"

    def get_security_definition(self, auto_schema):
        return _bearer_jwt()


class CustomDriverAuthScheme(OpenApiAuthenticationExtension):
    target_class = "authflow.authentication.CustomDriverAuth"
    name = "DriverJWT"

    def get_security_definition(self, auto_schema):
        return _bearer_jwt()


class CustomCustomerAuthScheme(OpenApiAuthenticationExtension):
    target_class = "authflow.authentication.CustomCustomerAuth"
    name = "CustomerJWT"

    def get_security_definition(self, auto_schema):
        return _bearer_jwt()


class CustomBAdminAuthScheme(OpenApiAuthenticationExtension):
    target_class = "authflow.authentication.CustomBAdminAuth"
    name = "BusinessAdminJWT"

    def get_security_definition(self, auto_schema):
        return _bearer_jwt()
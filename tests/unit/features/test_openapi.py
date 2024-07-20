from __future__ import annotations

from typing import TYPE_CHECKING

import msgspec
import pytest
from starlette.responses import JSONResponse, Response

from asgiext.features.app_features.starlette import StarletteFeature
from asgiext.features.openapi import OpenAPIConfig, OpenAPIFeature
from asgiext.testing.helpers import app_lifespan_manager, create_http_client

if TYPE_CHECKING:
    from starlette.requests import Request

    from asgiext.features.core.asgi_web_server import ASGIWebServerFeature

pytestmark = pytest.mark.anyio


async def test_get_spec_dict_single_route_docstring(asgi_web_server_feature: ASGIWebServerFeature):
    starlette_feature = StarletteFeature()
    openapi_feature = OpenAPIFeature(config=OpenAPIConfig())
    features = [
        starlette_feature,
        asgi_web_server_feature,
        openapi_feature,
    ]
    async with app_lifespan_manager(features, starlette_feature) as app:

        async def get_empty_array(request: Request) -> Response:  # noqa: ARG001
            """Get empty array.
            ---
            get:
              tags:
                - array
              summary: API for get empty array
              responses:
                "200":
                  description: Empty array
                  schema:
                    type: array
                "500":
                  description: Internal server error.
            """
            return JSONResponse("[]")

        app.add_route("/empty_array", get_empty_array)
        expected_spec = {
            "paths": {
                "/empty_array": {
                    "get": {
                        "tags": ["array"],
                        "summary": "API for get empty array",
                        "responses": {
                            "200": {"description": "Empty array", "schema": {"type": "array"}},
                            "500": {"description": "Internal server error."},
                        },
                    }
                }
            },
            "info": {"title": "asgiext", "version": "1.0.0"},
            "swagger": "2.0",
        }
        assert openapi_feature.get_spec_dict(regenerate=True) == expected_spec


async def test_get_spec_dict_multiple_routes_docstrings(asgi_web_server_feature: ASGIWebServerFeature):
    starlette_feature = StarletteFeature()
    openapi_feature = OpenAPIFeature(config=OpenAPIConfig())
    features = [starlette_feature, asgi_web_server_feature, openapi_feature]
    async with app_lifespan_manager(features, starlette_feature) as app:

        async def get_empty_array(request: Request) -> Response:  # noqa: ARG001
            """Get empty array.
            ---
            get:
              tags:
                - array
              summary: API for get empty array
              responses:
                "200":
                  description: Empty array
                  schema:
                    type: array
                "500":
                  description: Internal server error.
            """
            return JSONResponse("[]")

        async def get_full_array(request: Request) -> Response:  # noqa: ARG001
            """Get full array.
            ---
            get:
              tags:
                - array
              summary: API for get full array
              responses:
                "200":
                  description: Full array
                  schema:
                    type: array
                "500":
                  description: Internal server error.
            """
            return JSONResponse("[1]")

        app.add_route("/empty_array", get_empty_array)
        app.add_route("/full_array", get_full_array)
        expected_spec = {
            "paths": {
                "/empty_array": {
                    "get": {
                        "tags": ["array"],
                        "summary": "API for get empty array",
                        "responses": {
                            "200": {"description": "Empty array", "schema": {"type": "array"}},
                            "500": {"description": "Internal server error."},
                        },
                    }
                },
                "/full_array": {
                    "get": {
                        "tags": ["array"],
                        "summary": "API for get full array",
                        "responses": {
                            "200": {"description": "Full array", "schema": {"type": "array"}},
                            "500": {"description": "Internal server error."},
                        },
                    }
                },
            },
            "info": {"title": "asgiext", "version": "1.0.0"},
            "swagger": "2.0",
        }
        assert openapi_feature.get_spec_dict(regenerate=True) == expected_spec


async def test_get_spec_dict_empty(asgi_web_server_feature: ASGIWebServerFeature):
    starlette_feature = StarletteFeature()
    openapi_feature = OpenAPIFeature(config=OpenAPIConfig())
    features = [starlette_feature, asgi_web_server_feature, openapi_feature]
    async with app_lifespan_manager(features, starlette_feature):
        expected_spec = {"paths": {}, "info": {"title": "asgiext", "version": "1.0.0"}, "swagger": "2.0"}
        assert openapi_feature.get_spec_dict(regenerate=True) == expected_spec


async def test_get_spec_dict_multiple_http_methods_route_docstring(asgi_web_server_feature: ASGIWebServerFeature):
    starlette_feature = StarletteFeature()
    openapi_feature = OpenAPIFeature(config=OpenAPIConfig())
    features = [starlette_feature, asgi_web_server_feature, openapi_feature]
    async with app_lifespan_manager(features, starlette_feature) as app:

        async def get_integer_value(request: Request) -> Response:  # noqa: ARG001
            """Get integer array.
            ---
            get:
              tags:
                - array
              summary: API for get integer array
              responses:
                "200":
                  description: Integer value
                  type: integer
                "500":
                  description: Internal server error.
            post:
              tags:
                - array
              summary: API for get integer array
              responses:
                "200":
                  description: Integer value
                  type: integer
                "500":
                  description: Internal server error.
            """
            return JSONResponse("1")

        app.add_route("/integer_value", get_integer_value, methods=["GET", "POST"])
        expected_spec = {
            "paths": {
                "/integer_value": {
                    "get": {
                        "tags": ["array"],
                        "summary": "API for get integer array",
                        "responses": {
                            "200": {"description": "Integer value", "type": "integer"},
                            "500": {"description": "Internal server error."},
                        },
                    },
                    "post": {
                        "tags": ["array"],
                        "summary": "API for get integer array",
                        "responses": {
                            "200": {"description": "Integer value", "type": "integer"},
                            "500": {"description": "Internal server error."},
                        },
                    },
                }
            },
            "info": {"title": "asgiext", "version": "1.0.0"},
            "swagger": "2.0",
        }
        assert openapi_feature.get_spec_dict(regenerate=True) == expected_spec


async def test_http_openapi_spec(asgi_web_server_feature: ASGIWebServerFeature):
    starlette_feature = StarletteFeature()
    openapi_feature = OpenAPIFeature(config=OpenAPIConfig())
    features = [starlette_feature, asgi_web_server_feature, openapi_feature]
    async with (
        app_lifespan_manager(features, starlette_feature) as app,
        create_http_client(app) as test_client,
    ):
        expected_spec = {"paths": {}, "info": {"title": "asgiext", "version": "1.0.0"}, "swagger": "2.0"}
        response = await test_client.get(f"http://localhost{openapi_feature.config.openapi_path}")
        assert response.status_code == 200
        actual_spec = msgspec.json.decode(await response.aread())
        assert actual_spec == expected_spec

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Literal

import msgspec
import pytest
from starlette.responses import JSONResponse, PlainTextResponse, Response

from asgiext.features.app_features.starlette import StarletteFeature
from asgiext.features.request_id import RequestIDConfig, RequestIDFeature
from asgiext.testing.helpers import app_lifespan_manager, create_http_client

if TYPE_CHECKING:
    from starlette.requests import Request

    from asgiext.features.core.asgi_web_server import ASGIWebServerFeature

pytestmark = pytest.mark.anyio


class TestRequestIDFeature:
    def test_fields(self):
        assert RequestIDFeature.name == "REQUEST_ID"
        assert RequestIDFeature.config_cls() is RequestIDConfig  # type: ignore

    @pytest.mark.parametrize("http_header_name", ["X-Request-ID", "Request-ID"])
    async def test_get_current_id_if_exists_and_set_to_http_response(
        self, asgi_web_server_feature: ASGIWebServerFeature, http_header_name: Literal["X-Request-ID", "Request-ID"]
    ):
        starlette_feature = StarletteFeature()
        request_id_feature = RequestIDFeature(config=RequestIDConfig(http_header_name=http_header_name))
        features = [starlette_feature, asgi_web_server_feature, request_id_feature]
        async with (
            app_lifespan_manager(features, starlette_feature) as app,
            create_http_client(app) as test_client,
        ):

            async def get_request_id_entrypoint(request: Request) -> Response:  # noqa: ARG001
                return PlainTextResponse(request_id_feature.get_current_id())

            app.add_route("/get_request_id_entrypoint", get_request_id_entrypoint)

            response = await test_client.get("http://localhost/get_request_id_entrypoint")
            response_data = (await response.aread()).decode()
            uuid.UUID(response_data)  # check that request id is valid uuid 4
            assert response.headers[http_header_name] == response_data

    async def test_get_current_id_if_exists_and_set_to_http_response_false(
        self, asgi_web_server_feature: ASGIWebServerFeature
    ):
        starlette_feature = StarletteFeature()
        request_id_feature = RequestIDFeature(config=RequestIDConfig(set_to_http_response=False))
        features = [starlette_feature, asgi_web_server_feature, request_id_feature]
        async with (
            app_lifespan_manager(features, starlette_feature) as app,
            create_http_client(app) as test_client,
        ):

            async def get_request_id_entrypoint(request: Request) -> Response:  # noqa: ARG001
                return PlainTextResponse(request_id_feature.get_current_id())

            app.add_route("/get_request_id_entrypoint", get_request_id_entrypoint)

            response = await test_client.get("http://localhost/get_request_id_entrypoint")
            uuid.UUID((await response.aread()).decode())  # check that request id is valid uuid 4
            assert "X-Request-ID" not in response.headers

    async def test_get_empty_initialized_context(self, asgi_web_server_feature: ASGIWebServerFeature):
        """Testing that either request has empty context"""
        starlette_feature = StarletteFeature()
        request_id_feature = RequestIDFeature()
        features = [starlette_feature, asgi_web_server_feature, request_id_feature]

        async with (
            app_lifespan_manager(features, starlette_feature) as app,
            create_http_client(app) as test_client,
        ):

            async def get_current_request_context(request: Request) -> JSONResponse:  # noqa: ARG001
                return JSONResponse(request_id_feature.get_current_request_context())

            app.add_route("/get_current_request_context", get_current_request_context)

            response = await test_client.get("http://localhost/get_current_request_context")

            current_request_context = msgspec.json.decode(await response.aread())

            assert current_request_context == {}

    async def test_update_request_context(self, asgi_web_server_feature: ASGIWebServerFeature):
        """Testing context update"""
        starlette_feature = StarletteFeature()
        request_id_feature = RequestIDFeature()
        features = [starlette_feature, asgi_web_server_feature, request_id_feature]

        async with (
            app_lifespan_manager(features, starlette_feature) as app,
            create_http_client(app) as test_client,
        ):

            async def update_current_request_context(request: Request):  # noqa: ARG001
                request_id_feature.update_current_request_context({"test": "test"})
                return JSONResponse(request_id_feature.get_current_request_context())

            app.add_route("/update_current_request_context", update_current_request_context)

            response = await test_client.get("http://localhost/update_current_request_context")

            request_context = msgspec.json.decode((await response.aread()).decode())

            assert request_context == {"test": "test"}

    async def test_clear_request_context_after_response(self, asgi_web_server_feature: ASGIWebServerFeature):
        """Test that context was cleared after response"""
        starlette_feature = StarletteFeature()
        request_id_feature = RequestIDFeature()
        features = [starlette_feature, asgi_web_server_feature, request_id_feature]

        async with (
            app_lifespan_manager(features, starlette_feature) as app,
            create_http_client(app) as test_client,
        ):
            current_id: str = ""

            async def update_current_request_context(request: Request):  # noqa: ARG001
                nonlocal current_id
                current_id = request_id_feature.get_current_id()
                request_id_feature.update_current_request_context({"test": "test"})
                return PlainTextResponse(current_id)

            app.add_route("/update_current_request_context", update_current_request_context)

            await test_client.get("http://localhost/update_current_request_context")

            assert current_id != ""
            assert request_id_feature.get_request_context(current_id, error_if_not_exists=False) is None

    async def test_different_request_have_different_ids(self, asgi_web_server_feature: ASGIWebServerFeature):
        """Test multiple ids respectivly multiple requests"""

        starlette_feature = StarletteFeature()
        request_id_feature = RequestIDFeature()
        features = [starlette_feature, asgi_web_server_feature, request_id_feature]

        async with (
            app_lifespan_manager(features, starlette_feature) as app,
            create_http_client(app) as test_client,
        ):

            async def get_request_id_entrypoint(request: Request):  # noqa: ARG001
                return PlainTextResponse(request_id_feature.get_current_id())

            app.add_route("/get_request_id_entrypoint", get_request_id_entrypoint)

            response1 = await test_client.get("http://localhost/get_request_id_entrypoint")
            response2 = await test_client.get("http://localhost/get_request_id_entrypoint")
            response_data1 = await response1.aread()
            response_data2 = await response2.aread()

            assert response_data1 != response_data2

    async def test_different_requests_have_different_contexts(self, asgi_web_server_feature: ASGIWebServerFeature):
        """Test multiple contexts respectively for multiple requests"""
        starlette_feature = StarletteFeature()
        request_id_feature = RequestIDFeature()
        features = [starlette_feature, asgi_web_server_feature, request_id_feature]

        async with (
            app_lifespan_manager(features, starlette_feature) as app,
            create_http_client(app) as test_client,
        ):

            async def get_updated_request_context(request: Request):  # noqa: ARG001
                current_id = request_id_feature.get_current_id()
                request_id_feature.update_current_request_context({current_id: current_id})
                return JSONResponse(request_id_feature.get_current_request_context())

            app.add_route("/get_current_request_context", get_updated_request_context)

            response1 = await test_client.get("http://localhost/get_current_request_context")
            response2 = await test_client.get("http://localhost/get_current_request_context")
            request_context1 = msgspec.json.decode(await response1.aread())
            request_context2 = msgspec.json.decode(await response2.aread())

            assert request_context1 != request_context2

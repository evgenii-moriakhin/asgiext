from __future__ import annotations

from typing import TYPE_CHECKING

import msgspec
import pytest
from starlette.responses import Response

from asgiext.features.app_features.starlette import StarletteFeature
from asgiext.features.sessions import SessionsConfig, SessionsFeature
from asgiext.testing.helpers import app_lifespan_manager, create_http_client

if TYPE_CHECKING:
    from starlette.requests import Request

    from asgiext.features.core.asgi_web_server import ASGIWebServerFeature

pytestmark = pytest.mark.anyio


class TestSessionsFeature:
    async def test_set_and_get_session(self, asgi_web_server_feature: ASGIWebServerFeature):
        """Test that the session is set in the cookie on the first request,
        and the session remains the same on re-requests
        """
        starlette_feature = StarletteFeature()
        sessions_feature = SessionsFeature(config=SessionsConfig())
        features = [starlette_feature, asgi_web_server_feature, sessions_feature]
        async with app_lifespan_manager(features, starlette_feature) as app:

            async def get_current_session(request: Request):  # noqa: ARG001
                return Response(sessions_feature.get_current_session().to_json(), media_type="application/json")

            app.add_route("/get_current_session", get_current_session)

            async with create_http_client(app) as test_client:
                # cookies on the client are empty until the first request is made
                assert test_client.cookies == {}

                first_response = await test_client.get("http://localhost/get_current_session")
                first_session_data_response = msgspec.json.decode(await first_response.aread())

                # session cookie appeared on the client after the first request
                assert "session_id" in test_client.cookies

                # .get_current_session() method (from entrypoint) returned us a session
                # with the same id as saved on the client
                assert first_session_data_response["_session_id"] == test_client.cookies["session_id"]
                first_session_client_cookie = test_client.cookies["session_id"]

                # when re-requesting, the session remains the same in the client's
                # cookies and obtained programmatically from the entrypoint
                second_response = await test_client.get("http://localhost/get_current_session")
                second_session_data_response = msgspec.json.decode(await second_response.aread())
                second_session_client_cookie = test_client.cookies["session_id"]

                assert first_session_data_response == second_session_data_response
                assert first_session_client_cookie == second_session_client_cookie

    async def test_multiple_clients_have_different_sessions(self, asgi_web_server_feature: ASGIWebServerFeature):
        starlette_feature = StarletteFeature()
        sessions_feature = SessionsFeature(config=SessionsConfig())
        features = [starlette_feature, asgi_web_server_feature, sessions_feature]
        async with app_lifespan_manager(features, starlette_feature) as app:

            async def get_current_session(request: Request):  # noqa: ARG001
                return Response(sessions_feature.get_current_session().to_json(), media_type="application/json")

            app.add_route("/get_current_session", get_current_session)

            async with (
                create_http_client(app) as test_client1,
                create_http_client(app) as test_client2,
            ):
                test_client1_response = await test_client1.get("http://localhost/get_current_session")
                session1_data = msgspec.json.decode(await test_client1_response.aread())
                test_client2_response = await test_client2.get("http://localhost/get_current_session")
                session2_data = msgspec.json.decode(await test_client2_response.aread())

                assert session1_data["_session_id"] != session2_data["_session_id"]

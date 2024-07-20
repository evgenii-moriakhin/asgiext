# noqa: INP001
from typing import cast

from quart import current_app
from starlette.requests import Request
from starlette.responses import Response

from asgiext import init_app_and_get_runner
from asgiext.features.app_features.starlette import StarletteFeature
from asgiext.features.core import FeatureStore
from asgiext.features.core.asgi_web_server import ASGIWebServerFeature
from asgiext.features.logging_requests import LoggingRequestsFeature
from asgiext.features.request_id import RequestIDFeature

starlete_feature = StarletteFeature()
features = [starlete_feature, ASGIWebServerFeature(), RequestIDFeature(), LoggingRequestsFeature()]

runner = init_app_and_get_runner(features, starlete_feature)
app = starlete_feature.app

def some_entrypoint(request: Request) -> Response:  # noqa: ARG001
    ft_store = cast(FeatureStore, current_app.ft_store)  # type: ignore
    ft_store.logging.get_logger().info(
        f"Some request with request_id={ft_store.get(RequestIDFeature).get_current_id()}"
    )
    return Response("success")

app.add_route("/", some_entrypoint)

if __name__ == "__main__":
    runner()

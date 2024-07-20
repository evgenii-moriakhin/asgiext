# noqa: INP001
from starlette.requests import Request
from starlette.responses import Response

from asgiext import init_app_and_get_runner
from asgiext.features.app_features.starlette import StarletteFeature
from asgiext.features.core.asgi_web_server import ASGIWebServerFeature

starlette_feature = StarletteFeature()
features = [
    starlette_feature,
    ASGIWebServerFeature(),
]

runner = init_app_and_get_runner(features, starlette_feature) # type: ignore
app = starlette_feature.app

async def hello_world(request: Request) -> Response:  # noqa: ARG001
    return Response("Hello World")

app.add_route("/", hello_world)

if __name__ == "__main__":
    runner()

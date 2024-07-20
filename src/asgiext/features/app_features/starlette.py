from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.routing import BaseRoute, Mount, Route

from asgiext.features.core import AppFeature, FeatureConfig

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Generator, Iterable, Sequence

    from starlette.requests import Request
    from starlette.responses import Response


class RequestHooksMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Starlette, feature: StarletteFeature) -> None:
        super().__init__(app)
        self.feature = feature

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        for func in self.feature.before_request_funcs:
            await func(request)
        response = await call_next(request)
        for func in self.feature.after_request_funcs:
            response = await func(request, response) or response

        return response


class StarletteFeatureConfig(FeatureConfig):
    """StarletteFeatureConfig."""


class StarletteFeature(AppFeature[StarletteFeatureConfig, Starlette]):  # type: ignore
    name = "STARLETTE"

    app: Starlette

    before_request_funcs: list[Callable[[Request], Awaitable[None]]]
    after_request_funcs: list[Callable[[Request, Response], Awaitable[Response]]]

    def __init__(self, name: str | None = None, *, config: StarletteFeatureConfig | None = None) -> None:
        super().__init__(name, config=config)
        self.before_request_funcs = []
        self.after_request_funcs = []

    @classmethod
    def _infer_http_routes(
        cls, routes: Sequence[BaseRoute] | None = None
    ) -> Generator[tuple[str, Callable[..., Any]], Any, None]:
        for route in routes or []:
            if isinstance(route, Route):
                yield route.path, route.endpoint
            elif isinstance(route, Mount) and route.routes:
                yield from cls._infer_http_routes(route.routes)

    def get_http_routes(self) -> Iterable[tuple[str, Callable[..., Any]]]:
        return self._infer_http_routes(self.app.routes)

    def init(self) -> None:
        self.app = Starlette(
            lifespan=asynccontextmanager(self.features_lifespan),
        )
        self.app.add_middleware(RequestHooksMiddleware, feature=self)  # type: ignore
        self.app.state.ft_store = self.ft_store

    async def on_startup(self) -> None:
        pass

    async def on_shutdown(self) -> None:
        pass

    def before_request(self, func: Callable[[Request], Awaitable[None]]) -> None:
        self.before_request_funcs.append(func)

    def after_request(self, func: Callable[[Request, Response], Awaitable[Response]]) -> None:
        self.after_request_funcs.append(func)

from __future__ import annotations

from typing import TYPE_CHECKING

from asgiext.features.app_features.quart import QuartFeature
from asgiext.features.app_features.starlette import StarletteFeature
from asgiext.features.core import AbstractApplicationFeature, FeatureConfig

if TYPE_CHECKING:
    from logging import Logger


class LoggingRequestsConfig(FeatureConfig):
    """LoggingRequestsConfig."""

    log_msg: str = "HTTP Request"


class LoggingRequestsFeature(AbstractApplicationFeature[LoggingRequestsConfig]):
    """LoggingRequestsFeature."""

    name = "LOGGING_REQUESTS"
    access_logger: Logger

    def init(self) -> None:
        """Init."""
        ft_store = self.ft_store
        self.access_logger = ft_store.logging.get_logger("asgiext.accesslog")
        self._setup_logging_requests_for_asgi_framework()

    def _setup_logging_requests_for_asgi_framework(self) -> None:
        app_feature = self.ft_store.app_feature
        if isinstance(app_feature, QuartFeature):
            self._setup_logging_requests_for_quart(app_feature)
        if isinstance(app_feature, StarletteFeature):
            self._setup_logging_requests_for_starlette(app_feature)
        else:
            msg = f"ASGI framework {type(app_feature.app)} not supported for {self!r}"
            raise TypeError(msg)

    def _setup_logging_requests_for_quart(self, app_feature: QuartFeature) -> None:
        from quart import Response, request

        app = app_feature.app

        async def process_http_response(response: Response) -> Response:
            log_data = {
                "client_ip": request.remote_addr or "-",
                "user_agent": request.headers.get("User-Agent", "-"),
                "request_line": f"{request.method} {request.path}",
                "status_code": response.status_code,
                "http_referer": request.headers.get("Referer", "-"),
            }
            self.access_logger.info(self.config.log_msg, extra=log_data)
            return response

        app.after_request(process_http_response)

    def _setup_logging_requests_for_starlette(self, app_feature: StarletteFeature) -> None:
        from starlette.requests import Request  # noqa: TCH002
        from starlette.responses import Response  # noqa: TCH002

        async def process_http_response(request: Request, response: Response) -> Response:
            log_data = {
                "client_ip": request.client.host if request.client else "-",
                "user_agent": request.headers.get("User-Agent", "-"),
                "request_line": f"{request.method} {request.url.path}",
                "status_code": response.status_code,
                "http_referer": request.headers.get("Referer", "-"),
            }
            self.access_logger.info(self.config.log_msg, extra=log_data)
            return response

        app_feature.after_request(process_http_response)

    async def on_startup(self) -> None:
        """On startup."""

    async def on_shutdown(self) -> None:
        """On shutdown."""

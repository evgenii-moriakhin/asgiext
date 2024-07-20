from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Any, Literal, Optional, overload

from asgiext.features.app_features.quart import QuartFeature
from asgiext.features.app_features.starlette import StarletteFeature
from asgiext.features.core import AbstractApplicationFeature, FeatureConfig
from asgiext.features.request_id import RequestIDFeature

correlation_id: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


class CorrelationIDConfig(FeatureConfig):
    """CorrelationIDConfig."""

    set_on_http_request: bool = True
    set_from_http_request_id: bool = True
    http_header_name: str = "X-Correlation-ID"
    accept_external_http_header: bool = False

    def model_post_init(self, __context: Any) -> None:  # noqa: ANN401
        if self.set_from_http_request_id and not self.set_on_http_request:
            msg = (
                f"Configuration field {self.set_from_http_request_id=} "
                f"doesn't make sense if {self.set_on_http_request=}"
            )
            raise ValueError(msg)
        if self.accept_external_http_header and not self.set_on_http_request:
            msg = (
                f"Configuration field {self.accept_external_http_header=} "
                f"doesn't make sense if {self.set_on_http_request=}"
            )
            raise ValueError(msg)


class CorrelationIDFeature(AbstractApplicationFeature[CorrelationIDConfig]):
    """CorrelationIDFeature."""

    name = "CORRELATION_ID"

    ####################
    # FOR PUBLIC USAGE #
    ####################

    @overload
    def get_current_id(self, *, error_if_not_exists: Literal[True] = True) -> str: ...

    @overload
    def get_current_id(self, *, error_if_not_exists: Literal[False] = False) -> Optional[str]: ...

    def get_current_id(self, *, error_if_not_exists: bool = True) -> Optional[str]:
        current_id = self.correlation_id.get()
        if current_id is None and error_if_not_exists:
            msg = "No current correlation id has been set"
            raise ValueError(msg)
        return current_id

    def set_correlation_id(self, correlation_id: str | None = None) -> str:
        correlation_id = correlation_id or str(uuid.uuid4())
        self.correlation_id.set(correlation_id)
        return correlation_id

    ####################
    # NON-PUBLIC USAGE #
    ####################

    def init(self) -> None:
        self.correlation_id = correlation_id
        self._setup_correlation_id_for_asgi_framework()

    def _setup_correlation_id_for_asgi_framework(self) -> None:
        app_feature = self.ft_store.app_feature
        if isinstance(app_feature, QuartFeature):
            self._setup_correlation_id_for_quart(app_feature)
        if isinstance(app_feature, StarletteFeature):
            self._setup_correlation_id_for_starlette(app_feature)
        else:
            msg = f"ASGI framework {type(app_feature.app)} not supported for {self!r}"
            raise TypeError(msg)

    def _setup_correlation_id_for_quart(self, app_feature: QuartFeature) -> None:
        from quart import request

        app = app_feature.app

        async def process_http_request() -> None:
            if self.config.http_header_name in request.headers and self.config.accept_external_http_header:
                self.set_correlation_id(request.headers[self.config.http_header_name])
            elif self.config.set_from_http_request_id:
                self.set_correlation_id(self.ft_store.get(RequestIDFeature).get_current_id())
            else:
                self.set_correlation_id()

        if self.config.set_on_http_request:
            app.before_request(process_http_request)

    def _setup_correlation_id_for_starlette(self, app_feature: StarletteFeature) -> None:
        from starlette.requests import Request  # noqa: TCH002

        async def process_http_request(request: Request) -> None:
            if self.config.http_header_name in request.headers and self.config.accept_external_http_header:
                self.set_correlation_id(request.headers[self.config.http_header_name])
            elif self.config.set_from_http_request_id:
                self.set_correlation_id(self.ft_store.get(RequestIDFeature).get_current_id())
            else:
                self.set_correlation_id()

        if self.config.set_on_http_request:
            app_feature.before_request(process_http_request)

    async def on_startup(self) -> None:
        """On startup."""

    async def on_shutdown(self) -> None:
        """On shutdown."""

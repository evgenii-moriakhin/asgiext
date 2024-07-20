from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Any, Literal, Optional, overload

from asgiext.features.app_features.quart import QuartFeature
from asgiext.features.app_features.starlette import StarletteFeature
from asgiext.features.core import AbstractApplicationFeature, FeatureConfig
from asgiext.utils.datastructures import deep_update

request_id: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


class RequestIDConfig(FeatureConfig):
    """RequestIDConfig."""

    set_on_http_request: bool = True
    accept_external_request_header: bool = False
    set_to_http_response: bool = True
    http_header_name: str = "X-Request-ID"

    add_log_context: bool = True
    log_context_name: str = "request_id"

    def model_post_init(self, __context: Any) -> None:  # noqa: ANN401
        if self.set_to_http_response and not self.set_on_http_request:
            msg = (
                f"Configuration field {self.set_to_http_response=} "
                f"doesn't make sense if {self.set_on_http_request=}"
            )
            raise ValueError(msg)
        if self.accept_external_request_header and not self.set_on_http_request:
            msg = (
                f"Configuration field {self.accept_external_request_header=} "
                f"doesn't make sense if {self.set_on_http_request=}"
            )
            raise ValueError(msg)


class RequestIDFeature(AbstractApplicationFeature[RequestIDConfig]):
    """The HTTP X-Request-ID request header is an optional and unofficial HTTP header,
    used to trace individual HTTP requests.
    The feature also provides a context for each request to store the request data.

    It is also possible to use request identifier and context not only for HTTP requests,
    but for any incoming interactions. To do this manually use setting and clearing of id and context
    """

    name = "REQUEST_ID"

    _request_context_store: dict[str, dict[str, Any]]

    ####################
    # FOR PUBLIC USAGE #
    ####################

    def set_request_id_and_context(self, request_id: str | None = None) -> None:
        self._set_request_id(request_id)
        self._set_request_context(self.get_current_id(), {})

    @overload
    def get_current_id(self, *, error_if_not_exists: Literal[True] = True) -> str: ...

    @overload
    def get_current_id(self, *, error_if_not_exists: Literal[False] = False) -> Optional[str]: ...

    @overload
    def get_current_id(self, *, error_if_not_exists: bool = True) -> Optional[str]: ...

    def get_current_id(self, *, error_if_not_exists: bool = True) -> Optional[str]:
        current_id = self.request_id.get()
        if current_id is None and error_if_not_exists:
            msg = "No current request id has been set"
            raise ValueError(msg)
        return current_id

    @overload
    def get_request_context(self, request_id: str, *, error_if_not_exists: Literal[True] = True) -> dict[str, Any]: ...

    @overload
    def get_request_context(
        self, request_id: str, *, error_if_not_exists: Literal[False] = False
    ) -> dict[str, Any] | None: ...

    @overload
    def get_request_context(self, request_id: str, *, error_if_not_exists: bool = True) -> dict[str, Any] | None: ...

    def get_request_context(self, request_id: str, *, error_if_not_exists: bool = True) -> dict[str, Any] | None:
        request_context = self._request_context_store.get(request_id)
        if request_context is None and error_if_not_exists:
            msg = f"No request context set under the given {request_id=}"
            raise ValueError(msg)
        return request_context

    @overload
    def get_current_request_context(self, *, error_if_not_exists: Literal[True] = True) -> dict[str, Any]: ...

    @overload
    def get_current_request_context(self, *, error_if_not_exists: Literal[False] = False) -> dict[str, Any] | None: ...

    @overload
    def get_current_request_context(self, *, error_if_not_exists: bool = True) -> dict[str, Any] | None: ...

    def get_current_request_context(self, *, error_if_not_exists: bool = True) -> dict[str, Any] | None:
        current_request_id = self.get_current_id(error_if_not_exists=error_if_not_exists)

        if current_request_id:
            # request context always presents if request_id exists
            return self.get_request_context(request_id=current_request_id)

        return None

    def update_current_request_context(
        self,
        data: dict[str, Any],
        *,
        error_if_not_exists: bool = True,
        use_deep_update: bool = False,
    ) -> None:
        request_id = self.get_current_id(error_if_not_exists=error_if_not_exists)
        if not request_id:
            return
        self.update_request_context(
            request_id=request_id, data=data, error_if_not_exists=error_if_not_exists, use_deep_update=use_deep_update
        )

    def update_request_context(
        self,
        request_id: str,
        data: dict[str, Any],
        *,
        error_if_not_exists: bool = True,
        use_deep_update: bool = False,
    ) -> None:
        # Updating the context is not thread-safe. If thread-safety is ever needed,
        # it will probably be necessary to make async def update_request_context_treadsafe(...)
        # with such async lock:
        # https://stackoverflow.com/questions/63420413/how-to-use-threading-lock-in-async-function-while-object-can-be-accessed-from-mu
        # with the ability to use this function non-blocking even in cases when an application has several
        # event loops in different threads
        request_context = self.get_request_context(request_id, error_if_not_exists=error_if_not_exists) or {}
        if use_deep_update:
            request_context = deep_update(request_context, data)
        else:
            request_context.update(**data)
        self._set_request_context(request_id, request_context)

    ####################
    # NON-PUBLIC USAGE #
    ####################

    def init(self) -> None:
        ft_store = self.ft_store
        self.request_id = request_id
        self._request_context_store = {}
        self.logging_feature = ft_store.logging
        self._setup_request_id_for_asgi_framework()

    def _set_request_context(self, request_id: str, data: dict[str, Any]) -> None:
        self._request_context_store[request_id] = data

    def _setup_request_id_for_asgi_framework(self) -> None:
        app_feature = self.ft_store.app_feature
        if isinstance(app_feature, QuartFeature):
            self._setup_request_id_for_quart(app_feature)
        if isinstance(app_feature, StarletteFeature):
            self._setup_request_id_for_starlette(app_feature)
        else:
            msg = f"ASGI framework {type(app_feature.app)} not supported for {self!r}"
            raise TypeError(msg)

    def _setup_request_id_for_quart(self, app_feature: QuartFeature) -> None:
        from quart import Response, request

        app = app_feature.app

        async def set_request_id_before_http_request_quart() -> None:
            if self.config.accept_external_request_header:
                self.set_request_id_and_context(request_id=request.headers.get(self.config.http_header_name))
            else:
                self.set_request_id_and_context()

        async def clear_request_context_after_http_request_quart(response: Response) -> Response:
            self.clear_request_context()
            return response

        async def set_request_id_to_http_response_quart(response: Response) -> Response:
            response.headers.add(self.config.http_header_name, self.get_current_id())  # type: ignore
            return response

        if self.config.set_on_http_request:
            app.before_request(set_request_id_before_http_request_quart)
            app.after_request(clear_request_context_after_http_request_quart)
        if self.config.set_to_http_response:
            app.after_request(set_request_id_to_http_response_quart)

    def _setup_request_id_for_starlette(self, app_feature: StarletteFeature) -> None:
        from starlette.requests import Request  # noqa: TCH002
        from starlette.responses import Response  # noqa: TCH002

        async def set_request_id_before_http_request_quart(request: Request) -> None:
            if self.config.accept_external_request_header:
                self.set_request_id_and_context(request_id=request.headers.get(self.config.http_header_name))
            else:
                self.set_request_id_and_context()

        async def clear_request_context_after_http_request_quart(request: Request, response: Response) -> Response:  # noqa: ARG001
            self.clear_request_context()
            return response

        async def set_request_id_to_http_response_quart(request: Request, response: Response) -> Response:  # noqa: ARG001
            response.headers[self.config.http_header_name] = self.get_current_id()
            return response

        if self.config.set_on_http_request:
            app_feature.before_request(set_request_id_before_http_request_quart)
            app_feature.after_request(clear_request_context_after_http_request_quart)
        if self.config.set_to_http_response:
            app_feature.after_request(set_request_id_to_http_response_quart)

    def clear_request_context(self) -> None:
        request_id = self.get_current_id()
        self._request_context_store.pop(request_id, None)

    def _set_request_id(self, request_id: str | None = None) -> str:
        request_id = request_id or str(uuid.uuid4())
        self.request_id.set(request_id)
        if self.config.add_log_context:
            self.logging_feature.set_log_context(self.config.log_context_name, request_id)
        return request_id

    async def on_startup(self) -> None:
        """On startup."""

    async def on_shutdown(self) -> None:
        """On shutdown."""

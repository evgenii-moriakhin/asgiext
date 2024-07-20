from __future__ import annotations

import secrets
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional, cast, overload

import msgspec

from asgiext.features.app_features.quart import QuartFeature
from asgiext.features.app_features.starlette import StarletteFeature
from asgiext.features.core import AbstractApplicationFeature, FeatureConfig
from asgiext.features.stores.memory import MemoryStore
from asgiext.features.stores_registry import StoresRegistryFeature

ONE_DAY_IN_SECONDS = 60 * 60 * 24

session_context: ContextVar[Optional[ServerSideSession]] = ContextVar("session_context", default=None)


class SessionsConfig(FeatureConfig):
    """SessionsConfig."""

    cookie_name: str = "session_id"
    cookie_domain: Optional[str] = None
    cookie_path: str = "/"
    cookie_http_only: bool = True
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cookie_max_age: int = ONE_DAY_IN_SECONDS * 14  # if 0 - permanent cookies

    stores_registry_feature_name: str = "STORES_REGISTRY"
    sessions_store_name: Optional[str] = None


class SessionsFeature(AbstractApplicationFeature[SessionsConfig]):
    """SessionsFeature."""

    name = "SESSIONS"

    ####################
    # FOR PUBLIC USAGE #
    ####################

    @overload
    def get_current_session(self, *, error_if_not_exists: Literal[True] = True) -> ServerSideSession: ...

    @overload
    def get_current_session(self, *, error_if_not_exists: Literal[False] = False) -> Optional[ServerSideSession]: ...

    @overload
    def get_current_session(self, *, error_if_not_exists: bool = True) -> Optional[ServerSideSession]: ...

    def get_current_session(self, *, error_if_not_exists: bool = True) -> Optional[ServerSideSession]:
        session = self._session_context.get()
        if session is None and error_if_not_exists:
            msg = "No current session has been set"
            raise ValueError(msg)
        return session

    ####################
    # NON-PUBLIC USAGE #
    ####################

    def init(self) -> None:
        """Init."""
        if self.config.sessions_store_name:
            stores_registry_feature = self.ft_store.get(
                self.config.stores_registry_feature_name, validate_type=StoresRegistryFeature
            )
            self.store = stores_registry_feature.get_store(self.config.sessions_store_name)
        else:
            self.store = MemoryStore()
        self._setup_sessions_for_asgi_framework()
        self._session_context = session_context

    def _setup_sessions_for_asgi_framework(self) -> None:
        app_feature = self.ft_store.app_feature
        if isinstance(app_feature, QuartFeature):
            self._setup_sessions_for_quart(app_feature)
        if isinstance(app_feature, StarletteFeature):
            self._setup_sessions_for_starlette(app_feature)
        else:
            msg = f"ASGI framework {type(app_feature.app)} not supported for {self!r}"
            raise TypeError(msg)

    def _setup_sessions_for_quart(self, app_feature: QuartFeature) -> None:
        from quart import Response, request

        app = app_feature.app

        async def open_session_before_request() -> None:
            await self._open_session(request.cookies.get(self.config.cookie_name))

        app.before_request(open_session_before_request)

        async def save_session_after_request(response: Response) -> Response:
            session = self.get_current_session()
            if session.is_cleared:
                await self.store.delete(session.session_id)
                response.delete_cookie(
                    self.config.cookie_name,
                    domain=self.config.cookie_domain,
                    path=self.config.cookie_path,
                    secure=self.config.cookie_secure,
                    samesite=self.config.cookie_samesite,
                    httponly=self.config.cookie_http_only,
                )
                return response

            serialised_session_data = session.to_json()
            await self.store.set(
                key=session.session_id,
                value=serialised_session_data,
                expires_in=session.expires - datetime.now(tz=timezone.utc),
            )

            response.set_cookie(
                self.config.cookie_name,
                session.session_id,
                expires=session.expires,
                domain=self.config.cookie_domain,
                path=self.config.cookie_path,
                secure=self.config.cookie_secure,
                samesite=self.config.cookie_samesite,
                httponly=self.config.cookie_http_only,
            )
            return response

        app.after_request(save_session_after_request)

    def _setup_sessions_for_starlette(self, app_feature: StarletteFeature) -> None:
        from starlette.requests import Request  # noqa: TCH002
        from starlette.responses import Response  # noqa: TCH002

        async def open_session_before_request(request: Request) -> None:
            await self._open_session(request.cookies.get(self.config.cookie_name))

        app_feature.before_request(open_session_before_request)

        async def save_session_after_request(request: Request, response: Response) -> Response:  # noqa: ARG001
            session = self.get_current_session()
            if session.is_cleared:
                await self.store.delete(session.session_id)
                response.delete_cookie(
                    self.config.cookie_name,
                    domain=self.config.cookie_domain,
                    path=self.config.cookie_path,
                    secure=self.config.cookie_secure,
                    samesite=self.config.cookie_samesite,
                    httponly=self.config.cookie_http_only,
                )
                return response

            serialised_session_data = session.to_json()
            await self.store.set(
                key=session.session_id,
                value=serialised_session_data,
                expires_in=session.expires - datetime.now(tz=timezone.utc),
            )

            response.set_cookie(
                self.config.cookie_name,
                session.session_id,
                expires=session.expires,
                domain=self.config.cookie_domain,
                path=self.config.cookie_path,
                secure=self.config.cookie_secure,
                samesite=self.config.cookie_samesite,
                httponly=self.config.cookie_http_only,
            )
            return response

        app_feature.after_request(save_session_after_request)

    async def _open_session(self, session_id_cookie: str | None) -> None:
        if session_id_cookie:
            data = await self.store.get(session_id_cookie)
            if data is not None:
                session_data = self._deserialize_data(data)
                session = ServerSideSession(session_data)
                if not self.config.cookie_max_age:
                    # if max_age is not set, all sessions will behave as permanent sessions
                    session.expires = datetime.now(tz=timezone.utc) + timedelta(seconds=self.config.cookie_max_age)
                else:
                    # if max_age is set, all existing sessions continue to exist with their set expires
                    # current python version does not support parsing arbitrary ISO 8601 strings
                    # (with timezone in this case)
                    # https://stackoverflow.com/questions/55542280/why-does-python-3-find-this-iso8601-date-2019-04-05t165526z-invalid
                    # so set format explicity
                    session.expires = datetime.strptime(session_data["_expires"], "%Y-%m-%dT%H:%M:%S.%f%z")
                self._session_context.set(session)
                return
        session = ServerSideSession()
        session.session_id = self._generate_session_id()
        session.expires = datetime.now(tz=timezone.utc) + timedelta(seconds=self.config.cookie_max_age)
        self._session_context.set(session)

    @staticmethod
    def _deserialize_data(data: Any) -> dict[str, Any]:  # noqa: ANN401
        return cast("dict[str, Any]", msgspec.json.decode(data))

    def _generate_session_id(self) -> str:
        return secrets.token_hex(32)

    async def on_startup(self) -> None:
        """On startup."""

    async def on_shutdown(self) -> None:
        """On shutdown."""


class ServerSideSession(dict[str, Any]):
    def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        super().__init__(*args, **kwargs)
        self.is_cleared = False

    @property
    def expires(self) -> datetime:
        return cast(datetime, self["_expires"])

    @expires.setter
    def expires(self, value: datetime) -> None:
        self["_expires"] = value

    @property
    def session_id(self) -> str:
        return cast(str, self["_session_id"])

    @session_id.setter
    def session_id(self, value: str) -> None:
        self["_session_id"] = value

    def clear(self) -> None:
        self.is_cleared = True
        session_id = self.session_id
        super().clear()
        # save session_id for further delete from storage
        self.session_id = session_id

    def to_json(self) -> bytes:
        return msgspec.json.encode(self)

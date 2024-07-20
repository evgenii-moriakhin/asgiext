from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, Optional, cast

import msgspec
from flask.json.provider import JSONProvider
from quart import Quart

from asgiext.features.core import AppFeature, FeatureConfig


class JSONProviderMSGSPEC(JSONProvider):
    def dumps(self, obj: Any, **kwargs: Any) -> str:  # noqa: ANN401, ARG002
        """Serialize data as JSON."""
        # NOTE: For compatibility with the parent's typing. Maybe it is not necessary to decode back?
        # See similar case with orjson
        # https://stackoverflow.com/questions/60296197/flask-orjson-instead-of-json-module-for-decoding
        return msgspec.json.encode(obj).decode("utf-8")

    def loads(self, s: str | bytes, **kwargs: Any) -> Any:  # noqa: ANN401, ARG002
        """Deserialize data as JSON."""
        return msgspec.json.decode(s)


class QuartFeatureConfig(FeatureConfig):
    """QuartFeatureConfig."""

    max_content_length: Optional[int] = None
    body_timeout: Optional[int] = None
    json_provider: type[JSONProvider] = JSONProviderMSGSPEC


class QuartFeature(AppFeature[QuartFeatureConfig, Quart]):  # type: ignore
    """QuartFeature."""

    name = "QUART"

    app: Quart

    ####################
    # FOR PUBLIC USAGE #
    ####################

    def get_http_routes(self) -> Iterable[tuple[str, Callable[..., Any]]]:
        routes: list[tuple[str, Callable[..., Any]]] = []
        for rule in self.app.url_map.iter_rules():
            func = cast(Callable[..., Any], self.app.view_functions[rule.endpoint])  # type: ignore
            routes.append((rule.rule, func))
        return routes

    ####################
    # NON-PUBLIC USAGE #
    ####################

    def init(self) -> None:
        """Init."""
        ft_store = self.ft_store

        Quart.json_provider_class = self.config.json_provider
        self.app = Quart(self.name)
        self.app.config["MAX_CONTENT_LENGTH"] = self.config.max_content_length
        self.app.config["BODY_TIMEOUT"] = self.config.body_timeout
        self.app.while_serving(self.features_lifespan)
        self.app.ft_store = ft_store  # type: ignore

    async def on_startup(self) -> None:
        """On startup."""

    async def on_shutdown(self) -> None:
        """On shutdown."""

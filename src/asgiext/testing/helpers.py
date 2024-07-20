from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, TypeVar
from unittest import mock

import httpx

from asgiext import init_app_and_get_runner
from asgiext.testing.contrib.asgi_lifespan import LifespanManager
from asgiext.types.asgi import ASGIFramework

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Sequence

    from asgiext.features.core import AbstractApplicationFeature, AppFeature


_T_asgi_framework = TypeVar("_T_asgi_framework", bound=ASGIFramework)


@asynccontextmanager
async def app_lifespan_manager(
    features: Sequence[AbstractApplicationFeature[Any]],
    app_feature: AppFeature[Any, _T_asgi_framework],
    app_config: str = "",
) -> AsyncGenerator[_T_asgi_framework, None]:
    required_parse_cli_args_feature = False
    for feature in features:
        if not feature.has_init_config():
            required_parse_cli_args_feature = True
            break
    if required_parse_cli_args_feature:
        with (
            mock.patch(
                "sys.argv",
                [
                    "<first_arg>",
                    "--conf",
                    "<it doesn't matter to us>",
                ],
            ),
            mock.patch("pathlib.Path.read_bytes", return_value=app_config.encode()),
        ):
            _ = init_app_and_get_runner(features, app_feature)
    else:
        _ = init_app_and_get_runner(features, app_feature)

    async with LifespanManager(app_feature.app):
        yield app_feature.app


def create_http_client(app: ASGIFramework) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False))  # type: ignore

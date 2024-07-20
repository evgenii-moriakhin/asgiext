from __future__ import annotations

from contextlib import AsyncExitStack
from typing import TYPE_CHECKING, Any, Callable

from asgiext.features.core import AbstractApplicationFeature, AppFeature, FeatureStore
from asgiext.features.core.logging import LoggingFeature
from asgiext.features.core.parse_cli_args import ParseCLIArgsFeature

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Sequence

    from asgiext.types.asgi import ASGIFramework


def create_features_lifespan(ft_store: FeatureStore) -> Callable[..., AsyncGenerator[None, None]]:
    async def features_lifespan(*args: Any, **kwargs: Any) -> AsyncGenerator[None, None]:  # noqa: ANN401, ARG001
        """Управляет жизненным циклом фичей во время работы приложения."""
        async with AsyncExitStack() as async_context:
            features = ft_store.features
            for feature in features:
                try:
                    await async_context.enter_async_context(feature)
                except:  # noqa: PERF203
                    async_context.push_async_exit(feature)
                    raise
            for feature in features:
                if feature.may_start_serving_event:
                    feature.may_start_serving_event.set()
            yield

    return features_lifespan


def init_app_and_get_runner(
    features: Sequence[AbstractApplicationFeature[Any]],
    app_feature: AppFeature[Any, ASGIFramework],  # type: ignore
) -> Callable[..., Any]:
    """Init runner."""
    feature_store = FeatureStore(app_feature)
    required_parse_cli_args_feature = False
    for feature in features:
        if not feature.has_init_config():
            required_parse_cli_args_feature = True
            break
    all_features = [
        LoggingFeature(),
        *features,
    ]
    if required_parse_cli_args_feature:
        all_features = [ParseCLIArgsFeature(), *all_features]
    for feature in all_features:
        feature.set_config(feature_store)
    app_feature.register_features_lifespan(features_lifespan=create_features_lifespan(feature_store))
    for feature in all_features:
        if feature.config.init_override:
            feature.config.init_override(feature)
        else:
            feature.init()
    asgi_web_server_feature = feature_store.asgi_web_server
    return asgi_web_server_feature.get_runner()

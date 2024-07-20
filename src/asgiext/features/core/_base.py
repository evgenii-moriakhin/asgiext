from __future__ import annotations

import importlib.util
import os
import signal
from abc import abstractmethod
from collections.abc import (  # noqa: TCH003 - hush pydantic "is not fully defined" error for FeatureConfig
    AsyncGenerator,
    Awaitable,
    Iterable,
    Sequence,
)
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from typing import TYPE_CHECKING, Any, Callable, ClassVar, Generic, Literal, Optional, TypeVar, overload

import anyio.abc
import pydantic
from anyio import CancelScope
from pydantic import Field
from pydantic_settings import BaseSettings
from typing_extensions import Self, get_args, get_origin, get_original_bases

from asgiext.types.asgi import ASGIFramework

if TYPE_CHECKING:
    from logging import Logger
    from types import TracebackType

    from asgiext.features.core.asgi_web_server import ASGIWebServerFeature
    from asgiext.features.core.logging import LoggingFeature


_T_config = TypeVar("_T_config", bound="FeatureConfig")


class AbstractApplicationFeature(
    AbstractAsyncContextManager,  # type: ignore
    Generic[_T_config],
):
    """AbstractApplicationFeature."""

    name: str

    config: _T_config

    ft_store: FeatureStore

    # The event is required for features that cannot start serve immediately
    # (after calling their on_startup()) until the application is not fully initialized.
    # The application must set that event when it is ready to serve requests.
    may_start_serving_event: anyio.Event | None = None

    task_group: anyio.abc.TaskGroup | None = None
    async_context: AsyncExitStack | None = None
    shield: CancelScope | None

    _logger: Logger

    def __init__(self, name: str | None = None, *, config: _T_config | None = None) -> None:
        """Initialize."""
        self.name = name or self.name
        self._init_config = config

    def has_init_config(self) -> bool:
        return self._init_config is not None

    @abstractmethod
    async def on_startup(self) -> None:
        """On startup."""

    @abstractmethod
    async def on_shutdown(self) -> None:
        """On shutdown."""

    def set_config(self, ft_store: FeatureStore) -> None:
        """Set config."""
        if self._init_config is None:
            from asgiext.features.core.parse_cli_args import ParseCLIArgsFeature

            parse_args_feature = ft_store.get(ParseCLIArgsFeature)
            try:
                feature_config = parse_args_feature.config.features.get(self.name, {})
                if isinstance(feature_config, str):
                    # if config is a string,
                    # it should be the path to the python file (to define configs programmatically, if needed)
                    config_path_parent = parse_args_feature.config_path.parent
                    python_file_feature_config = config_path_parent.joinpath(feature_config)

                    spec = importlib.util.spec_from_file_location("", python_file_feature_config)
                    if spec is None:
                        msg = (
                            f"Error while get module spec for python config file in source {self.__class__.__name__!r}"
                        )
                        raise ValueError(msg)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)  # type: ignore
                    config_variable_name = self.config_cls().get_python_config_variable_name()
                    feature_config_variable = module.__dict__.get(config_variable_name)
                    if not isinstance(feature_config_variable, (dict, self.config_cls())):
                        msg = (
                            f"When programmatically defining the {self!r} feature config, "
                            f"the dict or {self.config_cls().__name__} instance named {config_variable_name!r} "
                            f"must be present in the python config file {python_file_feature_config.absolute()}"
                        )
                        raise TypeError(msg)
                    if isinstance(feature_config_variable, self.config_cls()):
                        self.config = feature_config_variable
                    else:
                        self.config = self.config_cls().model_validate(feature_config_variable)
                else:
                    self.config = self.config_cls().model_validate(feature_config)
            except pydantic.ValidationError as error:
                msg = f"Configuration validation error in the feature {self}: {error}"
                raise ValueError(msg) from error
        else:
            self.config = self._init_config
        ft_store.add(self)
        self.ft_store = ft_store

    @classmethod
    def config_cls(cls: type[AbstractApplicationFeature[_T_config]]) -> type[_T_config]:
        factory_bases: Iterable[type[AbstractApplicationFeature[_T_config]]] = (  # type: ignore
            b
            for b in get_original_bases(cls)
            if get_origin(b) and issubclass(get_origin(b), AbstractApplicationFeature)
        )
        generic_args: Sequence[type[_T_config]] = [
            arg
            for factory_base in factory_bases
            for arg in get_args(factory_base)
            if not isinstance(arg, TypeVar)  # type: ignore
        ]
        return generic_args[0]

    def init(self) -> None:
        pass

    async def _on_startup(self) -> None:
        """On startup."""
        self._logger = self.ft_store.logging.get_logger(f"asgiext.features.{self.name}")
        self._logger.info("Startup feature %s", self)
        try:
            if self.config.on_startup_override:
                await self.config.on_startup_override(self)
            else:
                await self.on_startup()
        except Exception as error:
            msg = f"Error while startup feature {self}: {error}"
            raise RuntimeError(msg) from error

    async def _on_shutdown(self) -> None:
        """On shutdown."""
        try:
            self._logger.info("Shutdown feature %s", self)
            if self.config.on_shutdown_override:
                await self.config.on_shutdown_override(self)
            else:
                await self.on_shutdown()
        except:  # noqa: E722
            self._logger.exception("Error while shutdown feature %s", self)

    def _start_soon_background_async(
        self,
        func: Callable[..., Awaitable[Any]],
        *args: Any,  # noqa: ANN401
        die_on_exception: bool = False,
        name: str | None = None,
    ) -> None:
        """Start soon background async."""
        background_awaitable: Callable[..., Awaitable[Any]]
        if die_on_exception:

            async def wrapper() -> None:
                try:
                    await func(*args)
                except:  # noqa: E722
                    task_name = f'"{name}": {func!r}' if name else repr(func)
                    self._logger.exception(
                        "Error in feature %s while serving background async task %s",
                        self,
                        task_name,
                    )
                    os.kill(os.getgid(), signal.SIGINT)

            background_awaitable = wrapper
        else:
            background_awaitable = func
        if not self.task_group:
            msg = f"No active async task group, need to call __aenter__ for the feature {self!r}"
            raise RuntimeError(msg)
        self.task_group.start_soon(background_awaitable)

    async def __aenter__(self) -> Self:
        """Aenter."""
        self.task_group = task_group = anyio.create_task_group()
        self.async_context = AsyncExitStack()
        self.shield = shield = CancelScope(shield=True)
        await self.async_context.__aenter__()

        async def on_exit_async_context(*args: Any, **kwargs: Any) -> None:  # noqa: ARG001, ANN401
            shield.cancel()
            task_group.cancel_scope.cancel()
            # hush exception, since the task group requires to handle all exceptions that occurred in it
            await task_group.__aexit__(None, None, None)

        await task_group.__aenter__()
        self.async_context.push_async_exit(on_exit_async_context)
        self.async_context.enter_context(self.shield)
        self.may_start_serving_event = anyio.Event()
        await self._on_startup()
        return self

    async def __aexit__(
        self,
        __exc_type: type[BaseException] | None,
        __exc_value: BaseException | None,
        __traceback: TracebackType | None,
    ) -> None:
        """Aexit."""
        await self._on_shutdown()
        # self.async_context should always be present when __aexit__ is called,
        # because __aenter__ should have been executed before that.
        # Without __aenter__ we should never call __aexit__ directly,
        # but should use the feature as a async context manager.
        await self.async_context.__aexit__(  # type: ignore
            __exc_type,
            __exc_value,
            __traceback,
        )

    def __repr__(self) -> str:
        """Repr."""
        return f"<{self.__class__.__name__}:{self.name}>"


_T_asgi_framework_co = TypeVar("_T_asgi_framework_co", bound=ASGIFramework, covariant=True)


class AppFeature(AbstractApplicationFeature[_T_config], Generic[_T_config, _T_asgi_framework_co]):
    """AppFeature."""

    app: _T_asgi_framework_co

    def register_features_lifespan(self, features_lifespan: Callable[..., AsyncGenerator[None, None]]) -> None:
        self.features_lifespan = features_lifespan

    @abstractmethod
    def get_http_routes(self) -> Iterable[tuple[str, Callable[..., Any]]]:
        pass


class FeatureConfig(BaseSettings):
    # If the FeatureConfig is set programmatically from a python file,
    # the file must contain a dict variable with a valid feature config and such a name.
    _python_config_variable_name: ClassVar[str] = "CONFIG"

    # exclude overridden functions from serialization
    init_override: Optional[Callable[[AbstractApplicationFeature[Self]], None]] = Field(default=None, exclude=True)
    on_startup_override: Optional[Callable[[AbstractApplicationFeature[Self]], Awaitable[None]]] = Field(
        default=None, exclude=True
    )
    on_shutdown_override: Optional[Callable[[AbstractApplicationFeature[Self]], Awaitable[None]]] = Field(
        default=None, exclude=True
    )

    @classmethod
    def get_python_config_variable_name(cls) -> str:
        return cls._python_config_variable_name


feature_type = TypeVar("feature_type", bound=AbstractApplicationFeature[Any])


class FeatureStore:
    """FeatureStore."""

    _features: dict[str, AbstractApplicationFeature[Any]]

    def __init__(self, app_feature: AppFeature[Any, _T_asgi_framework_co]) -> None:  # type: ignore
        """Initialize."""
        self._features = {}
        self.app_feature = app_feature

    def add(self, feature: AbstractApplicationFeature[Any]) -> None:
        """Add."""
        self._features[feature.name] = feature

    @overload
    def get(
        self,
        feature: str,
        *,
        error_if_not_exists: Literal[True] = True,
        validate_type: Optional[type[feature_type]],
    ) -> feature_type: ...

    @overload
    def get(
        self,
        feature: str,
        *,
        error_if_not_exists: Literal[True] = True,
        validate_type: Optional[type[feature_type]] = None,
    ) -> AbstractApplicationFeature[Any]: ...

    @overload
    def get(
        self,
        feature: str,
        *,
        error_if_not_exists: Literal[False] = False,
        validate_type: Optional[type[feature_type]],
    ) -> feature_type | None: ...

    @overload
    def get(
        self,
        feature: str,
        *,
        error_if_not_exists: Literal[False] = False,
        validate_type: Optional[type[feature_type]] = None,
    ) -> AbstractApplicationFeature[Any] | None: ...

    @overload
    def get(
        self,
        feature: type[feature_type],
        *,
        error_if_not_exists: Literal[True] = True,
        validate_type: Optional[type[feature_type]] = None,
    ) -> feature_type: ...

    @overload
    def get(
        self,
        feature: type[feature_type],
        *,
        error_if_not_exists: Literal[False] = False,
        validate_type: Optional[type[feature_type]] = None,
    ) -> feature_type | None: ...

    def get(
        self,
        feature: str | type[feature_type],
        *,
        error_if_not_exists: bool = True,
        validate_type: Optional[type[feature_type]] = None,
    ) -> AbstractApplicationFeature[Any] | None:
        """Get."""
        feature_obj = self._features.get(feature) if isinstance(feature, str) else self._features.get(feature.name)
        if feature_obj is None and error_if_not_exists:
            msg = f"Feature {feature!r} does not exists in FeatureStore"
            raise ValueError(msg)
        if feature_obj is None:
            return feature_obj
        if not isinstance(feature, str):
            validate_type = feature
        if validate_type and not issubclass(feature_obj.__class__, validate_type):
            msg = (
                f"Feature {feature_obj!r} with type {feature_obj.__class__!r} "
                f"obtained from the feature store failed validation for type {validate_type!r}"
            )
            raise TypeError(msg)
        return feature_obj

    @property
    def features(self) -> tuple[AbstractApplicationFeature[Any], ...]:
        """Features."""
        return tuple(self._features.values())

    # easy access to default features
    @property
    def asgi_web_server(self) -> ASGIWebServerFeature:
        from asgiext.features.core.asgi_web_server import ASGIWebServerFeature

        return self.get(ASGIWebServerFeature)

    @property
    def logging(self) -> LoggingFeature:
        from asgiext.features.core.logging import LoggingFeature

        return self.get(LoggingFeature)

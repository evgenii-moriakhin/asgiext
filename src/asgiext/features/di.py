from __future__ import annotations

from typing import Any, Callable

from asgiext.features.core import AbstractApplicationFeature, FeatureConfig


class DependenciesInjectionFeatureConfig(FeatureConfig):
    """DependenciesInjectionFeatureConfig."""


class DependenciesInjectionFeature(AbstractApplicationFeature[DependenciesInjectionFeatureConfig]):
    """DependenciesInjectionFeature."""

    name: str = "DI"

    _inject_dependencies_func: Callable[..., Any]

    def __init__(
        self,
        name: str | None = None,
        *,
        config: DependenciesInjectionFeatureConfig | None = None,
        inject_dependencies_func: Callable[..., Any] = lambda: None,
    ) -> None:
        super().__init__(name, config=config)
        self._inject_dependencies_func = inject_dependencies_func

    ####################
    # NON-PUBLIC USAGE #
    ####################

    async def on_startup(self) -> None:
        """On startup."""
        self._inject_dependencies_func(self)

    async def on_shutdown(self) -> None:
        """On shutdown."""

from __future__ import annotations

import copy
from typing import Any

from pydantic import Field

from asgiext.features.core import AbstractApplicationFeature, FeatureConfig


class ConstantsConfig(FeatureConfig):
    """ConstantsConfig."""

    constants_store: dict[str, Any] = Field(
        default_factory=dict,
    )


class ConstantsFeature(AbstractApplicationFeature[ConstantsConfig]):
    """ConstantsFeature.

    Allows you to store arbitrary constants required by the application in the config and retrieve them in runtime.
    A deep copy is always returned for mutable constants (dict and list now).
    """

    name = "CONSTANTS"

    ####################
    # FOR PUBLIC USAGE #
    ####################

    def get(self, name: str) -> Any:  # noqa: ANN401
        """Get constant from application config by name.

        Returns deep copy for mutable constant types (list and dict).
        """
        constant = self.config.constants_store.get(name, None)
        if isinstance(constant, (list, dict)):
            return copy.deepcopy(constant)  # type: ignore
        return constant

    ####################
    # NON-PUBLIC USAGE #
    ####################

    async def on_startup(self) -> None:
        """On startup."""

    async def on_shutdown(self) -> None:
        """On shutdown."""

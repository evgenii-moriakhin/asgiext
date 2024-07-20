from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

from asgiext.features.core import AbstractApplicationFeature, FeatureConfig, FeatureStore


class ParseCLIArgsConfig(FeatureConfig):
    """ParseCLIArgsConfig."""

    features: dict[str, Any]


class ParseCLIArgsFeature(AbstractApplicationFeature[ParseCLIArgsConfig]):
    """ParseCLIArgsFeature."""

    name = "PARSE_CLI_ARGS"

    ####################
    # FOR PUBLIC USAGE #
    ####################

    @property
    def config_path(self) -> Path:
        return self._config_path

    ####################
    # NON-PUBLIC USAGE #
    ####################

    def set_config(self, ft_store: FeatureStore) -> None:
        """Set config"""
        parser = argparse.ArgumentParser()
        parser.add_argument("--conf", help="Path to app configuration", required=True)
        args = parser.parse_args()
        self._config_path = Path(args.conf)
        try:
            self.config = self.config_cls().model_validate(
                {"features": yaml.load(self._config_path.read_bytes(), Loader=yaml.CSafeLoader) or {}}
            )
        except Exception as error:
            msg = (
                "Error receiving and validation application config "
                f"from yaml file {self.config_path} in the feature {self}: {error}"
            )
            raise ValueError(msg) from error
        ft_store.add(self)
        self.ft_store = ft_store

    async def on_startup(self) -> None:
        """On startup."""

    async def on_shutdown(self) -> None:
        """On shutdown."""

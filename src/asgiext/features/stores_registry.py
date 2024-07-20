from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Optional, Union

from pydantic import Field
from pydantic_settings import BaseSettings
from redis.asyncio import Redis

from asgiext.features.core import AbstractApplicationFeature, FeatureConfig
from asgiext.features.stores.file import FileStore
from asgiext.features.stores.memory import MemoryStore
from asgiext.features.stores.redis import RedisStore

if TYPE_CHECKING:
    from asgiext.features.stores.base import Store


class StoreNotExistsError(Exception): ...


class FileStoreConfig(BaseSettings):
    path: Union[str, Path]


class MemoryStoreConfig(BaseSettings): ...


class RedisStoreConfig(BaseSettings):
    namespace: Optional[str] = None

    host: str = "localhost"
    port: int = 6379
    db: Union[str, int] = 0
    password: Optional[str] = None
    username: Optional[str] = None


class StoreConfig(BaseSettings):
    """StoresRegistryConfig."""

    name: str
    type: Literal["file", "memory", "redis"]
    config: dict[str, Any] = Field(default_factory=dict)


class StoresRegistryConfig(FeatureConfig):
    """StoresRegistryConfig."""

    stores: list[StoreConfig] = Field(default_factory=list)


class StoresRegistryFeature(AbstractApplicationFeature[StoresRegistryConfig]):
    """StoresRegistryFeature."""

    name = "STORES_REGISTRY"

    _stores: dict[str, Store]

    ####################
    # FOR PUBLIC USAGE #
    ####################

    def get_store(self, name: str) -> Store:
        try:
            return self._stores[name]
        except KeyError as error:
            msg = f"Store named {name!r} does not exist in the store registry {self!r}"
            raise StoreNotExistsError(msg) from error

    ####################
    # NON-PUBLIC USAGE #
    ####################

    def init(self) -> None:
        self._stores = {}
        for store in self.config.stores:
            if store.type == "file":
                file_store_config = FileStoreConfig.model_validate(store.config or {})
                self._stores[store.name] = FileStore(Path(file_store_config.path))
            if store.type == "memory":
                memory_store_config = MemoryStoreConfig.model_validate(store.config or {})  # type: ignore  # noqa: F841
                self._stores[store.name] = MemoryStore()
            if store.type == "redis":
                redis_store_config = RedisStoreConfig.model_validate(store.config or {})
                self._stores[store.name] = RedisStore(
                    Redis(
                        host=redis_store_config.host,
                        port=redis_store_config.port,
                        db=redis_store_config.db,
                        password=redis_store_config.password,
                        username=redis_store_config.username,
                    ),
                    namespace=redis_store_config.namespace,
                )

    async def on_startup(self) -> None:
        """On startup."""

    async def on_shutdown(self) -> None:
        """On shutdown."""

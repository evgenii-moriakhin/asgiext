from __future__ import annotations

from typing import TYPE_CHECKING
from unittest import mock

import pytest
from fakeredis import FakeAsyncRedis

from asgiext.features.app_features.starlette import StarletteFeature
from asgiext.features.stores_registry import (
    StoreConfig,
    StoreNotExistsError,
    StoresRegistryConfig,
    StoresRegistryFeature,
)
from asgiext.testing.helpers import app_lifespan_manager

if TYPE_CHECKING:
    from asgiext.features.core.asgi_web_server import ASGIWebServerFeature

pytestmark = pytest.mark.anyio


class TestStoresRegistryFeature:
    def test_fields(self):
        assert StoresRegistryFeature.name == "STORES_REGISTRY"
        assert StoresRegistryFeature.config_cls() is StoresRegistryConfig  # type: ignore

    async def test_stores_registry_file_stores(
        self, tmp_path_factory: pytest.TempPathFactory, asgi_web_server_feature: ASGIWebServerFeature
    ):
        starlette_feature = StarletteFeature()
        stores_registry = StoresRegistryFeature(
            config=StoresRegistryConfig(
                stores=[
                    StoreConfig(
                        name="first_file_store", type="file", config={"path": tmp_path_factory.mktemp("first")}
                    ),
                    StoreConfig(
                        name="second_file_store", type="file", config={"path": tmp_path_factory.mktemp("second")}
                    ),
                ]
            )
        )
        features = [starlette_feature, asgi_web_server_feature, stores_registry]
        async with app_lifespan_manager(features, starlette_feature):
            first_file_store = stores_registry.get_store("first_file_store")
            second_file_store = stores_registry.get_store("second_file_store")
            await first_file_store.set("test1", "value1")
            await second_file_store.set("test2", "value2")
            with pytest.raises(StoreNotExistsError):
                stores_registry.get_store("third_file_store")

            assert await first_file_store.get("test1") == b"value1"
            assert await second_file_store.get("test2") == b"value2"

            assert await second_file_store.get("test1") is None

    async def test_stores_registry_memory_stores(self, asgi_web_server_feature: ASGIWebServerFeature):
        starlette_feature = StarletteFeature()
        stores_registry = StoresRegistryFeature(
            config=StoresRegistryConfig(
                stores=[
                    StoreConfig(name="first_memory_store", type="memory"),
                    StoreConfig(name="second_memory_store", type="memory"),
                ]
            )
        )
        features = [starlette_feature, asgi_web_server_feature, stores_registry]
        async with app_lifespan_manager(features, starlette_feature):
            first_memory_store = stores_registry.get_store("first_memory_store")
            second_memory_store = stores_registry.get_store("second_memory_store")
            await first_memory_store.set("test1", "value1")
            await second_memory_store.set("test2", "value2")
            with pytest.raises(StoreNotExistsError):
                stores_registry.get_store("third_file_store")

            assert await first_memory_store.get("test1") == b"value1"
            assert await second_memory_store.get("test2") == b"value2"

            assert await second_memory_store.get("test1") is None

    async def test_stores_registry_redis_stores(self, asgi_web_server_feature: ASGIWebServerFeature):
        starlette_feature = StarletteFeature()
        stores_registry = StoresRegistryFeature(
            config=StoresRegistryConfig(
                stores=[
                    StoreConfig(name="first_redis_store", type="redis", config={"port": 1000}),
                    StoreConfig(name="second_redis_store", type="redis", config={"port": 1001}),
                ]
            )
        )
        features = [starlette_feature, asgi_web_server_feature, stores_registry]
        with mock.patch("asgiext.features.stores_registry.Redis", FakeAsyncRedis):
            async with app_lifespan_manager(features, starlette_feature):
                first_redis_store = stores_registry.get_store("first_redis_store")
                second_redis_store = stores_registry.get_store("second_redis_store")
                await first_redis_store.set("test1", "value1")
                await second_redis_store.set("test2", "value2")
                with pytest.raises(StoreNotExistsError):
                    stores_registry.get_store("third_file_store")

                assert await first_redis_store.get("test1") == b"value1"
                assert await second_redis_store.get("test2") == b"value2"

                assert await second_redis_store.get("test1") is None

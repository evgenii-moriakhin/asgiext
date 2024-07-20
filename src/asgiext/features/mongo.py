from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient

from asgiext.features.core import AbstractApplicationFeature, FeatureConfig


class MongoConfig(FeatureConfig):
    """MongoConfig."""

    host: str
    port: int


class MongoFeature(AbstractApplicationFeature[MongoConfig]):
    """MongoFeature."""

    name = "MONGO"

    _client: AsyncIOMotorClient | None = None

    ####################
    # FOR PUBLIC USAGE #
    ####################

    @property
    def client(self) -> AsyncIOMotorClient:
        """Mongo Client."""
        if self._client is None:
            msg = "Mongo client doesn't exist yet"
            raise RuntimeError(msg)
        return self._client

    ####################
    # NON-PUBLIC USAGE #
    ####################

    async def on_startup(self) -> None:
        """On startup."""
        self._client = AsyncIOMotorClient(self.config.host, self.config.port)

    async def on_shutdown(self) -> None:
        """On shutdown."""
        self.client.close()

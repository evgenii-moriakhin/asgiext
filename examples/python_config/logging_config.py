# noqa: INP001
from typing import cast

from asgiext.features.core import AbstractApplicationFeature
from asgiext.features.core.logging import LoggingFeature, LoggingFeatureConfig


def custom_init(ft: AbstractApplicationFeature[LoggingFeatureConfig]) -> None:
    ft = cast(LoggingFeature, ft)
    ft.init()
    ft.get_logger().info("Custom LoggingFeature init done")


async def custom_on_startup(ft: AbstractApplicationFeature[LoggingFeatureConfig]) -> None:
    ft = cast(LoggingFeature, ft)
    await ft.on_startup()
    ft.get_logger().info("Custom LoggingFeature on_startup done")


async def custom_on_shutdown(ft: AbstractApplicationFeature[LoggingFeatureConfig]) -> None:
    ft = cast(LoggingFeature, ft)
    await ft.on_shutdown()
    ft.get_logger().info("Custom LoggingFeature on_shutdown done")


CONFIG = LoggingFeatureConfig(
    init_override=custom_init,
    on_startup_override=custom_on_startup,
    on_shutdown_override=custom_on_shutdown,
)

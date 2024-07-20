from __future__ import annotations

import logging
from contextvars import Context  # noqa: TCH003
from dataclasses import asdict, dataclass, field
from logging import Logger, config
from typing import Any, Callable, Literal, Optional, Union

import msgspec
import structlog
from pydantic import Field
from structlog.contextvars import bind_contextvars, clear_contextvars, get_contextvars, unbind_contextvars
from structlog.dev import RichTracebackFormatter, plain_traceback
from structlog.typing import BindableLogger, Processor, WrappedLogger  # noqa: TCH002

from asgiext.features.core import AbstractApplicationFeature, FeatureConfig

timestamper = structlog.processors.TimeStamper(fmt="iso")
pre_chain = [
    # Add the log level and a timestamp to the event_dict if the log entry
    # is not from structlog.
    structlog.stdlib.add_log_level,
    # Add extra attributes of LogRecord objects to the event dictionary
    # so that values passed in the extra parameter of log methods pass
    # through to log output.
    structlog.stdlib.ExtraAdder(),
    timestamper,
]


def extract_from_record(_, __, event_dict: dict[str, Any]) -> dict[str, Any]:  # type: ignore # noqa: ANN001
    """Extract thread and process names and add them to the event dict."""
    record = event_dict["_record"]
    event_dict["thread_name"] = record.threadName
    event_dict["process_name"] = record.processName
    return event_dict


@dataclass
class StructlogConfig:
    processors: Optional[list[Processor]] = field(
        default_factory=lambda: [
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            timestamper,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ]
    )
    wrapper_class: Optional[type[BindableLogger]] = structlog.stdlib.BoundLogger
    context_class: Optional[type[Context]] = None
    logger_factory: Optional[Callable[..., WrappedLogger]] = structlog.stdlib.LoggerFactory()  # noqa: RUF009
    cache_logger_on_first_use: Optional[bool] = True


def default_json_format_serializer(obj: Any, **kwargs: Any) -> str:  # noqa: ANN401
    order = kwargs.get("order", "sorted")
    return msgspec.json.encode(obj, order=order).decode()


class LoggingFeatureConfig(FeatureConfig):
    """LoggingFeatureConfig."""

    version: Literal[1] = 1
    disable_existing_loggers: bool = False
    filters: Optional[dict[str, dict[str, Any]]] = None
    propagate: bool = True
    formatters: dict[str, Any] = Field(
        default_factory=lambda: {
            "plain": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processors": [
                    extract_from_record,
                    structlog.contextvars.merge_contextvars,
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.dev.ConsoleRenderer(colors=False, exception_formatter=plain_traceback),
                ],
                "foreign_pre_chain": pre_chain,
            },
            "json": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processors": [
                    extract_from_record,
                    structlog.contextvars.merge_contextvars,
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.processors.dict_tracebacks,
                    structlog.processors.JSONRenderer(serializer=default_json_format_serializer),
                ],
                "foreign_pre_chain": pre_chain,
            },
            "colored": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processors": [
                    extract_from_record,
                    structlog.contextvars.merge_contextvars,
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.dev.ConsoleRenderer(colors=True, exception_formatter=plain_traceback),
                ],
                "foreign_pre_chain": pre_chain,
            },
            "colored_rich_traceback": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processors": [
                    extract_from_record,
                    structlog.contextvars.merge_contextvars,
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.dev.ConsoleRenderer(colors=True, exception_formatter=RichTracebackFormatter()),
                ],
                "foreign_pre_chain": pre_chain,
            },
        },  # type: ignore
    )
    handlers: dict[str, dict[str, Any]] = Field(
        default_factory=lambda: {
            "console": {
                "class": "logging.StreamHandler",
                "level": "DEBUG",
                "formatter": "colored",
            },
        },
    )
    loggers: dict[str, dict[str, Any]] = Field(
        default_factory=lambda: {
            "asgiext": {"level": "INFO", "handlers": ["console"], "propagate": False},
        },
    )
    root: dict[str, Union[dict[str, Any], list[Any], str]] = Field(
        default_factory=lambda: {
            "handlers": ["console"],
            "level": "INFO",
        },
    )
    log_exceptions: Literal["always", "debug", "never"] = "debug"
    traceback_line_limit: int = 20

    structlog_config: StructlogConfig = Field(default=StructlogConfig(), exclude=True)


class LoggingFeature(AbstractApplicationFeature[LoggingFeatureConfig]):
    """LoggingFeature."""

    name = "LOGGING"

    ####################
    # FOR PUBLIC USAGE #
    ####################

    def get_logger(self, logger_name: str | None = None) -> Logger:
        """Get stdlib logger."""
        return logging.getLogger(logger_name)

    @classmethod
    def set_log_context(cls, key: str, value: str) -> None:
        bind_contextvars(**{key: value})

    @classmethod
    def clear_log_context(cls) -> None:
        clear_contextvars()

    @classmethod
    def get_log_context(cls) -> dict[str, Any]:
        return get_contextvars()

    @classmethod
    def remove_log_context(cls, *keys: str) -> None:
        return unbind_contextvars(*keys)

    @property
    def logging_dict_config(self) -> dict[str, Any]:
        return self.config.model_dump(exclude_none=True)

    ####################
    # NON-PUBLIC USAGE #
    ####################

    def init(self) -> None:
        """Init."""
        try:
            config.dictConfig(self.logging_dict_config)
            structlog.configure(**asdict(self.config.structlog_config))
        except Exception as error:
            msg = f"Exception while configure logging in feature {self}: {error}"
            raise type(error)(msg) from error

    async def on_startup(self) -> None:
        """On startup."""

    async def on_shutdown(self) -> None:
        """On shutdown."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any, Callable, Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings

from asgiext.features.core import AbstractApplicationFeature, FeatureConfig

if TYPE_CHECKING:
    from gunicorn.arbiter import Arbiter  # type: ignore
    from gunicorn.workers.base import Worker  # type: ignore


class HypercornConfig(BaseSettings):
    """HypercornConfig."""

    application_path: str
    errorlog: str = "hypercorn.error"
    accesslog: str = "hypercorn.access"
    access_log_format: str = "%(r)s %(s)s %(st)s - %(a)s"
    bind: str = "127.0.0.1:8000"
    workers: int = 1

    # exclude fields not related to the web server configuration from serialization
    errorlog_enabled: bool = True
    accesslog_enabled: bool = False


class UvicornConfig(BaseSettings):
    """UvicornConfig."""

    app: str
    host: str = "127.0.0.1"
    port: int = 8000
    loop: str = "asyncio"
    lifespan: str = "on"
    interface: str = "asgi3"
    access_log: bool = False
    workers: int = 1

    # exclude fields not related to the web server configuration from serialization
    uvicorn_errorlog_handlers: list[str] = Field(default_factory=lambda: ["console"], exclude=True)
    uvicorn_accesslog_handlers: list[str] = Field(default_factory=lambda: ["console"], exclude=True)


class GunicornUvicornConfig(BaseSettings):
    """GunicornUvicornConfig."""

    app: str
    uvicorn_worker_settings: dict[str, Any] = Field(
        default_factory=lambda: {"loop": "asyncio"},
    )
    # settings and allowed values from .../gunicorn/config.py
    bind: str = "127.0.0.1:8000"
    accesslog: Optional[str] = None
    workers: int = 1
    timeout: int = 600
    loglevel: str = "info"

    # exclude fields not related to the web server configuration from serialization
    gunicorn_errorlog_handlers: list[str] = Field(default_factory=lambda: ["console"], exclude=True)
    gunicorn_accesslog_handlers: list[str] = Field(default_factory=lambda: ["console"], exclude=True)


class GranianConfig(BaseSettings):
    """GranianConfig."""

    target: str
    address: str = "127.0.0.1"
    port: int = 8000

    # exclude fields not related to the web server configuration from serialization
    granian_log_handlers: list[str] = Field(default_factory=lambda: ["console"], exclude=True)


class ASGIWebServerConfig(FeatureConfig):
    """ASGIWebServerConfig."""

    type: Literal["hypercorn", "uvicorn", "gunicorn_uvicorn", "granian"]
    config: dict[str, Any]


class ASGIWebServerFeature(AbstractApplicationFeature[ASGIWebServerConfig]):
    """ASGIWebServerFeature."""

    name = "ASGI_WEB_SERVER"

    _runner: Callable[..., Any]
    _gunicorn_child_exit_callbacks: list[Callable[[Arbiter, Worker], None]]

    def __init__(self, name: str | None = None, *, config: ASGIWebServerConfig | None = None) -> None:
        super().__init__(name, config=config)
        self.multiproc_mode = False
        self._gunicorn_child_exit_callbacks = []

    ####################
    # FOR PUBLIC USAGE #
    ####################

    def get_runner(self) -> Callable[..., Any]:
        """Get runner."""
        return self._runner

    def add_gunicorn_child_exit_callback(self, child_exit_callback: Callable[[Arbiter, Worker], None]) -> None:
        self._gunicorn_child_exit_callbacks.append(child_exit_callback)

    ####################
    # NON-PUBLIC USAGE #
    ####################

    def init(self) -> None:  # noqa: C901, PLR0915, PLR0912
        """Init.

        Warning!
        If you use gevent, it doesn't work with uvloop implementation (at least for now).
        So the default implementation in the config is asyncio
        """
        if self.config.type == "hypercorn":
            """ since the latest (at the moment) version of hypercorn 15.0 is quite raw and has many issues
            that appeared on the github, which have also appeared here, (https://github.com/pgjones/hypercorn/issues/158)
            it is recommended to use gunicorn + uvicorn."""
            from hypercorn import Config, run

            hypercorn_feature_config = HypercornConfig.model_validate(self.config.config)
            if hypercorn_feature_config.workers > 1:
                self.multiproc_mode = True
            hypercorn_config = Config.from_mapping(hypercorn_feature_config.model_dump())

            # explicitly set the logger objects so that hypercorn does not make its own logger init internally
            if hypercorn_feature_config.errorlog_enabled:
                hypercorn_config.errorlog = self.ft_store.logging.get_logger(hypercorn_feature_config.errorlog)
            else:
                hypercorn_config.errorlog = None
            if hypercorn_feature_config.accesslog_enabled:
                hypercorn_config.access_log_format = hypercorn_feature_config.access_log_format
                hypercorn_config.accesslog = self.ft_store.logging.get_logger(hypercorn_feature_config.accesslog)
            else:
                hypercorn_config.accesslog = None
            self._runner = partial(run.run, hypercorn_config)
        elif self.config.type == "uvicorn":
            import uvicorn

            uvicorn_config = UvicornConfig.model_validate(self.config.config)
            if uvicorn_config.workers > 1:
                self.multiproc_mode = True
            uvicorn_config_dict = uvicorn_config.model_dump()

            # Use the logger config from the feature
            logging_dict_config = self.ft_store.logging.logging_dict_config
            if "uvicorn.error" not in logging_dict_config["loggers"]:
                logging_dict_config["loggers"]["uvicorn.error"] = {
                    "level": "INFO",
                    "handlers": uvicorn_config.uvicorn_errorlog_handlers,
                    "propagate": False,
                }
            if "uvicorn.access" not in logging_dict_config["loggers"]:
                logging_dict_config["loggers"]["uvicorn.access"] = {
                    "level": "INFO",
                    "handlers": uvicorn_config.uvicorn_accesslog_handlers,
                    "propagate": False,
                }
            uvicorn_config_dict["log_config"] = logging_dict_config
            self._runner = partial(uvicorn.run, **uvicorn_config_dict)
        elif self.config.type == "gunicorn_uvicorn":
            """It is recommended to use this gunicorn + uvicorn worker bundle for great stability
            (from the internet and discussions)"""

            from gunicorn.app.base import BaseApplication  # type: ignore
            from uvicorn.workers import UvicornWorker

            class StandaloneApplication(BaseApplication):
                """Slightly modified gunicorn + uvicorn launch from python code.

                from here:
                https://gist.github.com/Kludex/c98ed6b06f5c0f89fd78dd75ef58b424.
                """

                def __init__(self, application_path: str, options: Optional[dict[str, Any]] = None) -> None:
                    self.options = options or {}
                    self.application_path = application_path
                    super().__init__()  # type: ignore

                def load_config(self) -> None:
                    for key, value in self.options.items():
                        if self.cfg and key in self.cfg.settings:  # type: ignore
                            self.cfg.set(key, value)  # type: ignore

                def load(self) -> str:
                    return self.application_path

            gunicorn_uvicorn_config = GunicornUvicornConfig.model_validate(self.config.config)
            if gunicorn_uvicorn_config.workers > 1:
                self.multiproc_mode = True
            gunicorn_opts = gunicorn_uvicorn_config.model_dump()

            class CustomUvicornWorker(UvicornWorker):
                CONFIG_KWARGS = gunicorn_uvicorn_config.uvicorn_worker_settings

                @classmethod
                def endswith(cls: type[CustomUvicornWorker], string: str) -> bool:
                    """Workaround fix AttributeError: No configuration setting for: worker_class_str in gunicorn source.

                    in the case of directly passing the worker class in opts.
                    """
                    return cls.__name__.endswith(string)

                """it was decided not to use the asyncio_gevent library, because of the implicit problems encountered.
                For example, I have encountered the inability to debug gunicorn+uvicorn,
                as well as the inability to debug uvicorn.
                After removing the asyncio_gevent event loop policy,
                at least the uvicorn debugging worked"""

                """Necessary when using asyncio_gevent loop policy,
                asyncio.set_event_loop_policy(asyncio_gevent.EventLoopPolicy())
                because otherwise asgi lifespan shutdown does not work for the workers.
                With asyncio gevent loop policy turned off, these lines do not visually cause errors -
                asgi startup and shudtown for workers work fine.
                I DON'T KNOW WHY IT BREAKS, AND WHY IT WORKS WITH THIS FIX.
                I found this signal handler in the Server code."""
                """async def _serve(self) -> None:
                    self.config.app = self.wsgi
                    server = Server(config=self.config)
                    self._install_sigquit_handler()
                    loop = asyncio.get_running_loop()
                    loop.add_signal_handler(signal.SIGINT, server.handle_exit, signal.SIGINT, None)
                    # and this handler is needed for correct shutdown via 'kill <pid>'
                    loop.add_signal_handler(signal.SIGTERM, server.handle_exit, signal.SIGTERM, None)

                    await server.serve(sockets=self.sockets)
                    if not server.started:
                        sys.exit(Arbiter.WORKER_BOOT_ERROR)"""

            gunicorn_opts["worker_class"] = CustomUvicornWorker

            logging_dict_config = self.ft_store.logging.logging_dict_config
            if "gunicorn.error" not in logging_dict_config["loggers"]:
                logging_dict_config["loggers"]["gunicorn.error"] = {
                    "level": "INFO",
                    "handlers": gunicorn_uvicorn_config.gunicorn_errorlog_handlers,
                    "propagate": False,
                }
            if "gunicorn.access" not in logging_dict_config["loggers"] and gunicorn_uvicorn_config.accesslog:
                logging_dict_config["loggers"]["gunicorn.access"] = {
                    "level": "INFO",
                    "handlers": gunicorn_uvicorn_config.gunicorn_accesslog_handlers,
                    "propagate": False,
                }
            gunicorn_opts["logconfig_dict"] = logging_dict_config

            def child_exit(server: Arbiter, worker: Worker) -> None:
                for child_exit_callback in self._gunicorn_child_exit_callbacks:
                    child_exit_callback(server, worker)

            gunicorn_opts["child_exit"] = child_exit

            self._runner = StandaloneApplication(
                gunicorn_uvicorn_config.app,
                gunicorn_opts,
            ).run

        elif self.config.type == "granian":
            from granian import constants
            from granian.server import Granian

            granian_config = GranianConfig.model_validate(self.config.config)
            # TODO(emoryakhin): need add granian multiproc mode and set self.multiproc_mode  # noqa: TD003, FIX002
            logging_dict_config = self.ft_store.logging.logging_dict_config

            if "_granian" not in logging_dict_config["loggers"]:
                logging_dict_config["loggers"]["_granian"] = {
                    "_granian": {"handlers": granian_config.granian_log_handlers, "level": "INFO", "propagate": False}
                }
            self._runner = Granian(
                target=granian_config.target,
                address=granian_config.address,
                port=granian_config.port,
                interface=constants.Interfaces.ASGI,
                log_dictconfig=logging_dict_config,
                loop=constants.Loops.asyncio,
            ).serve
        else:
            msg = f"No such ASGI server is supported at this time: {self.config.type}"
            raise RuntimeError(msg)

    async def on_startup(self) -> None:
        """On startup."""

    async def on_shutdown(self) -> None:
        """On shutdown."""

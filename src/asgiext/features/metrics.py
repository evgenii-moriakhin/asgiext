from __future__ import annotations

import os
import time
from collections.abc import (  # noqa: TCH003 need to have real type objects for annotations in pydantic
    Mapping,
)
from contextvars import ContextVar
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Optional, TypedDict, Union, cast

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    multiprocess,
)
from prometheus_client.openmetrics.exposition import (
    CONTENT_TYPE_LATEST as OPENMETRICS_CONTENT_TYPE_LATEST,
)
from prometheus_client.openmetrics.exposition import (
    generate_latest as openmetrics_generate_latest,  # type: ignore
)

from asgiext.features.app_features.quart import QuartFeature
from asgiext.features.app_features.starlette import StarletteFeature
from asgiext.features.core import AbstractApplicationFeature, FeatureConfig

if TYPE_CHECKING:
    from gunicorn.arbiter import Arbiter  # type: ignore
    from gunicorn.workers.base import Worker  # type: ignore
    from prometheus_client.metrics import MetricWrapperBase

metrics_context: ContextVar[Optional[dict[str, Any]]] = ContextVar("metrics_context", default=None)


class MetricsConfig(FeatureConfig):
    """MetricsConfig."""

    enabled: bool = True
    http_path: str = "/metrics"
    openmetrics_format: bool = False

    """The prefix to use for the metrics."""
    prefix: str = "asgiext"
    """A list of buckets to use for the histogram."""
    buckets: Optional[list[Union[str, float]]] = None


class _RequestData(TypedDict):
    method: str
    server: str
    path: str


class MetricsFeature(AbstractApplicationFeature[MetricsConfig]):
    """MetricsFeature."""

    name = "METRICS_MIDDLEWARE"
    DEFAULT_BUCKETS = (
        0.005,
        0.01,
        0.025,
        0.05,
        0.075,
        0.1,
        0.25,
        0.5,
        0.75,
        1.0,
        2.5,
        5.0,
        7.5,
        10.0,
        float("inf"),
    )

    _metrics: ClassVar[dict[str, MetricWrapperBase]] = {}
    _metrics_context: ContextVar[Optional[dict[str, Any]]]
    multiproc_mode: bool

    def __init__(self, name: str | None = None, *, config: MetricsConfig | None = None) -> None:
        super().__init__(name, config=config)
        self._metrics_context = metrics_context
        self.multiproc_mode = False

    ####################
    # NON-PUBLIC USAGE #
    ####################

    def init(self) -> None:
        self.enabled = self.config.enabled
        if self.enabled:
            from prometheus_client import multiprocess

            ft_store = self.ft_store

            asgi_web_server_feature = ft_store.asgi_web_server

            self.multiproc_mode = asgi_web_server_feature.multiproc_mode
            if self.multiproc_mode and "PROMETHEUS_MULTIPROC_DIR" not in os.environ:
                msg = (
                    "The 'PROMETHEUS_MULTIPROC_DIR' env must be set to a directory "
                    "for store metrics in multiproc mode"
                )
                raise ValueError(msg)
            # Directory for metrics,
            # if the server runs in multiproc mode - https://prometheus.github.io/client_python/multiprocess/
            # Unfortunately there is no easy way to pass it in the yaml config right now,
            # because prometheus_client source code is too much tied to the environment variable

            # this means that there may be cases when the env is set globally and the current service
            # is not running in multiproc mode, but the library will still use the approach
            # to collect metrics for multiprocessing.
            # Therefore, the presence of this env does not necessarily needs to run in multiprocess mode,
            # (but multiproc mode needs for this env)
            if "PROMETHEUS_MULTIPROC_DIR" in os.environ and not Path(os.environ["PROMETHEUS_MULTIPROC_DIR"]).is_dir():
                msg = "The 'PROMETHEUS_MULTIPROC_DIR' env is set but is not a directory"
                raise ValueError(msg)
            if asgi_web_server_feature.config.type == "gunicorn_uvicorn":
                # from docs for gunicorn https://prometheus.github.io/client_python/multiprocess/
                def child_exit(server: Arbiter, worker: Worker) -> None:  # noqa: ARG001
                    multiprocess.mark_process_dead(worker.pid, path=os.environ["PROMETHEUS_MULTIPROC_DIR"])  # type: ignore

                asgi_web_server_feature.add_gunicorn_child_exit_callback(child_exit)
            self._setup_metrics_for_asgi_framework()

    def _setup_metrics_for_asgi_framework(self) -> None:
        app_feature = self.ft_store.app_feature
        if isinstance(app_feature, QuartFeature):
            self._setup_metrics_for_quart(app_feature)
        if isinstance(app_feature, StarletteFeature):
            self._setup_metrics_for_starlette(app_feature)
        else:
            msg = f"ASGI framework {type(app_feature.app)} not supported for {self!r}"
            raise TypeError(msg)

    def _setup_metrics_for_quart(self, app_feature: QuartFeature) -> None:
        from quart import Response, request

        app = app_feature.app

        async def metrics_entrypoint() -> Response:
            if self.multiproc_mode:
                registry = CollectorRegistry()
                multiprocess.MultiProcessCollector(registry)
            else:
                registry = REGISTRY
            if self.config.openmetrics_format:
                return Response(
                    openmetrics_generate_latest(registry), status=200, content_type=OPENMETRICS_CONTENT_TYPE_LATEST
                )
            return Response(generate_latest(registry), status=200, content_type=CONTENT_TYPE_LATEST)

        app.get(self.config.http_path)(metrics_entrypoint)

        async def process_http_request_wrapper() -> None:
            self._process_http_request(
                _RequestData(
                    method=request.method,
                    server=request.host,
                    path=request.path,
                )
            )

        async def process_http_response_wrapper(response: Response) -> Response:
            self._process_http_response(status_code=response.status_code)
            return response

        app.before_request(process_http_request_wrapper)
        app.after_request(process_http_response_wrapper)

    def _setup_metrics_for_starlette(self, app_feature: StarletteFeature) -> None:
        from starlette.requests import Request  # noqa: TCH002
        from starlette.responses import Response

        app = app_feature.app

        async def metrics_entrypoint(request: Request) -> Response:  # noqa: ARG001
            if self.multiproc_mode:
                registry = CollectorRegistry()
                multiprocess.MultiProcessCollector(registry)
            else:
                registry = REGISTRY
            if self.config.openmetrics_format:
                return Response(openmetrics_generate_latest(registry), media_type=OPENMETRICS_CONTENT_TYPE_LATEST)
            return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

        app.add_route(self.config.http_path, metrics_entrypoint)

        async def process_http_request_wrapper(request: Request) -> None:
            self._process_http_request(
                _RequestData(
                    method=request.method,
                    server=request.url.hostname or "<unknown_server>",
                    path=request.url.path,
                )
            )

        async def process_http_response_wrapper(request: Request, response: Response) -> Response:  # noqa: ARG001
            self._process_http_response(status_code=response.status_code)
            return response

        app_feature.before_request(process_http_request_wrapper)
        app_feature.after_request(process_http_response_wrapper)

    def _process_http_request(self, request_data: _RequestData) -> None:
        metrics_context: dict[str, Any] = {}
        labels = {
            "method": request_data["method"],
            "path": request_data["path"],
            "server": request_data["server"],
        }
        metrics_context["labels"] = labels
        metrics_context["request_span"] = {
            "start_time": time.perf_counter(),
            "end_time": 0,
            "duration": 0,
            "status_code": 200,
        }
        self._requests_in_progress(labels).labels(*labels.values()).inc()
        self._metrics_context.set(metrics_context)

    def _process_http_response(self, status_code: int) -> None:
        metrics_context = cast(dict[str, Any], self._metrics_context.get())
        labels = metrics_context["labels"]
        self._requests_in_progress(labels).labels(*labels.values()).dec()

        request_span = metrics_context["request_span"]
        end = time.perf_counter()
        request_span["duration"] = end - request_span["start_time"]
        request_span["end_time"] = end
        labels["status_code"] = status_code
        label_values = [*labels.values()]
        extra: dict[str, Any] = {}
        if request_span["status_code"] >= 500:  # noqa: PLR2004
            self._requests_error_count(labels).labels(*label_values).inc(**extra)
        self._request_count(labels).labels(*label_values).inc(**extra)
        self._request_time(labels).labels(*label_values).observe(request_span["duration"], **extra)

    def _request_count(self, labels: Mapping[str, str | int | float]) -> Counter:
        metric_name = f"{self.config.prefix}_requests_total"

        if metric_name not in self._metrics:
            self._metrics[metric_name] = Counter(
                name=metric_name,
                documentation="Total requests",
                labelnames=[*labels.keys()],
            )

        return cast("Counter", self._metrics[metric_name])

    def _request_time(self, labels: Mapping[str, str | int | float]) -> Histogram:
        metric_name = f"{self.config.prefix}_request_duration_seconds"

        buckets = self.config.buckets or self.DEFAULT_BUCKETS

        if metric_name not in self._metrics:
            self._metrics[metric_name] = Histogram(
                name=metric_name,
                documentation="Request duration, in seconds",
                labelnames=[*labels.keys()],
                buckets=buckets,
            )
        return cast("Histogram", self._metrics[metric_name])

    def _requests_in_progress(self, labels: Mapping[str, str | int | float]) -> Gauge:
        metric_name = f"{self.config.prefix}_requests_in_progress"

        if metric_name not in self._metrics:
            self._metrics[metric_name] = Gauge(
                name=metric_name,
                documentation="Total requests currently in progress",
                labelnames=[*labels.keys()],
                multiprocess_mode="livesum",
            )
        return cast("Gauge", self._metrics[metric_name])

    def _requests_error_count(self, labels: Mapping[str, str | int | float]) -> Counter:
        metric_name = f"{self.config.prefix}_requests_error_total"

        if metric_name not in self._metrics:
            self._metrics[metric_name] = Counter(
                name=metric_name,
                documentation="Total errors in requests",
                labelnames=[*labels.keys()],
            )
        return cast("Counter", self._metrics[metric_name])

    async def on_startup(self) -> None:
        """On startup."""

    async def on_shutdown(self) -> None:
        """On shutdown."""
        if self.enabled and self.multiproc_mode:
            from prometheus_client import multiprocess

            # Maybe not only Gauge data should be deleted? (see method implementation)
            multiprocess.mark_process_dead(os.getpid())  # type: ignore

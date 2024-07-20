from __future__ import annotations

import typing
from contextlib import AsyncExitStack

import anyio
from typing_extensions import Self

from asgiext.types.asgi import Message

if typing.TYPE_CHECKING:
    from types import TracebackType

    from asgiext.types.asgi import ASGIFramework, Scope


class LifespanRuntimeError(RuntimeError):
    pass


class LifespanNotSupportedError(Exception):
    pass


class LifespanManager:
    def __init__(
        self,
        app: ASGIFramework,
        startup_timeout: float | None = 5,
        shutdown_timeout: float | None = 5,
    ) -> None:
        self._state: dict[str, typing.Any] = {}
        self.app = app
        self.startup_timeout = startup_timeout
        self.shutdown_timeout = shutdown_timeout
        self._startup_event = anyio.Event()
        self._startup_complete = anyio.Event()
        self._startup_failed = anyio.Event()
        self._shutdown_event = anyio.Event()
        self._shutdown_complete = anyio.Event()
        self._shutdown_failed = anyio.Event()
        self._failed_msg = ""
        self._send_stream, self._receive_stream = anyio.create_memory_object_stream[Message](max_buffer_size=2)
        self._receive_called = False
        self._app_exception: typing.Optional[BaseException] = None
        self._exit_stack = AsyncExitStack()

    async def startup(self) -> None:
        await self._send_stream.send({"type": "lifespan.startup"})
        with anyio.fail_after(self.startup_timeout):
            await self._startup_event.wait()

    async def shutdown(self) -> None:
        await self._send_stream.send({"type": "lifespan.shutdown"})
        with anyio.fail_after(self.shutdown_timeout):
            await self._shutdown_event.wait()

    async def receive(self) -> Message:
        self._receive_called = True
        return await self._receive_stream.receive()

    async def send(self, event: Message) -> None:
        if not self._receive_called:
            msg = (
                "Application called send() before receive(). "
                "Is it missing `assert scope['type'] == 'http'` or similar?"
            )
            raise LifespanNotSupportedError(msg)

        if event["type"] == "lifespan.startup.complete":
            self._startup_complete.set()
            self._startup_event.set()
        if event["type"] == "lifespan.startup.failed":
            self._startup_failed.set()
            self._startup_event.set()
            self._failed_msg = event["message"]
        if event["type"] == "lifespan.shutdown.complete":
            self._shutdown_complete.set()
            self._shutdown_event.set()
        if event["type"] == "lifespan.shutdown.failed":
            self._shutdown_failed.set()
            self._shutdown_event.set()
            self._failed_msg = event["message"]

    async def run_app(self) -> None:
        scope: Scope = {"type": "lifespan", "asgi": {"version": "2.0", "spec_version": ""}}

        try:
            await self.app(scope, self.receive, self.send)
        except BaseException as exc:
            self._app_exception = exc

            # We crashed, so don't make '.startup()' and '.shutdown()'
            # wait unnecessarily (or they'll timeout).
            self._startup_event.set()
            self._shutdown_event.set()

            if not self._receive_called:
                msg = (
                    "Application failed before making its first call to 'receive()'. "
                    "We expect this to originate from a statement similar to "
                    "`assert scope['type'] == 'type'`. "
                    "If that is not the case, then this crash is unexpected and "
                    "there is probably more debug output in the cause traceback."
                )
                raise LifespanNotSupportedError(msg) from exc

            raise

    async def __aenter__(self) -> Self:
        await self._exit_stack.__aenter__()
        task_group = anyio.create_task_group()
        await self._exit_stack.enter_async_context(task_group)
        task_group.start_soon(self.run_app)
        await self.startup()
        if self._startup_failed.is_set():
            msg = "Error in ASGI Lifespan"
            if self._startup_failed.is_set():
                msg += f" while startup application: {self._failed_msg}"
                raise LifespanRuntimeError(msg)
            if self._app_exception:
                msg += f" while call asgi application with lifespan scope type: {self._app_exception}"
                raise LifespanRuntimeError(msg) from self._app_exception
        return self

    async def __aexit__(
        self,
        exc_type: typing.Optional[type[BaseException]] = None,
        exc_value: typing.Optional[BaseException] = None,
        traceback: typing.Optional[TracebackType] = None,
    ) -> typing.Optional[bool]:
        self._exit_stack.push_async_callback(self.shutdown)
        await self._exit_stack.__aexit__(None, None, None)
        if exc_value is not None or self._shutdown_failed.is_set():
            if self._shutdown_failed.is_set():
                msg = f"Error in ASGI Lifespan while shutdown event handling: {self._failed_msg}"
                raise LifespanRuntimeError(msg)
            if exc_value:
                raise exc_value

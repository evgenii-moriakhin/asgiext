# ASGI types.
from __future__ import annotations

from collections.abc import Awaitable, MutableMapping
from typing import (
    Any,
    Callable,
)

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]

Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]


ASGIFramework = Callable[
    [
        Scope,
        Receive,
        Send,
    ],
    Awaitable[None],
]

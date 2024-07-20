from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Callable

import anyio
import pytest

if TYPE_CHECKING:
    import pathlib
    from collections.abc import AsyncGenerator

    from anyio.abc import TaskGroup


@pytest.fixture()
def anyio_backend():
    return "asyncio"


@pytest.fixture()
async def task_group() -> AsyncGenerator[TaskGroup, None]:
    task_group = anyio.create_task_group()
    async with task_group:
        yield task_group


@pytest.fixture()
def tmp_file_creator(tmp_path: pathlib.Path) -> Callable[[str | None], pathlib.Path]:
    def creator(extension: str | None = None) -> pathlib.Path:
        file_name = f"{uuid.uuid4()}.{extension}" if extension else str(uuid.uuid4())
        file_path = tmp_path / file_name
        file_path.touch(exist_ok=False)
        return file_path

    return creator

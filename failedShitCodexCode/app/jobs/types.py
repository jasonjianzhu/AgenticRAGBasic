from __future__ import annotations

from typing import Protocol


class EnqueuedJob(Protocol):
    id: str


class TaskQueue(Protocol):
    name: str

    def enqueue(self, func, *args, **kwargs) -> EnqueuedJob:
        ...


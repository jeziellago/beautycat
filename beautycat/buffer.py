from __future__ import annotations

from collections import deque
from typing import Iterable

from beautycat.parser import LogRecord


class RingBuffer:
    """Bounded FIFO buffer of LogRecord. Oldest dropped on overflow."""

    def __init__(self, maxlen: int = 10_000) -> None:
        if maxlen <= 0:
            raise ValueError("maxlen must be positive")
        self._dq: deque[LogRecord] = deque(maxlen=maxlen)

    @property
    def maxlen(self) -> int:
        return self._dq.maxlen or 0

    def append(self, record: LogRecord) -> None:
        self._dq.append(record)

    def extend(self, records: Iterable[LogRecord]) -> None:
        self._dq.extend(records)

    def snapshot(self) -> list[LogRecord]:
        return list(self._dq)

    def clear(self) -> None:
        self._dq.clear()

    def __len__(self) -> int:
        return len(self._dq)

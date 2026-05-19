from __future__ import annotations

import asyncio
import contextlib
from typing import Awaitable, Callable, Optional

from beautycat.adb import Adb
from beautycat.buffer import RingBuffer
from beautycat.parser import LogRecord, LogcatParser
from beautycat.resolver import PackageResolver


BatchListener = Callable[[list[LogRecord]], Awaitable[None]]


class DeviceSession:
    """One logcat stream per device. Owns the subprocess, parser, buffer, resolver."""

    def __init__(self, adb: Adb, serial: str, buffer_size: int = 10_000) -> None:
        self.adb = adb
        self.serial = serial
        self.buffer = RingBuffer(maxlen=buffer_size)
        self.parser = LogcatParser()
        self.resolver = PackageResolver(adb, serial)
        self._task: Optional[asyncio.Task] = None
        self._listeners: set[BatchListener] = set()
        self._lock = asyncio.Lock()
        self._stopped = False

    def add_listener(self, listener: BatchListener) -> None:
        self._listeners.add(listener)

    def remove_listener(self, listener: BatchListener) -> None:
        self._listeners.discard(listener)

    def snapshot(self) -> list[LogRecord]:
        return self.buffer.snapshot()

    async def clear(self) -> None:
        """Clear both the device buffer and the local ring buffer."""
        await self.adb.clear_logcat(self.serial)
        self.buffer.clear()
        self.parser = LogcatParser()

    async def start(self) -> None:
        async with self._lock:
            if self._task is not None and not self._task.done():
                return
            await self.resolver.start()
            self._stopped = False
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        async with self._lock:
            self._stopped = True
            if self._task is not None:
                self._task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._task
                self._task = None
            await self.resolver.stop()

    async def _broadcast(self, records: list[LogRecord]) -> None:
        if not records or not self._listeners:
            return
        # Snapshot listeners to allow concurrent add/remove
        listeners = list(self._listeners)
        for listener in listeners:
            try:
                await listener(records)
            except Exception:
                # Drop misbehaving listener; caller can re-add on reconnect
                self._listeners.discard(listener)

    def _annotate(self, record: LogRecord) -> None:
        if record.package is None:
            pkg = self.resolver.get(record.pid)
            if pkg:
                record.package = pkg

    async def _run(self) -> None:
        BATCH_MS = 50
        MAX_BATCH = 200
        pending: list[LogRecord] = []
        last_flush = asyncio.get_event_loop().time()

        async def flush() -> None:
            nonlocal pending, last_flush
            if not pending:
                last_flush = asyncio.get_event_loop().time()
                return
            batch = pending
            pending = []
            last_flush = asyncio.get_event_loop().time()
            await self._broadcast(batch)

        try:
            async for raw in self.adb.stream_logcat(self.serial):
                for record in self.parser.feed(raw):
                    self._annotate(record)
                    self.buffer.append(record)
                    pending.append(record)
                now = asyncio.get_event_loop().time()
                if len(pending) >= MAX_BATCH or (now - last_flush) * 1000 >= BATCH_MS:
                    await flush()
        except asyncio.CancelledError:
            raise
        except Exception:
            # Stream ended unexpectedly; flush whatever we have
            pass
        finally:
            for record in self.parser.flush():
                self._annotate(record)
                self.buffer.append(record)
                pending.append(record)
            await flush()


class SessionManager:
    """Holds DeviceSession instances keyed by serial."""

    def __init__(self, adb: Adb, buffer_size: int = 10_000) -> None:
        self.adb = adb
        self.buffer_size = buffer_size
        self._sessions: dict[str, DeviceSession] = {}
        self._lock = asyncio.Lock()

    async def get_or_create(self, serial: str) -> DeviceSession:
        async with self._lock:
            session = self._sessions.get(serial)
            if session is None:
                session = DeviceSession(self.adb, serial, buffer_size=self.buffer_size)
                self._sessions[serial] = session
            await session.start()
            return session

    async def stop_all(self) -> None:
        async with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        await asyncio.gather(*(s.stop() for s in sessions), return_exceptions=True)

from __future__ import annotations

import asyncio
import time
from typing import Optional

from beautycat.adb import Adb


class PackageResolver:
    """Maintains a cached PID -> package/process-name map for a device.

    Refreshes periodically in the background. Callers can also force a refresh.
    """

    def __init__(self, adb: Adb, serial: str, refresh_interval: float = 2.0) -> None:
        self._adb = adb
        self._serial = serial
        self._refresh_interval = refresh_interval
        self._map: dict[int, str] = {}
        self._last_refresh: float = 0.0
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    def get(self, pid: int) -> Optional[str]:
        return self._map.get(pid)

    def snapshot(self) -> dict[int, str]:
        return dict(self._map)

    async def refresh(self) -> None:
        async with self._lock:
            try:
                self._map = await self._adb.ps(self._serial)
                self._last_refresh = time.monotonic()
            except Exception:
                # Keep the previous map on failure; the device may be transient
                pass

    async def _run_loop(self) -> None:
        try:
            while True:
                await self.refresh()
                await asyncio.sleep(self._refresh_interval)
        except asyncio.CancelledError:
            return

    async def start(self) -> None:
        if self._task is None or self._task.done():
            await self.refresh()
            self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

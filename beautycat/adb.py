from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass
from typing import AsyncIterator, Optional


class AdbError(RuntimeError):
    pass


@dataclass
class Device:
    serial: str
    state: str
    model: Optional[str] = None
    product: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "serial": self.serial,
            "state": self.state,
            "model": self.model,
            "product": self.product,
        }


def resolve_adb_path(explicit: Optional[str] = None) -> str:
    if explicit:
        return explicit
    found = shutil.which("adb")
    if found:
        return found
    # Common macOS Android SDK location
    import os

    candidate = os.path.expanduser("~/Library/Android/sdk/platform-tools/adb")
    if os.path.isfile(candidate):
        return candidate
    raise AdbError("adb not found on PATH. Pass --adb-path or install platform-tools.")


class Adb:
    def __init__(self, adb_path: Optional[str] = None) -> None:
        self.adb_path = resolve_adb_path(adb_path)

    async def _run(self, *args: str, timeout: float = 10.0) -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_exec(
            self.adb_path,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            raise AdbError(f"adb {' '.join(args)} timed out")
        return proc.returncode or 0, stdout.decode("utf-8", "replace"), stderr.decode("utf-8", "replace")

    async def list_devices(self) -> list[Device]:
        code, out, err = await self._run("devices", "-l")
        if code != 0:
            raise AdbError(f"adb devices failed: {err.strip()}")
        devices: list[Device] = []
        for line in out.splitlines()[1:]:
            line = line.strip()
            if not line or line.startswith("*"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            serial, state = parts[0], parts[1]
            model = product = None
            for token in parts[2:]:
                if token.startswith("model:"):
                    model = token.split(":", 1)[1]
                elif token.startswith("product:"):
                    product = token.split(":", 1)[1]
            devices.append(Device(serial=serial, state=state, model=model, product=product))
        return devices

    async def clear_logcat(self, serial: str) -> None:
        code, _, err = await self._run("-s", serial, "logcat", "-c")
        if code != 0:
            raise AdbError(f"adb logcat -c failed: {err.strip()}")

    async def ps(self, serial: str) -> dict[int, str]:
        """Return PID -> process/package name map for the device."""
        code, out, err = await self._run(
            "-s", serial, "shell", "ps", "-A", "-o", "PID,NAME"
        )
        if code != 0:
            # Older devices may not support -A / -o; fall back to plain ps
            code, out, err = await self._run("-s", serial, "shell", "ps")
            if code != 0:
                raise AdbError(f"adb shell ps failed: {err.strip()}")
        return _parse_ps(out)

    async def stream_logcat(self, serial: str) -> AsyncIterator[str]:
        """Yield raw lines from `adb -s SERIAL logcat -v threadtime`."""
        proc = await asyncio.create_subprocess_exec(
            self.adb_path,
            "-s",
            serial,
            "logcat",
            "-v",
            "threadtime",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert proc.stdout is not None
        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                yield line.decode("utf-8", "replace")
        finally:
            if proc.returncode is None:
                try:
                    proc.terminate()
                    await asyncio.wait_for(proc.wait(), timeout=2.0)
                except (ProcessLookupError, asyncio.TimeoutError):
                    try:
                        proc.kill()
                    except ProcessLookupError:
                        pass


def _parse_ps(output: str) -> dict[int, str]:
    """Parse `ps` output, supporting both `ps -A -o PID,NAME` and legacy formats."""
    mapping: dict[int, str] = {}
    lines = output.splitlines()
    if not lines:
        return mapping

    header = lines[0].split()
    try:
        pid_idx = next(i for i, h in enumerate(header) if h.upper() == "PID")
    except StopIteration:
        pid_idx = 1  # legacy: USER PID PPID ... NAME

    for line in lines[1:]:
        parts = line.split()
        if len(parts) <= pid_idx:
            continue
        try:
            pid = int(parts[pid_idx])
        except ValueError:
            continue
        # Process name is always the last column. This works for both
        # `ps -A -o PID,NAME` and legacy `ps` (which has a free-form state column).
        mapping[pid] = parts[-1]
    return mapping

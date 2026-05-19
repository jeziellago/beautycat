from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Optional


LEVELS = ("V", "D", "I", "W", "E", "A", "F")
LEVEL_NAMES = {
    "V": "VERBOSE",
    "D": "DEBUG",
    "I": "INFO",
    "W": "WARN",
    "E": "ERROR",
    "A": "ASSERT",
    "F": "FATAL",
}

_THREADTIME_RE = re.compile(
    r"^(?P<date>\d{2}-\d{2})\s+"
    r"(?P<time>\d{2}:\d{2}:\d{2}\.\d{3})\s+"
    r"(?P<pid>\d+)\s+"
    r"(?P<tid>\d+)\s+"
    r"(?P<level>[VDIWEAF])\s+"
    r"(?P<tag>[^:]+?)\s*:\s?"
    r"(?P<message>.*)$"
)

_DIVIDER_RE = re.compile(r"^-{2,}\s*beginning of\s+\w+\s*$", re.IGNORECASE)


@dataclass
class LogRecord:
    seq: int
    date: str
    time: str
    pid: int
    tid: int
    level: str
    tag: str
    message: str
    package: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    def to_logcat_line(self) -> str:
        return f"{self.date} {self.time} {self.pid:>5} {self.tid:>5} {self.level} {self.tag}: {self.message}"


class LogcatParser:
    """Stateful parser for `adb logcat -v threadtime` output.

    Lines that don't match the threadtime format are treated as continuations
    of the previous record's message (Android stack traces produce these).
    """

    def __init__(self) -> None:
        self._seq = 0
        self._pending: Optional[LogRecord] = None

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def feed(self, line: str) -> list[LogRecord]:
        """Feed a single line. Returns zero or more completed records.

        Records emit when a new structured line arrives (closing the previous
        record) or when explicitly flushed.
        """
        line = line.rstrip("\r\n")
        out: list[LogRecord] = []

        if not line:
            return out
        if _DIVIDER_RE.match(line):
            if self._pending is not None:
                out.append(self._pending)
                self._pending = None
            return out

        m = _THREADTIME_RE.match(line)
        if m:
            if self._pending is not None:
                out.append(self._pending)
            self._pending = LogRecord(
                seq=self._next_seq(),
                date=m["date"],
                time=m["time"],
                pid=int(m["pid"]),
                tid=int(m["tid"]),
                level=m["level"],
                tag=m["tag"].strip(),
                message=m["message"],
            )
            return out

        # Continuation: append to previous message (stack traces, multiline logs)
        if self._pending is not None:
            self._pending.message = f"{self._pending.message}\n{line}"
        else:
            # Orphan line before any structured record — emit as synthetic record
            out.append(
                LogRecord(
                    seq=self._next_seq(),
                    date="",
                    time="",
                    pid=0,
                    tid=0,
                    level="I",
                    tag="logcat",
                    message=line,
                )
            )
        return out

    def flush(self) -> list[LogRecord]:
        """Emit any pending record. Call when the source stream ends."""
        if self._pending is None:
            return []
        out = [self._pending]
        self._pending = None
        return out

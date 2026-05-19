from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

from beautycat.parser import LEVELS, LogRecord


_LEVEL_RANK = {lvl: i for i, lvl in enumerate(LEVELS)}


@dataclass
class FilterSpec:
    level: str = ""            # min level: V<D<I<W<E<A<F. "" = no filter.
    tag: str = ""              # case-insensitive substring
    package: str = ""          # case-insensitive substring
    pid: Optional[int] = None  # exact match
    search: str = ""           # case-insensitive substring OR regex if regex=True
    regex: bool = False

    def __post_init__(self) -> None:
        self.level = (self.level or "").strip().upper()
        if self.level and self.level not in _LEVEL_RANK:
            self.level = ""

    def matches(self, record: LogRecord) -> bool:
        if self.level:
            if _LEVEL_RANK.get(record.level, -1) < _LEVEL_RANK[self.level]:
                return False
        if self.tag and self.tag.lower() not in record.tag.lower():
            return False
        if self.package:
            pkg = (record.package or "").lower()
            if self.package.lower() not in pkg:
                return False
        if self.pid is not None and record.pid != self.pid:
            return False
        if self.search:
            if self.regex:
                try:
                    if not re.search(self.search, record.message, re.IGNORECASE):
                        return False
                except re.error:
                    return False
            else:
                if self.search.lower() not in record.message.lower():
                    return False
        return True


def apply_filter(records: Iterable[LogRecord], spec: FilterSpec) -> list[LogRecord]:
    return [r for r in records if spec.matches(r)]

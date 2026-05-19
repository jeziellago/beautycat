from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


@dataclass
class FilterPreset:
    name: str
    level: str = ""           # one of "", V, D, I, W, E, A
    tag: str = ""             # substring match
    package: str = ""         # substring match
    search: str = ""          # plain text or regex
    regex: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "FilterPreset":
        return cls(
            name=str(data.get("name", "")).strip(),
            level=str(data.get("level", "")).strip().upper(),
            tag=str(data.get("tag", "")),
            package=str(data.get("package", "")),
            search=str(data.get("search", "")),
            regex=bool(data.get("regex", False)),
        )


def _config_dir() -> Path:
    base = os.environ.get("BEAUTYCAT_HOME")
    if base:
        return Path(base)
    return Path.home() / ".beautycat"


def _config_path() -> Path:
    return _config_dir() / "presets.json"


class PresetStore:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or _config_path()

    def load(self) -> list[FilterPreset]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        if not isinstance(data, list):
            return []
        result: list[FilterPreset] = []
        for item in data:
            if isinstance(item, dict) and item.get("name"):
                result.append(FilterPreset.from_dict(item))
        return result

    def save(self, presets: list[FilterPreset]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [p.to_dict() for p in presets]
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def upsert(self, preset: FilterPreset) -> list[FilterPreset]:
        presets = self.load()
        presets = [p for p in presets if p.name != preset.name]
        presets.append(preset)
        presets.sort(key=lambda p: p.name.lower())
        self.save(presets)
        return presets

    def delete(self, name: str) -> list[FilterPreset]:
        presets = [p for p in self.load() if p.name != name]
        self.save(presets)
        return presets

from beautycat.presets import FilterPreset, PresetStore


def test_upsert_and_load(tmp_path):
    store = PresetStore(path=tmp_path / "p.json")
    store.upsert(FilterPreset(name="errors", level="E"))
    store.upsert(FilterPreset(name="app", package="com.example"))
    loaded = store.load()
    names = sorted(p.name for p in loaded)
    assert names == ["app", "errors"]


def test_upsert_replaces_same_name(tmp_path):
    store = PresetStore(path=tmp_path / "p.json")
    store.upsert(FilterPreset(name="x", level="I"))
    store.upsert(FilterPreset(name="x", level="E"))
    loaded = store.load()
    assert len(loaded) == 1
    assert loaded[0].level == "E"


def test_delete(tmp_path):
    store = PresetStore(path=tmp_path / "p.json")
    store.upsert(FilterPreset(name="a"))
    store.upsert(FilterPreset(name="b"))
    store.delete("a")
    names = [p.name for p in store.load()]
    assert names == ["b"]


def test_load_returns_empty_when_file_missing(tmp_path):
    store = PresetStore(path=tmp_path / "missing.json")
    assert store.load() == []


def test_corrupted_file_returns_empty(tmp_path):
    path = tmp_path / "p.json"
    path.write_text("not json", encoding="utf-8")
    store = PresetStore(path=path)
    assert store.load() == []


def test_from_dict_normalizes():
    p = FilterPreset.from_dict({"name": " test ", "level": "e", "regex": "yes"})
    assert p.name == "test"
    assert p.level == "E"
    assert p.regex is True

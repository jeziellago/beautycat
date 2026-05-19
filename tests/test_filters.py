from beautycat.filters import FilterSpec, apply_filter
from beautycat.parser import LogRecord


def rec(seq, level="I", tag="X", pid=100, tid=200, message="hello", package=None):
    return LogRecord(
        seq=seq, date="05-18", time="00:00:00.000", pid=pid, tid=tid,
        level=level, tag=tag, message=message, package=package,
    )


def test_level_filter_inclusive_min():
    records = [rec(1, "V"), rec(2, "I"), rec(3, "W"), rec(4, "E")]
    out = apply_filter(records, FilterSpec(level="W"))
    assert [r.seq for r in out] == [3, 4]


def test_invalid_level_is_ignored():
    records = [rec(1, "I"), rec(2, "E")]
    out = apply_filter(records, FilterSpec(level="zzz"))
    assert len(out) == 2


def test_tag_filter_is_case_insensitive_substring():
    records = [rec(1, tag="ActivityManager"), rec(2, tag="Zygote")]
    out = apply_filter(records, FilterSpec(tag="activity"))
    assert [r.seq for r in out] == [1]


def test_package_filter_handles_missing_package():
    records = [
        rec(1, package="com.example.app"),
        rec(2, package=None),
        rec(3, package="com.other"),
    ]
    out = apply_filter(records, FilterSpec(package="example"))
    assert [r.seq for r in out] == [1]


def test_pid_filter_exact():
    records = [rec(1, pid=100), rec(2, pid=200)]
    out = apply_filter(records, FilterSpec(pid=200))
    assert [r.seq for r in out] == [2]


def test_search_substring_case_insensitive():
    records = [rec(1, message="Connection OPEN"), rec(2, message="closed")]
    out = apply_filter(records, FilterSpec(search="open"))
    assert [r.seq for r in out] == [1]


def test_search_regex():
    records = [rec(1, message="value=42"), rec(2, message="value=ab")]
    out = apply_filter(records, FilterSpec(search=r"value=\d+", regex=True))
    assert [r.seq for r in out] == [1]


def test_invalid_regex_filters_everything_out():
    records = [rec(1, message="x"), rec(2, message="y")]
    out = apply_filter(records, FilterSpec(search="[unclosed", regex=True))
    assert out == []


def test_combination_all_filters():
    records = [
        rec(1, level="E", tag="ActivityManager", pid=100, package="com.example.app",
            message="crash here"),
        rec(2, level="E", tag="ActivityManager", pid=200, package="com.example.app",
            message="crash here"),
        rec(3, level="W", tag="ActivityManager", pid=100, package="com.example.app",
            message="crash here"),
    ]
    spec = FilterSpec(level="E", tag="Activity", package="example", pid=100, search="crash")
    out = apply_filter(records, spec)
    assert [r.seq for r in out] == [1]

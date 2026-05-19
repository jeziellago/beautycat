import pytest

from beautycat.buffer import RingBuffer
from beautycat.parser import LogRecord


def make(seq):
    return LogRecord(
        seq=seq, date="", time="", pid=0, tid=0, level="I", tag="t", message=f"m{seq}"
    )


def test_invalid_maxlen():
    with pytest.raises(ValueError):
        RingBuffer(0)


def test_drops_oldest_on_overflow():
    buf = RingBuffer(maxlen=3)
    for i in range(5):
        buf.append(make(i))
    snap = buf.snapshot()
    assert [r.seq for r in snap] == [2, 3, 4]
    assert len(buf) == 3


def test_snapshot_is_a_copy():
    buf = RingBuffer(maxlen=10)
    buf.append(make(1))
    snap = buf.snapshot()
    snap.clear()
    assert len(buf) == 1


def test_clear():
    buf = RingBuffer(maxlen=10)
    for i in range(3):
        buf.append(make(i))
    buf.clear()
    assert len(buf) == 0
    assert buf.snapshot() == []


def test_extend():
    buf = RingBuffer(maxlen=10)
    buf.extend(make(i) for i in range(4))
    assert [r.seq for r in buf.snapshot()] == [0, 1, 2, 3]

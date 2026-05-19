from beautycat.parser import LogcatParser


def test_parses_threadtime_line():
    parser = LogcatParser()
    records = parser.feed("05-18 23:32:33.884   849   913 I libPerfCtl: xgfGetFPS pid:2276 fps:-1")
    records += parser.flush()
    assert len(records) == 1
    r = records[0]
    assert r.date == "05-18"
    assert r.time == "23:32:33.884"
    assert r.pid == 849
    assert r.tid == 913
    assert r.level == "I"
    assert r.tag == "libPerfCtl"
    assert r.message == "xgfGetFPS pid:2276 fps:-1"


def test_assigns_increasing_seqs():
    parser = LogcatParser()
    parser.feed("05-18 23:32:33.884   849   913 I A: m1")
    parser.feed("05-18 23:32:33.885   849   913 I A: m2")
    out = parser.feed("05-18 23:32:33.886   849   913 I A: m3") + parser.flush()
    seqs = [r.seq for r in out]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)


def test_continuation_lines_append_to_previous_message():
    parser = LogcatParser()
    parser.feed("05-18 23:32:33.884   849   913 E AndroidRuntime: FATAL EXCEPTION: main")
    parser.feed("        at com.example.Foo.bar(Foo.java:10)")
    parser.feed("        at com.example.Foo.baz(Foo.java:20)")
    records = parser.feed("05-18 23:32:33.885   849   913 I libPerfCtl: ok") + parser.flush()
    # First record now contains all three lines
    assert records[0].tag == "AndroidRuntime"
    assert "at com.example.Foo.bar" in records[0].message
    assert "at com.example.Foo.baz" in records[0].message
    # Second record is the I libPerfCtl
    assert records[1].tag == "libPerfCtl"


def test_skips_divider_lines():
    parser = LogcatParser()
    out = parser.feed("--------- beginning of main")
    out += parser.feed("05-18 23:32:33.884   849   913 I A: m1") + parser.flush()
    assert len(out) == 1
    assert out[0].message == "m1"


def test_tag_with_colon_in_message():
    parser = LogcatParser()
    records = parser.feed(
        "05-18 23:32:34.223   910   910 I BufferQueueProducer: [SurfaceView] queueBuffer: fps=89.96"
    ) + parser.flush()
    assert len(records) == 1
    assert records[0].tag == "BufferQueueProducer"
    assert records[0].message == "[SurfaceView] queueBuffer: fps=89.96"


def test_to_logcat_line_roundtrip_shape():
    parser = LogcatParser()
    rec = (parser.feed("05-18 23:32:33.884   849   913 I libPerfCtl: hello") + parser.flush())[0]
    line = rec.to_logcat_line()
    assert "05-18 23:32:33.884" in line
    assert "I libPerfCtl: hello" in line


def test_flush_emits_pending():
    parser = LogcatParser()
    out = parser.feed("05-18 23:32:33.884   849   913 I A: m1")
    assert out == []  # not yet emitted, still pending
    flushed = parser.flush()
    assert len(flushed) == 1
    assert flushed[0].message == "m1"


def test_orphan_continuation_before_any_record():
    parser = LogcatParser()
    out = parser.feed("some-bare-line")
    assert len(out) == 1
    assert out[0].tag == "logcat"
    assert out[0].message == "some-bare-line"

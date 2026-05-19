from beautycat.adb import _parse_ps


PS_A_O_PID_NAME = """\
   PID NAME
     1 init
   849 surfaceflinger
   910 system_server
  2276 com.example.app
"""

PS_LEGACY = """\
USER       PID  PPID  VSIZE  RSS   WCHAN              PC  NAME
root         1     0   2104   608  SyS_epoll_ 00000000 S init
system     849     1  12345  4567  SyS_epoll_ 00000000 S surfaceflinger
"""


def test_parses_pid_name_columns():
    out = _parse_ps(PS_A_O_PID_NAME)
    assert out[1] == "init"
    assert out[849] == "surfaceflinger"
    assert out[2276] == "com.example.app"


def test_parses_legacy_ps_format():
    out = _parse_ps(PS_LEGACY)
    assert out[1] == "init"
    assert out[849] == "surfaceflinger"


def test_skips_unparseable_lines():
    out = _parse_ps("PID NAME\nbroken line\n  42 ok\n")
    assert out == {42: "ok"}


def test_empty_output():
    assert _parse_ps("") == {}

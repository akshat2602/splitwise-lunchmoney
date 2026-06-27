from swlm.state import StateStore


def test_cursor_roundtrip(tmp_path):
    s = StateStore(tmp_path / "s.db")
    assert s.get_cursor() is None
    s.set_cursor("2026-06-01T00:00:00Z")
    assert s.get_cursor() == "2026-06-01T00:00:00Z"


def test_cursor_overwrites(tmp_path):
    s = StateStore(tmp_path / "s.db")
    s.set_cursor("a")
    s.set_cursor("b")
    assert s.get_cursor() == "b"


def test_last_run_roundtrip(tmp_path):
    s = StateStore(tmp_path / "s.db")
    assert s.get_last_run() is None
    s.set_last_run("2026-06-27T10:00:00Z")
    assert s.get_last_run() == "2026-06-27T10:00:00Z"


def test_survives_reopen(tmp_path):
    path = tmp_path / "s.db"
    s = StateStore(path)
    s.set_cursor("persisted")
    s.close()
    assert StateStore(path).get_cursor() == "persisted"

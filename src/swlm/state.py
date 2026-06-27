"""Disposable local cache (SQLite): just the cursor and last-run timestamp.

Deliberately holds NO correctness-critical data. Lunch Money's external_id map is the source of
truth for what we've written, so losing or corrupting this file only costs a wider re-scan on
the next run — never a duplicate or a wrong balance. See ``runner`` for why.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

_CURSOR_KEY = "cursor"
_LAST_RUN_KEY = "last_run"


class StateStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def _get(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def _set(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._conn.commit()

    def get_cursor(self) -> str | None:
        return self._get(_CURSOR_KEY)

    def set_cursor(self, value: str) -> None:
        self._set(_CURSOR_KEY, value)

    def get_last_run(self) -> str | None:
        return self._get(_LAST_RUN_KEY)

    def set_last_run(self, value: str) -> None:
        self._set(_LAST_RUN_KEY, value)

    def close(self) -> None:
        self._conn.close()

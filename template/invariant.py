"""Runtime invariant — how this module knows its own data is broken.

Assert a relationship you own, not that a function exists. "tool_add_note is
defined" is a static fact that is always true; it can never go red because a
user's data got corrupted. These can:

  1. the recorded schema version matches the code
  2. every stored note still has a non-empty body

Never raise. A reporter that throws is worse than no reporter — the caller
cannot tell "checked and fine" from "the check itself broke".
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

EXPECTED_SCHEMA = "1"


def check(home: Path) -> list[str]:
    failures: list[str] = []
    db = Path(home) / "module-data" / "example-module" / "notes.sqlite3"
    if not db.exists():
        return failures  # nothing created yet is not broken

    conn = None
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        if row is None:
            failures.append("meta table has no schema_version — migration may have stopped halfway")
        elif str(row["value"]) != EXPECTED_SCHEMA:
            failures.append(
                f"schema_version mismatch: database {row['value']!r} vs code {EXPECTED_SCHEMA!r}")
        for note in conn.execute("SELECT id, body FROM notes"):
            if not str(note["body"] or "").strip():
                failures.append(f"note #{note['id']} has an empty body — it was rejected on write")
    except Exception as exc:
        failures.append(f"the invariant check itself failed: {type(exc).__name__}: {exc}")
    finally:
        if conn is not None:
            conn.close()
    return failures

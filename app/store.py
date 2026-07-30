"""SQLite persistence.

One table, one JSON column for the submission, and the state kept in its own
column because that is what the state machine reads and writes. The database
path is injected, so a test gets a fresh file per test and the service has no
global state to leak between cases.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from app.domain import State
from app.models import ChangeRecord, ChangeSubmission

SCHEMA = """
CREATE TABLE IF NOT EXISTS changes (
    id          TEXT PRIMARY KEY,
    state       TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    submission  TEXT NOT NULL
);
"""


class Store:
    """A connection to one change database."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.executescript(SCHEMA)
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def create(
        self,
        change_id: str,
        submission: ChangeSubmission,
        now: datetime,
    ) -> ChangeRecord:
        """Insert a new record in Draft (REQ-2, first state)."""
        stamp = now.isoformat()
        self._connection.execute(
            "INSERT INTO changes (id, state, created_at, updated_at, submission)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                change_id,
                State.DRAFT.value,
                stamp,
                stamp,
                submission.model_dump_json(),
            ),
        )
        self._connection.commit()
        record = self.get(change_id)
        assert record is not None  # noqa: S101 - just inserted
        return record

    def get(self, change_id: str) -> ChangeRecord | None:
        """Read one record, or None."""
        row = self._connection.execute(
            "SELECT id, state, created_at, updated_at, submission FROM changes"
            " WHERE id = ?",
            (change_id,),
        ).fetchone()
        if row is None:
            return None
        return ChangeRecord(
            id=row["id"],
            state=State(row["state"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            submission=ChangeSubmission.model_validate(json.loads(row["submission"])),
        )

    def set_state(self, change_id: str, state: State, now: datetime) -> ChangeRecord:
        """Write a new state. The caller has already checked it is legal."""
        self._connection.execute(
            "UPDATE changes SET state = ?, updated_at = ? WHERE id = ?",
            (state.value, now.isoformat(), change_id),
        )
        self._connection.commit()
        record = self.get(change_id)
        assert record is not None  # noqa: S101 - just updated
        return record

    def count(self) -> int:
        """Number of records held. Used by tests to prove isolation."""
        return int(self._connection.execute("SELECT COUNT(*) FROM changes").fetchone()[0])

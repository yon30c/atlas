# SQLite compatibility

Atlas requires SQLite **3.26.0 or newer** for its SQLite persistence adapter.

The minimum is chosen because Atlas enables `PRAGMA foreign_keys = ON` on every
connection and migrations rebuild and rename tables that participate in foreign
key relationships. SQLite 3.26.0 is the baseline from which table renames update
foreign key references regardless of the `foreign_keys` setting. Atlas still
enables foreign key enforcement explicitly and verifies the configured setting.

The identity schema also uses deferred foreign key constraints so the reciprocal
`identity_records` and `atlas_users` rows can be written in one transaction and
validated together at commit.

Check the runtime linked to Python with:

```bash
python -c "import sqlite3; print(sqlite3.sqlite_version)"
```

The GitHub Actions test matrix checks the linked SQLite runtime against the
minimum before running the unit test suite. The unit tests additionally inspect
the reciprocal foreign key definitions after the v6 table rebuild and run
`PRAGMA foreign_key_check`.

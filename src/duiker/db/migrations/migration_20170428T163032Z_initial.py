"""
Create history table and FTS tables.
"""

__bump_version__ = True


def apply(connection):
    connection.executescript("""
CREATE TABLE IF NOT EXISTS history (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    command   TEXT NOT NULL,
              UNIQUE (timestamp, command) ON CONFLICT REPLACE
);

CREATE VIRTUAL TABLE IF NOT EXISTS fts_history USING fts4(history_id, command);

CREATE VIRTUAL TABLE IF NOT EXISTS fts_history_terms USING fts4aux(fts_history);
""")

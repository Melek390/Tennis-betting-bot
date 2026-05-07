import csv
import io
import sqlite3
from datetime import datetime, timezone

BETS_DB_KEY = "bets_db"

RULE_LABELS: dict[str, str] = {
    "r1": "Rule 1 — Break Point / Advantage",
    "r2": "Rule 2 — Kalshi Spike Fade",
    "r3": "Rule 3 — Back Fav after Set Loss",
}

_TABLES = {
    "r1": "bets_r1",
    "r2": "bets_r2",
    "r3": "bets_r3",
}

_CREATE = """
CREATE TABLE IF NOT EXISTS {table} (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,
    player      TEXT    NOT NULL,
    match       TEXT    NOT NULL,
    entry_price REAL    NOT NULL,
    exit_price  REAL,
    pnl         REAL,
    exit_reason TEXT,
    match_state TEXT
)
"""


class BetsDB:
    def __init__(self, path: str = "bets.db"):
        self._path = path
        self._init()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._conn() as conn:
            for table in _TABLES.values():
                conn.execute(_CREATE.format(table=table))
            # Migration: add match_state column to existing tables that predate it
            for table in _TABLES.values():
                try:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN match_state TEXT")
                except sqlite3.OperationalError:
                    pass  # column already exists
            conn.commit()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def log_exit(
        self,
        rule: str,                      # "r1", "r2", "r3"
        player: str,
        match: str,
        entry_price: float,
        exit_price: float | None,
        reason: str,
        match_state: str | None = None, # only populated for R2
    ) -> None:
        table = _TABLES.get(rule)
        if table is None:
            return
        pnl = round((exit_price - entry_price) * 100, 2) if exit_price is not None else None
        ts  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        with self._conn() as conn:
            conn.execute(
                f"INSERT INTO {table} "
                "(timestamp, player, match, entry_price, exit_price, pnl, exit_reason, match_state) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (ts, player, match, entry_price, exit_price, pnl, reason, match_state),
            )
            conn.commit()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_stats(self, rule: str) -> dict:
        table = _TABLES.get(rule, "bets_r1")
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM {table} ORDER BY timestamp DESC"
            ).fetchall()
        total     = len(rows)
        wins      = sum(1 for r in rows if r["pnl"] is not None and r["pnl"] > 0)
        losses    = sum(1 for r in rows if r["pnl"] is not None and r["pnl"] <= 0)
        total_pnl = round(sum(r["pnl"] for r in rows if r["pnl"] is not None), 2)
        last5     = [dict(r) for r in rows[:5]]
        return {
            "total":     total,
            "wins":      wins,
            "losses":    losses,
            "total_pnl": total_pnl,
            "last5":     last5,
        }

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_csv(self, rule: str) -> io.BytesIO:
        table = _TABLES.get(rule, "bets_r1")
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT timestamp, player, match, entry_price, exit_price, pnl, exit_reason, match_state "
                f"FROM {table} ORDER BY timestamp DESC"
            ).fetchall()
        sio = io.StringIO()
        writer = csv.writer(sio)
        writer.writerow([
            "timestamp", "player", "match",
            "entry_price", "exit_price", "pnl_cents", "exit_reason", "match_state",
        ])
        for row in rows:
            writer.writerow([
                row["timestamp"], row["player"], row["match"],
                row["entry_price"], row["exit_price"], row["pnl"],
                row["exit_reason"], row["match_state"],
            ])
        return io.BytesIO(sio.getvalue().encode("utf-8"))

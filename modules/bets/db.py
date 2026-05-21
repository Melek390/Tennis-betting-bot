import csv
import io
import json
import sqlite3
from datetime import datetime, timezone

BETS_DB_KEY = "bets_db"

RULE_LABELS: dict[str, str] = {
    "r2": "Rule 2 — Kalshi Spike Fade",
    "r3": "Rule 3 — Back Fav after Set Loss",
    "r4": "Rule 4 — Set 1 Winner Spike Fade",
}

_TABLES = {
    "r2": "bets_r2",
    "r3": "bets_r3",
    "r4": "bets_r4",
}

_CREATE = """
CREATE TABLE IF NOT EXISTS {table} (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp          TEXT    NOT NULL,
    player             TEXT    NOT NULL,
    match              TEXT    NOT NULL,
    entry_price        REAL    NOT NULL,
    exit_price         REAL,
    pnl                REAL,
    exit_reason        TEXT,
    match_state_entry  TEXT,
    match_state_exit   TEXT,
    entry_ask          REAL,
    entry_spread       REAL,
    entry_drop         INTEGER,
    entry_prev_ask     REAL,
    entry_serving      TEXT,
    entry_set_score    TEXT,
    entry_game_score   TEXT,
    entry_break_game   INTEGER,
    exit_ask           REAL,
    exit_time          TEXT,
    hold_seconds       REAL,
    ticks              TEXT,
    post_ticks         TEXT
)
"""

_MIGRATIONS = [
    "ALTER TABLE {table} ADD COLUMN match_state TEXT",        # legacy — kept for old rows
    "ALTER TABLE {table} ADD COLUMN match_state_entry TEXT",
    "ALTER TABLE {table} ADD COLUMN match_state_exit TEXT",
    "ALTER TABLE {table} ADD COLUMN entry_ask REAL",
    "ALTER TABLE {table} ADD COLUMN entry_spread REAL",
    "ALTER TABLE {table} ADD COLUMN entry_drop INTEGER",
    "ALTER TABLE {table} ADD COLUMN entry_prev_ask REAL",
    "ALTER TABLE {table} ADD COLUMN entry_serving TEXT",
    "ALTER TABLE {table} ADD COLUMN entry_set_score TEXT",
    "ALTER TABLE {table} ADD COLUMN entry_game_score TEXT",
    "ALTER TABLE {table} ADD COLUMN entry_break_game INTEGER",
    "ALTER TABLE {table} ADD COLUMN exit_ask REAL",
    "ALTER TABLE {table} ADD COLUMN exit_time TEXT",
    "ALTER TABLE {table} ADD COLUMN hold_seconds REAL",
    "ALTER TABLE {table} ADD COLUMN ticks TEXT",
    "ALTER TABLE {table} ADD COLUMN post_ticks TEXT",
]

_CSV_COLUMNS = [
    "timestamp", "player", "match",
    "entry_price", "exit_price", "pnl_cents",
    "exit_reason", "match_state_entry", "match_state_exit",
    "entry_ask", "entry_spread", "entry_drop", "entry_prev_ask",
    "entry_serving", "entry_set_score", "entry_game_score", "entry_break_game",
    "exit_ask", "exit_time", "hold_seconds",
    "ticks", "post_ticks",
]


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
            for table in _TABLES.values():
                for migration in _MIGRATIONS:
                    try:
                        conn.execute(migration.format(table=table))
                    except sqlite3.OperationalError:
                        pass  # column already exists
            conn.commit()

    # ------------------------------------------------------------------
    # Write — R3
    # ------------------------------------------------------------------

    def log_exit(
        self,
        rule: str,
        player: str,
        match: str,
        entry_price: float,
        exit_price: float | None,
        reason: str,
        match_state_entry: str | None = None,
        match_state_exit: str | None = None,
    ) -> None:
        table = _TABLES.get(rule)
        if table is None:
            return
        pnl = round((exit_price - entry_price) * 100, 2) if exit_price is not None else None
        ts  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        with self._conn() as conn:
            conn.execute(
                f"INSERT INTO {table} "
                "(timestamp, player, match, entry_price, exit_price, pnl, exit_reason, "
                "match_state_entry, match_state_exit) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (ts, player, match, entry_price, exit_price, pnl, reason,
                 match_state_entry, match_state_exit),
            )
            conn.commit()

    # ------------------------------------------------------------------
    # Write — R2 (full LOG data including all 22 fields)
    # ------------------------------------------------------------------

    def log_exit_r2(
        self,
        market_title: str,
        log_data: dict,
        match_state_entry: str | None = None,
        rule: str = "r2",
    ) -> None:
        table = _TABLES.get(rule, "bets_r2")
        entry_mid  = log_data.get("entry_mid")
        exit_mid   = log_data.get("exit_mid")
        entry_time = log_data.get("entry_time")
        exit_time  = log_data.get("exit_time")

        pnl = round((exit_mid - entry_mid) * 100, 2) if exit_mid is not None and entry_mid is not None else None

        hold_seconds = None
        if entry_time and exit_time:
            hold_seconds = round((exit_time - entry_time).total_seconds(), 1)

        ts       = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        exit_ts  = exit_time.strftime("%Y-%m-%d %H:%M:%S UTC") if exit_time else None

        ticks_json      = json.dumps(log_data.get("ticks", []))
        post_ticks_json = json.dumps(log_data.get("post_ticks", []))

        with self._conn() as conn:
            conn.execute(
                f"INSERT INTO {table} "
                "(timestamp, player, match, entry_price, exit_price, pnl, exit_reason, "
                "match_state_entry, match_state_exit, "
                "entry_ask, entry_spread, entry_drop, entry_prev_ask, "
                "entry_serving, entry_set_score, entry_game_score, entry_break_game, "
                "exit_ask, exit_time, hold_seconds, ticks, post_ticks) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    ts, market_title, market_title,
                    entry_mid, exit_mid, pnl,
                    log_data.get("exit_reason", ""),
                    match_state_entry,
                    log_data.get("match_state_exit"),
                    log_data.get("entry_ask"),
                    log_data.get("entry_spread"),
                    log_data.get("entry_drop"),
                    log_data.get("entry_prev_ask"),
                    log_data.get("entry_serving"),
                    log_data.get("entry_set_score"),
                    log_data.get("entry_game_score"),
                    log_data.get("entry_break_game"),
                    log_data.get("exit_ask"),
                    exit_ts,
                    hold_seconds,
                    ticks_json,
                    post_ticks_json,
                ),
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
                f"SELECT timestamp, player, match, entry_price, exit_price, pnl, "
                f"exit_reason, match_state_entry, match_state_exit, "
                f"entry_ask, entry_spread, entry_drop, entry_prev_ask, "
                f"entry_serving, entry_set_score, entry_game_score, entry_break_game, "
                f"exit_ask, exit_time, hold_seconds, ticks, post_ticks "
                f"FROM {table} ORDER BY timestamp DESC"
            ).fetchall()
        sio = io.StringIO()
        writer = csv.writer(sio)
        writer.writerow(_CSV_COLUMNS)
        for row in rows:
            writer.writerow([
                row["timestamp"], row["player"], row["match"],
                row["entry_price"], row["exit_price"], row["pnl"],
                row["exit_reason"], row["match_state_entry"], row["match_state_exit"],
                row["entry_ask"], row["entry_spread"], row["entry_drop"], row["entry_prev_ask"],
                row["entry_serving"], row["entry_set_score"], row["entry_game_score"], row["entry_break_game"],
                row["exit_ask"], row["exit_time"], row["hold_seconds"],
                row["ticks"], row["post_ticks"],
            ])
        return io.BytesIO(sio.getvalue().encode("utf-8"))

from dataclasses import dataclass
from datetime import datetime, timezone


def _c(p: float | None) -> str:
    return f"{round(p * 100)}¢" if p is not None else "—"


def _pnl(exit_p: float | None, entry_p: float | None) -> str:
    if exit_p is None or entry_p is None:
        return "—"
    d = round((exit_p - entry_p) * 100)
    return f"+{d}¢" if d > 0 else f"{d}¢"


def _fmt_ts(ts: datetime | None) -> str:
    return ts.strftime("%H:%M:%S") if ts else "—"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S UTC")


@dataclass
class Signal:
    rule: str                     # "R2", "R3"
    kind: str                     # "ENTRY", "EXIT", "RE-ENTRY"
    context: str                  # match / player / market identifier
    detail: str = ""              # optional second line
    entry_price: float | None = None
    exit_price: float | None = None
    reason: str = ""

    def render(self) -> str:
        lines = [f"<b>{self.rule} · {self.kind}</b>  {self.context}"]
        if self.detail:
            lines.append(self.detail)
        if self.kind != "EXIT":
            lines.append(f"Entry: {_c(self.entry_price)}")
        else:
            lines.append(self.reason or "Condition no longer met")
            lines.append(
                f"Entry: {_c(self.entry_price)} → Exit: {_c(self.exit_price)}"
                f"  |  P&L: <b>{_pnl(self.exit_price, self.entry_price)}</b>"
            )
        lines.append(f"<i>{_now()}</i>")
        return "\n".join(lines)


def log_r2_text(market_title: str, log: dict) -> str:
    entry_time      = log.get("entry_time")
    entry_ask       = log.get("entry_ask")
    entry_mid       = log.get("entry_mid")
    entry_spread    = log.get("entry_spread")
    entry_drop      = log.get("entry_drop")     # int (¢) or None
    entry_prev_ask  = log.get("entry_prev_ask")
    entry_serving   = log.get("entry_serving", "")
    entry_set_score = log.get("entry_set_score", "")
    entry_game_score = log.get("entry_game_score", "")
    entry_break_game = log.get("entry_break_game")
    ticks           = log.get("ticks", [])
    exit_time       = log.get("exit_time")
    exit_ask        = log.get("exit_ask")
    exit_mid        = log.get("exit_mid")
    exit_reason     = log.get("exit_reason", "")
    post_ticks      = log.get("post_ticks", [])

    # Hold duration
    hold_str = "—"
    if entry_time and exit_time:
        secs = (exit_time - entry_time).total_seconds()
        hold_str = f"{int(secs // 60)}m {int(secs % 60)}s"

    # P&L
    pnl_val = round((exit_mid - entry_mid) * 100) if exit_mid is not None and entry_mid is not None else None
    pnl_str = (f"+{pnl_val}¢" if pnl_val and pnl_val > 0 else f"{pnl_val}¢") if pnl_val is not None else "—"

    lines = [
        "<b>R2 LOG — Spike Fade</b>",
        f"{market_title} · ENTRY",
        "",
        f"Entry {_fmt_ts(entry_time)} UTC",
    ]

    # Price line
    drop_str   = f"{entry_drop}¢" if entry_drop is not None else "—"
    spread_str = f"{round(entry_spread * 100)}¢" if entry_spread is not None else "—"
    lines.append(
        f"Ask {_c(entry_ask)} · Mid {_c(entry_mid)} · Spread {spread_str} · Drop {drop_str} · Pre-drop {_c(entry_prev_ask)}"
    )

    # Tennis state at entry
    tennis_parts = []
    if entry_serving:
        tennis_parts.append(f"Serving: {entry_serving}")
    if entry_set_score:
        tennis_parts.append(f"Set {entry_set_score}")
    if entry_game_score:
        tennis_parts.append(f"Game {entry_game_score}")
    if entry_break_game is not None:
        tennis_parts.append(f"Spike at set game #{entry_break_game + 1}")
    if tennis_parts:
        lines.append(" · ".join(tennis_parts))

    lines.append("")

    # In-position ticks
    for i, t in enumerate(ticks, 1):
        parts = [f"T{i} Mid {_c(t['mid'])}"]
        if t.get("serving"):
            parts.append(f"Serving: {t['serving']}")
        if t.get("set_score"):
            parts.append(f"Set {t['set_score']}")
        if t.get("game_score"):
            parts.append(f"Game {t['game_score']}")
        parts.append(f"2nd break: {'Yes' if t.get('second_break') else 'No'}")
        lines.append(" · ".join(parts))

    lines.append("")
    lines.append(f"Exit {_fmt_ts(exit_time)} UTC · Hold {hold_str}")
    lines.append(f"Ask {_c(exit_ask)} · Mid {_c(exit_mid)} · Reason: {exit_reason or '—'}")

    if post_ticks:
        lines.append("")
        for i, t in enumerate(post_ticks, 1):
            parts = [f"T+{i} Mid {_c(t['mid'])}"]
            if t.get("set_score"):
                parts.append(f"Set {t['set_score']}")
            if t.get("game_score"):
                parts.append(f"Game {t['game_score']}")
            lines.append(" · ".join(parts))

    lines.append("")
    lines.append(f"P&L <b>{pnl_str}</b>")

    return "\n".join(lines)


def heartbeat_text(
    match_count: int,
    enabled_r2: bool = True,
    enabled_r3: bool = True,
) -> str:
    matches_line = (
        f"{match_count} live match{'es' if match_count != 1 else ''}"
        if match_count else "No live matches"
    )
    return (
        f"<b>Heartbeat</b>\n\n"
        f"<b>Tennis API:</b> {matches_line}\n"
        f"<b>Rule 2:</b> {'ON' if enabled_r2 else 'OFF'}\n"
        f"<b>Rule 3:</b> {'ON' if enabled_r3 else 'OFF'}\n"
        f"<i>{_now()}</i>"
    )


def error_text(message: str) -> str:
    return (
        f"<b>BOT ERROR</b>\n\n"
        f"{message}\n"
        f"<i>{_now()}</i>"
    )

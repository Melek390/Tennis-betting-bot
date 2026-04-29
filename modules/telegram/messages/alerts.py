from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S UTC")

def _fmt_ts(ts: datetime | None) -> str:
    return ts.strftime("%H:%M:%S UTC") if ts else "—"

def _c(price: float | None) -> str:
    return f"{round(price * 100)}¢" if price is not None else "—"

def _diff(a: float | None, b: float | None) -> str:
    if a is None or b is None:
        return ""
    d = round((a - b) * 100)
    return f"  (+{d}¢)" if d > 0 else f"  ({d}¢)" if d < 0 else "  (0¢)"


def entry_text(
    player: str, match: str, score: str, price: float,
    detail: str = "", spread: float | None = None,
) -> str:
    price_line = f"<b>Price:</b> {_c(price)}"
    if spread is not None:
        mid = price - spread / 2
        price_line += f"  |  Mid: {_c(mid)}  |  Slippage: ~{round(spread / 2 * 100)}¢"
    return (
        f"<b>ENTRY — Rule 5</b>\n"
        f"<i>{detail}</i>\n\n"
        f"<b>Match:</b> {match}\n"
        f"<b>Player:</b> {player}\n"
        f"<b>Score:</b> {score}\n"
        f"{price_line}\n"
        f"<i>{_now()}</i>"
    )


def exit_text(
    player: str, match: str, score: str,
    exit_price: float | None = None,
    stats: dict | None = None,
    exit_reason: str | None = None,
) -> str:
    reason = exit_reason or "Condition no longer met"

    ep   = stats.get("entry_price")     if stats else None
    e_ts = stats.get("entry_timestamp") if stats else None

    pnl = round((exit_price - ep) * 100) if (exit_price is not None and ep is not None) else None
    pnl_str = (f"+{pnl}¢" if pnl > 0 else f"{pnl}¢") if pnl is not None else "—"

    text = (
        f"<b>EXIT — Rule 5</b>\n\n"
        f"<b>Match:</b> {match}\n"
        f"<b>Player:</b> {player}\n"
        f"<b>Score:</b> {score}\n"
        f"<b>Reason:</b> {reason}\n\n"
        f"<b>Entry:</b> {_c(ep)} @ {_fmt_ts(e_ts)}\n"
        f"<b>Exit:</b>  {_c(exit_price)} @ {_now()}\n"
        f"<b>P&L:</b>   {pnl_str}"
    )

    if stats:
        e_st   = stats.get("entry_state", "")
        spread = stats.get("entry_spread")
        ticks  = stats.get("price_after_tick", [])

        if e_st:
            text += f"\n<b>State at entry:</b> {e_st}"
        for i, tp in enumerate(ticks[:2], 1):
            text += f"\n<b>Tick {i}:</b> {_c(tp)}{_diff(tp, ep)}"
        if spread is not None and ep is not None:
            mid = ep - spread / 2
            text += f"\n<b>Mid at entry:</b> {_c(mid)}  |  Slippage: ~{round(spread/2*100)}¢"

    return text


def reentry_text(
    player: str, match: str, score: str, price: float,
    detail: str = "", spread: float | None = None,
) -> str:
    price_line = f"<b>Price:</b> {_c(price)}"
    if spread is not None:
        mid = price - spread / 2
        price_line += f"  |  Mid: {_c(mid)}  |  Slippage: ~{round(spread / 2 * 100)}¢"
    return (
        f"<b>RE-ENTRY — Rule 5</b>\n"
        f"<i>{detail}</i>\n\n"
        f"<b>Match:</b> {match}\n"
        f"<b>Player:</b> {player}\n"
        f"<b>Score:</b> {score}\n"
        f"{price_line}\n"
        f"<i>{_now()}</i>"
    )


def heartbeat_text(match_count: int, enabled: bool) -> str:
    matches_line = (
        f"{match_count} live match{'es' if match_count != 1 else ''}"
        if match_count else "No live matches"
    )
    return (
        f"<b>Heartbeat</b>\n\n"
        f"<b>Monitoring:</b> {matches_line}\n"
        f"<b>Rule 5:</b> {'ON' if enabled else 'OFF'}\n"
        f"<i>{_now()}</i>"
    )


def error_text(message: str) -> str:
    return (
        f"<b>BOT ERROR</b>\n\n"
        f"{message}\n"
        f"<i>{_now()}</i>"
    )

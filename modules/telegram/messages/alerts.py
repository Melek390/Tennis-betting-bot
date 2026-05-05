from datetime import datetime, timezone

from rules import fmt_point_score


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S UTC")

def _fmt_ts(ts: datetime | None) -> str:
    return ts.strftime("%H:%M:%S") if ts else "—"

def _c(price: float | None) -> str:
    return f"{round(price * 100)}¢" if price is not None else "—"

def _pnl(exit_p: float | None, entry_p: float | None) -> str:
    if exit_p is None or entry_p is None:
        return "—"
    d = round((exit_p - entry_p) * 100)
    return f"+{d}¢" if d > 0 else f"{d}¢"

def _slip(spread: float | None) -> str:
    if spread is None:
        return ""
    return f"  |  Slip: −{round(spread / 2 * 100)}¢"


def entry_text(
    player: str, match: str, score: str, price: float,
    detail: str = "", spread: float | None = None,
) -> str:
    mid_line = ""
    if spread is not None:
        mid = price - spread / 2
        mid_line = f"  |  Mid: {_c(mid)}{_slip(spread)}"
    return (
        f"<b>R5 ENTRY</b> — {match}\n"
        f"<i>{player} (returning)</i>\n"
        f"{detail}\n"
        f"Entry: {_c(price)}{mid_line}\n"
        f"<i>{_now()}</i>"
    )


def exit_text(
    player: str, match: str, score: str,
    exit_price: float | None = None,
    stats: dict | None = None,
    exit_reason: str | None = None,
) -> str:
    ep  = stats.get("entry_price")    if stats else None
    ets = stats.get("entry_timestamp") if stats else None
    reason = exit_reason or "Condition no longer met"

    return (
        f"<b>R5 EXIT</b> — {match}\n"
        f"<i>{player} (returning)</i>\n"
        f"{score}\n"
        f"Reason: {reason}\n"
        f"Entry: {_c(ep)} @ {_fmt_ts(ets)}  →  Exit: {_c(exit_price)}\n"
        f"P&L: <b>{_pnl(exit_price, ep)}</b>\n"
        f"<i>{_now()}</i>"
    )


def reentry_text(
    player: str, match: str, score: str, price: float,
    detail: str = "", spread: float | None = None,
) -> str:
    mid_line = ""
    if spread is not None:
        mid = price - spread / 2
        mid_line = f"  |  Mid: {_c(mid)}{_slip(spread)}"
    return (
        f"<b>R5 RE-ENTRY</b> — {match}\n"
        f"<i>{player} (returning)</i>\n"
        f"{detail}\n"
        f"Entry: {_c(price)}{mid_line}\n"
        f"<i>{_now()}</i>"
    )


def log_text(player: str, match: str, log: dict) -> str:
    ep   = log.get("entry_price")
    em   = log.get("entry_mid")
    ets  = log.get("entry_timestamp")
    xp   = log.get("exit_price")
    xm   = log.get("exit_mid")
    xts  = log.get("exit_timestamp")
    mae  = log.get("mae", 0.0)
    mfe  = log.get("mfe", 0.0)
    reason = log.get("exit_reason_str", "")
    ticks  = log.get("tick_history", [])       # [(price, mid, ps), ...]
    pticks = log.get("post_exit_ticks", [])    # [(price, mid, ps), ...]
    entry_ps = log.get("entry_point_score", "")

    def _row(label: str, price: float | None, mid: float | None, ps: str, suffix: str = "") -> str:
        mid_str = f" (mid {_c(mid)})" if mid is not None else ""
        ps_str  = f"  {fmt_point_score(ps)}" if ps else ""
        return f"<code>{label:<4}</code> {_c(price)}{mid_str}{ps_str}{suffix}"

    lines = [
        f"<b>R5 LOG</b> — {match}",
        f"<i>{player}</i>",
        "",
        "<b>Price path:</b>",
        _row("t0", ep, em, entry_ps),
    ]

    for i, (p, m, ps) in enumerate(ticks, 1):
        lines.append(_row(f"t{i}", p, m, ps))

    xps = log.get("exit_point_score", "")
    lines.append(_row("exit", xp, xm, xps, "  ← exit"))

    for i, (p, m, ps) in enumerate(pticks, 1):
        lines.append(_row(f"t+{i}", p, m, ps))

    mae_str = f"{round(mae * 100)}¢" if mae < 0 else f"+{round(mae * 100)}¢"
    mfe_str = f"+{round(mfe * 100)}¢"

    lines += [
        "",
        f"Entry: {_c(ep)} @ {_fmt_ts(ets)}  |  Exit: {_c(xp)} @ {_fmt_ts(xts)}",
        f"P&L: <b>{_pnl(xp, ep)}</b>  |  MAE: {mae_str}  |  MFE: {mfe_str}",
    ]

    if pticks:
        post_moves = [(p - ep) * 100 for p, _, _ in pticks if ep is not None]
        best  = round(max(post_moves)) if post_moves else None
        worst = round(min(post_moves)) if post_moves else None
        if best is not None:
            b_str = f"+{best}¢" if best >= 0 else f"{best}¢"
            w_str = f"+{worst}¢" if worst >= 0 else f"{worst}¢"
            lines.append(f"Post-exit: best {b_str}, worst {w_str}")

    if reason:
        lines.append(f"<i>Reason: {reason}</i>")

    return "\n".join(lines)


def heartbeat_text(match_count: int, kalshi_count: int, enabled: bool) -> str:
    matches_line = (
        f"{match_count} live match{'es' if match_count != 1 else ''}"
        if match_count else "No live matches"
    )
    kalshi_line = (
        f"{kalshi_count} tradeable market{'s' if kalshi_count != 1 else ''}"
        if kalshi_count else "No tradeable markets"
    )
    return (
        f"<b>Heartbeat</b>\n\n"
        f"<b>Tennis API:</b> {matches_line}\n"
        f"<b>Kalshi:</b> {kalshi_line}\n"
        f"<b>Rule 5:</b> {'ON' if enabled else 'OFF'}\n"
        f"<i>{_now()}</i>"
    )


def error_text(message: str) -> str:
    return (
        f"<b>BOT ERROR</b>\n\n"
        f"{message}\n"
        f"<i>{_now()}</i>"
    )

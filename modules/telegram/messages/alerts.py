from dataclasses import dataclass
from datetime import datetime, timezone

from rules import fmt_point_score


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
    rule: str                     # "R1", "R2", "R3"
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


def log_text(player: str, match: str, log: dict) -> str:
    ep      = log.get("entry_price")
    em      = log.get("entry_mid")
    ets     = log.get("entry_timestamp")
    xp      = log.get("exit_price")
    xm      = log.get("exit_mid")
    xts     = log.get("exit_timestamp")
    mae     = log.get("mae", 0.0)
    mfe     = log.get("mfe", 0.0)
    reason  = log.get("exit_reason_str", "")
    ticks   = log.get("tick_history", [])     # [(price, mid, point_score), ...]
    pticks  = log.get("post_exit_ticks", [])  # [(price, mid, point_score), ...]
    entry_ps = log.get("entry_point_score", "")

    def _row(label: str, price, mid, ps: str, suffix: str = "") -> str:
        mid_str = f" (mid {_c(mid)})" if mid is not None else ""
        ps_str  = f"  {fmt_point_score(ps)}" if ps else ""
        return f"<code>{label:<4}</code> {_c(price)}{mid_str}{ps_str}{suffix}"

    lines = [
        f"<b>R1 LOG</b> — {match}",
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


def heartbeat_text(
    match_count: int,
    enabled: bool,
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
        f"<b>Rule 1:</b> {'ON' if enabled else 'OFF'}\n"
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

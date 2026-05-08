from dataclasses import dataclass
from datetime import datetime, timezone


def _c(p: float | None) -> str:
    return f"{round(p * 100)}¢" if p is not None else "—"


def _pnl(exit_p: float | None, entry_p: float | None) -> str:
    if exit_p is None or entry_p is None:
        return "—"
    d = round((exit_p - entry_p) * 100)
    return f"+{d}¢" if d > 0 else f"{d}¢"


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

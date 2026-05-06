from modules.bets.db import RULE_LABELS


def main_menu_text(enabled: bool = True, enabled_r2: bool = True, enabled_r3: bool = True) -> str:
    r1 = "✅" if enabled    else "⬜"
    r2 = "✅" if enabled_r2 else "⬜"
    r3 = "✅" if enabled_r3 else "⬜"
    return (
        "<b>Tennis Betting Bot</b>\n\n"
        f"R1 {r1}   R2 {r2}   R3 {r3}\n\n"
        "Choose an option:"
    )


def rules_menu_text() -> str:
    return "Tap a rule to toggle it on or off."


def bets_history_menu_text() -> str:
    return "<b>📊 Bets History</b>\n\nSelect a rule to view its trade log:"


def bets_rule_text(rule: str, stats: dict) -> str:
    label     = RULE_LABELS.get(rule, rule)
    total     = stats["total"]
    wins      = stats["wins"]
    losses    = stats["losses"]
    total_pnl = stats["total_pnl"]
    last5     = stats["last5"]

    win_rate = f"{round(wins / total * 100)}%" if total > 0 else "—"
    pnl_str  = f"+{total_pnl}¢" if total_pnl >= 0 else f"{total_pnl}¢"

    lines = [
        f"<b>📊 {label}</b>\n",
        f"Total: <b>{total}</b>   W: <b>{wins}</b>   L: <b>{losses}</b>   ({win_rate})",
        f"P&amp;L: <b>{pnl_str}</b>\n",
    ]

    if last5:
        lines.append("<b>Recent bets:</b>")
        for b in last5:
            pnl_val = b.get("pnl")
            p    = (f"+{pnl_val}¢" if pnl_val >= 0 else f"{pnl_val}¢") if pnl_val is not None else "—"
            name = (b.get("player") or "?")[:20]
            ts   = (b.get("timestamp") or "")[:10]
            rsn  = (b.get("exit_reason") or "")[:30]
            lines.append(f"• {ts} · {name} · <b>{p}</b> · <i>{rsn}</i>")
    else:
        lines.append("<i>No bets recorded yet.</i>")

    return "\n".join(lines)

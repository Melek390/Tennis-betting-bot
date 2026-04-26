from datetime import datetime, timezone

_EXIT_REASONS: dict[int, str] = {
    1: "Match point lost",
    2: "Game lead dropped below 2",
    3: "Game lead dropped below 2",
    4: "Set 2 lead disappeared",
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M UTC")


def entry_text(rule: int, player: str, match: str, score: str, price: float, detail: str = "") -> str:
    return (
        f"<b>ENTRY — Rule {rule}</b>\n"
        f"<i>{detail}</i>\n\n"
        f"<b>Match:</b> {match}\n"
        f"<b>Player:</b> {player}\n"
        f"<b>Score:</b> {score}\n"
        f"<b>Price:</b> {round(price * 100)}¢\n"
        f"<i>{_now()}</i>"
    )


def exit_text(rule: int, player: str, match: str, score: str) -> str:
    reason = _EXIT_REASONS.get(rule, "Condition no longer met")
    return (
        f"<b>EXIT — Rule {rule}</b>\n\n"
        f"<b>Match:</b> {match}\n"
        f"<b>Player:</b> {player}\n"
        f"<b>Score:</b> {score}\n"
        f"<b>Reason:</b> {reason}\n"
        f"<i>{_now()}</i>"
    )


def reentry_text(rule: int, player: str, match: str, score: str, price: float, detail: str = "") -> str:
    return (
        f"<b>RE-ENTRY — Rule {rule}</b>\n"
        f"<i>{detail}</i>\n\n"
        f"<b>Match:</b> {match}\n"
        f"<b>Player:</b> {player}\n"
        f"<b>Score:</b> {score}\n"
        f"<b>Price:</b> {round(price * 100)}¢\n"
        f"<i>{_now()}</i>"
    )


def heartbeat_text(match_count: int, enabled_rules: dict[int, bool]) -> str:
    matches_line = (
        f"{match_count} live match{'es' if match_count != 1 else ''}"
        if match_count else "No live matches"
    )
    rules_line = "  ".join(
        f"R{r}: {'ON' if on else 'OFF'}" for r, on in sorted(enabled_rules.items())
    )
    return (
        f"<b>Heartbeat</b>\n\n"
        f"<b>Monitoring:</b> {matches_line}\n"
        f"<b>Rules:</b> {rules_line}\n"
        f"<i>{_now()}</i>"
    )


def error_text(message: str) -> str:
    return (
        f"<b>BOT ERROR</b>\n\n"
        f"{message}\n"
        f"<i>{_now()}</i>"
    )

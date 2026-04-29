def main_menu_text(enabled: bool) -> str:
    status = "ON" if enabled else "OFF"
    return (
        "<b>Tennis Betting Bot</b>\n\n"
        f"Rule 5 (Break Point / Advantage) is <b>{status}</b>.\n\n"
        "Choose an option:"
    )


def rules_menu_text() -> str:
    return "Tap to toggle Rule 5 on or off."

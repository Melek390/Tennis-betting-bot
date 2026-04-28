RULE_LABELS: dict[int, str] = {
    1: "Match point · ≤75¢",
    2: "1-0 sets + 2 game lead · ≤65¢",
    3: "1-1 sets + 2 game lead · ≤62¢",
    4: "Set 1 dominant + 1 game lead · ≤58¢",
    5: "Break point / Advantage · ≤60¢",
    6: "Tiebreak mini-break · ≤55¢",
    7: "Break confirmed (early set) · ≤75¢",
}


def main_menu_text(enabled_rules: dict[int, bool]) -> str:
    active = sum(enabled_rules.values())
    total = len(enabled_rules)
    return (
        "<b>Tennis Betting Bot</b>\n\n"
        f"Monitoring <b>{active}/{total}</b> rules across all live matches.\n\n"
        "Choose an option:"
    )


def rules_menu_text() -> str:
    return "Select rules to enable/disable:\n\nTap a rule to toggle it."

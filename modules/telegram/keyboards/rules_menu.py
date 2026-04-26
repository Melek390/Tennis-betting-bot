from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from ..messages.menus import RULE_LABELS


def build(enabled_rules: dict[int, bool]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            f"{'✅' if enabled_rules[r] else '⬜'} Rule {r} — {RULE_LABELS[r]}",
            callback_data=f"toggle_{r}",
        )]
        for r in range(1, 5)
    ]
    rows.append([InlineKeyboardButton("« Back to Main Menu", callback_data="main")])
    return InlineKeyboardMarkup(rows)

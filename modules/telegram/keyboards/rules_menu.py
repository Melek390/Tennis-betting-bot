from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build(enabled: bool) -> InlineKeyboardMarkup:
    label = "✅ Rule 5 — Break Point / Advantage · ≤60¢" if enabled else "⬜ Rule 5 — Break Point / Advantage · ≤60¢"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(label, callback_data="toggle_rule")],
        [InlineKeyboardButton("« Back to Main Menu", callback_data="main")],
    ])

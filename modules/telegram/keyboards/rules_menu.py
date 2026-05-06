from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build(enabled: bool, enabled_r2: bool = True, enabled_r3: bool = True) -> InlineKeyboardMarkup:
    lbl1 = "✅ Rule 1 — Break Point / Advantage · ≤60¢" if enabled    else "⬜ Rule 1 — Break Point / Advantage · ≤60¢"
    lbl2 = "✅ Rule 2 — Kalshi Spike Fade · auto"       if enabled_r2 else "⬜ Rule 2 — Kalshi Spike Fade · auto"
    lbl3 = "✅ Rule 3 — Back Fav after Set Loss"        if enabled_r3 else "⬜ Rule 3 — Back Fav after Set Loss"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(lbl1, callback_data="toggle_rule")],
        [InlineKeyboardButton(lbl2, callback_data="toggle_rule_r2")],
        [InlineKeyboardButton(lbl3, callback_data="toggle_rule_r3")],
        [InlineKeyboardButton("« Back to Main Menu", callback_data="main")],
    ])

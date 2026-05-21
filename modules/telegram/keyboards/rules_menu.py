from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build(enabled_r2: bool = True, enabled_r3: bool = True, enabled_r4: bool = True) -> InlineKeyboardMarkup:
    lbl2 = "✅ Rule 2 — Kalshi Spike Fade" if enabled_r2 else "⬜ Rule 2 — Kalshi Spike Fade"
    lbl3 = "✅ Rule 3 — Back Fav after Set Loss" if enabled_r3 else "⬜ Rule 3 — Back Fav after Set Loss"
    lbl4 = "✅ Rule 4 — Set 1 Winner Spike Fade" if enabled_r4 else "⬜ Rule 4 — Set 1 Winner Spike Fade"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(lbl2, callback_data="toggle_rule_r2")],
        [InlineKeyboardButton(lbl3, callback_data="toggle_rule_r3")],
        [InlineKeyboardButton(lbl4, callback_data="toggle_rule_r4")],
        [InlineKeyboardButton("« Back to Main Menu", callback_data="main")],
    ])

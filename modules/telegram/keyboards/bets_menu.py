from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build_rule_picker() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Rule 1 — Break Point / Advantage",  callback_data="bets_r1")],
        [InlineKeyboardButton("Rule 2 — Kalshi Spike Fade",        callback_data="bets_r2")],
        [InlineKeyboardButton("Rule 3 — Back Fav after Set Loss",  callback_data="bets_r3")],
        [InlineKeyboardButton("« Back",                            callback_data="main")],
    ])


def build_rule_detail(rule: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📥  Export CSV", callback_data=f"export_csv_{rule}")],
        [InlineKeyboardButton("« Back",         callback_data="bets_history")],
    ])

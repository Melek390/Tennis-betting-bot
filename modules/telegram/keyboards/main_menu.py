from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️  Set Rules",    callback_data="monitoring")],
        [InlineKeyboardButton("📊  Bets History", callback_data="bets_history")],
        [InlineKeyboardButton("❓  Help",         callback_data="help")],
    ])

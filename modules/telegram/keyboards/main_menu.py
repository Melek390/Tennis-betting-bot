from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Start Monitoring", callback_data="monitoring")],
        [InlineKeyboardButton("Help", callback_data="help")],
    ])

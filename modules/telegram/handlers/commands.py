from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ..keyboards import main_menu
from ..messages.menus import main_menu_text
from ..state import STATE_KEY


async def start(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    state = _context.application.bot_data[STATE_KEY]
    await update.message.reply_text(
        text=main_menu_text(state.enabled_r2, state.enabled_r3),
        reply_markup=main_menu.build(),
        parse_mode=ParseMode.HTML,
    )

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ..keyboards import main_menu, rules_menu
from ..messages.help_text import HELP_TEXT
from ..messages.menus import main_menu_text, rules_menu_text
from ..state import STATE_KEY


async def show_main(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    state = _context.application.bot_data[STATE_KEY]
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        text=main_menu_text(state.enabled),
        reply_markup=main_menu.build(),
        parse_mode=ParseMode.HTML,
    )


async def show_monitoring(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    state = _context.application.bot_data[STATE_KEY]
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        text=rules_menu_text(),
        reply_markup=rules_menu.build(state.enabled),
        parse_mode=ParseMode.HTML,
    )


async def show_help(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        text=HELP_TEXT,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("« Back", callback_data="main")]
        ]),
        parse_mode=ParseMode.HTML,
    )


async def toggle_rule(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    state = _context.application.bot_data[STATE_KEY]
    query = update.callback_query
    await query.answer()
    state.enabled = not state.enabled
    await query.edit_message_text(
        text=rules_menu_text(),
        reply_markup=rules_menu.build(state.enabled),
        parse_mode=ParseMode.HTML,
    )

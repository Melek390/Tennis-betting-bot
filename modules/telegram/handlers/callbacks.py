from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ..keyboards import main_menu, rules_menu
from ..messages.help_text import HELP_TEXT
from ..messages.menus import main_menu_text, rules_menu_text
from ..state import STATE_KEY, STATE_MGR_KEY


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


# ------------------------------------------------------------------
# Entry / exit / re-entry confirmation buttons
# Callback data format: "{prefix}:{match_id}:{player_side}"
# ------------------------------------------------------------------

def _parse(data: str) -> tuple[str, str]:
    parts = data.split(":")
    return parts[1], parts[2]


async def _update(query, status_line: str) -> None:
    original = query.message.text_html
    await query.edit_message_text(
        text=original + f"\n\n<b>——</b> <i>{status_line}</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=None,
    )


async def confirm_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    match_id, player = _parse(query.data)
    context.application.bot_data[STATE_MGR_KEY].confirm_entry(match_id, player)
    await query.answer("In position")
    await _update(query, "Scanning for exit condition...")


async def skip_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    match_id, player = _parse(query.data)
    context.application.bot_data[STATE_MGR_KEY].skip_entry(match_id, player)
    await query.answer("Skipped")
    await _update(query, "Skipped — watching for next entry signal")


async def confirm_exit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    match_id, player = _parse(query.data)
    context.application.bot_data[STATE_MGR_KEY].confirm_exit(match_id, player)
    await query.answer("Exited")
    await _update(query, "Looking for re-entry opportunity...")


async def keep_position(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    match_id, player = _parse(query.data)
    context.application.bot_data[STATE_MGR_KEY].keep_position(match_id, player)
    await query.answer("Holding")
    await _update(query, "Staying in position — monitoring exit condition")


async def confirm_reentry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    match_id, player = _parse(query.data)
    context.application.bot_data[STATE_MGR_KEY].confirm_reentry(match_id, player)
    await query.answer("Re-entered")
    await _update(query, "Scanning for exit condition...")


async def skip_reentry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    match_id, player = _parse(query.data)
    context.application.bot_data[STATE_MGR_KEY].skip_reentry(match_id, player)
    await query.answer("Skipped")
    await _update(query, "Watching for re-entry signal...")

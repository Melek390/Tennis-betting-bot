from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from modules.bets.db import BETS_DB_KEY
from ..keyboards import bets_menu, main_menu, rules_menu
from ..messages.help_text import HELP_TEXT
from ..messages.menus import (
    bets_history_menu_text, bets_rule_text,
    main_menu_text, rules_menu_text,
)
from ..state import STATE_KEY


# ------------------------------------------------------------------
# Main menu
# ------------------------------------------------------------------

async def show_main(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    state = _context.application.bot_data[STATE_KEY]
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        text=main_menu_text(state.enabled_r2, state.enabled_r3, state.enabled_r4),
        reply_markup=main_menu.build(),
        parse_mode=ParseMode.HTML,
    )


async def show_monitoring(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    state = _context.application.bot_data[STATE_KEY]
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        text=rules_menu_text(),
        reply_markup=rules_menu.build(state.enabled_r2, state.enabled_r3, state.enabled_r4),
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


# ------------------------------------------------------------------
# Rule toggles
# ------------------------------------------------------------------

async def toggle_rule_r2(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    state = _context.application.bot_data[STATE_KEY]
    query = update.callback_query
    await query.answer()
    state.enabled_r2 = not state.enabled_r2
    await query.edit_message_text(
        text=rules_menu_text(),
        reply_markup=rules_menu.build(state.enabled_r2, state.enabled_r3, state.enabled_r4),
        parse_mode=ParseMode.HTML,
    )


async def toggle_rule_r3(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    state = _context.application.bot_data[STATE_KEY]
    query = update.callback_query
    await query.answer()
    state.enabled_r3 = not state.enabled_r3
    await query.edit_message_text(
        text=rules_menu_text(),
        reply_markup=rules_menu.build(state.enabled_r2, state.enabled_r3, state.enabled_r4),
        parse_mode=ParseMode.HTML,
    )


async def toggle_rule_r4(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    state = _context.application.bot_data[STATE_KEY]
    query = update.callback_query
    await query.answer()
    state.enabled_r4 = not state.enabled_r4
    await query.edit_message_text(
        text=rules_menu_text(),
        reply_markup=rules_menu.build(state.enabled_r2, state.enabled_r3, state.enabled_r4),
        parse_mode=ParseMode.HTML,
    )


# ------------------------------------------------------------------
# Bets history
# ------------------------------------------------------------------

async def show_bets_history(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        text=bets_history_menu_text(),
        reply_markup=bets_menu.build_rule_picker(),
        parse_mode=ParseMode.HTML,
    )


async def show_bets_rule(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    rule  = query.data.split("_")[-1]   # "r1", "r2", "r3"
    db    = _context.application.bot_data[BETS_DB_KEY]
    stats = db.get_stats(rule)
    await query.answer()
    await query.edit_message_text(
        text=bets_rule_text(rule, stats),
        reply_markup=bets_menu.build_rule_detail(rule),
        parse_mode=ParseMode.HTML,
    )


async def export_csv(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    rule  = query.data.rsplit("_", 1)[-1]   # "r1", "r2", "r3"
    db    = _context.application.bot_data[BETS_DB_KEY]
    buf   = db.export_csv(rule)
    await query.answer("Generating CSV…")
    await query.message.reply_document(
        document=buf,
        filename=f"bets_{rule}.csv",
        caption=f"📥 Full trade log — {rule.upper()}",
    )

from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from ..handlers import callbacks, commands


def setup(app: Application) -> None:
    app.add_handler(CommandHandler("start", commands.start))

    # Main navigation
    app.add_handler(CallbackQueryHandler(callbacks.show_main,       pattern="^main$"))
    app.add_handler(CallbackQueryHandler(callbacks.show_monitoring, pattern="^monitoring$"))
    app.add_handler(CallbackQueryHandler(callbacks.show_help,       pattern="^help$"))

    # Rule toggles
    app.add_handler(CallbackQueryHandler(callbacks.toggle_rule,    pattern=r"^toggle_rule$"))
    app.add_handler(CallbackQueryHandler(callbacks.toggle_rule_r2, pattern=r"^toggle_rule_r2$"))
    app.add_handler(CallbackQueryHandler(callbacks.toggle_rule_r3, pattern=r"^toggle_rule_r3$"))

    # Bets history
    app.add_handler(CallbackQueryHandler(callbacks.show_bets_history, pattern=r"^bets_history$"))
    app.add_handler(CallbackQueryHandler(callbacks.show_bets_rule,    pattern=r"^bets_r[123]$"))
    app.add_handler(CallbackQueryHandler(callbacks.export_csv,        pattern=r"^export_csv_r[123]$"))

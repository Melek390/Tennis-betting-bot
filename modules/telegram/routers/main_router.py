from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from ..handlers import callbacks, commands


def setup(app: Application) -> None:
    app.add_handler(CommandHandler("start", commands.start))
    app.add_handler(CallbackQueryHandler(callbacks.show_main,       pattern="^main$"))
    app.add_handler(CallbackQueryHandler(callbacks.show_monitoring, pattern="^monitoring$"))
    app.add_handler(CallbackQueryHandler(callbacks.show_help,       pattern="^help$"))
    app.add_handler(CallbackQueryHandler(callbacks.toggle_rule,     pattern=r"^toggle_[1-4]$"))
    # Entry / exit / re-entry confirmation buttons
    app.add_handler(CallbackQueryHandler(callbacks.confirm_entry,   pattern=r"^ce:"))
    app.add_handler(CallbackQueryHandler(callbacks.skip_entry,      pattern=r"^se:"))
    app.add_handler(CallbackQueryHandler(callbacks.confirm_exit,    pattern=r"^cx:"))
    app.add_handler(CallbackQueryHandler(callbacks.keep_position,   pattern=r"^kx:"))
    app.add_handler(CallbackQueryHandler(callbacks.confirm_reentry, pattern=r"^cr:"))
    app.add_handler(CallbackQueryHandler(callbacks.skip_reentry,    pattern=r"^sr:"))

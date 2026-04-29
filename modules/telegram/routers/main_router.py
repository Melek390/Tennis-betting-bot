from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from ..handlers import callbacks, commands


def setup(app: Application) -> None:
    app.add_handler(CommandHandler("start", commands.start))
    app.add_handler(CallbackQueryHandler(callbacks.show_main,       pattern="^main$"))
    app.add_handler(CallbackQueryHandler(callbacks.show_monitoring, pattern="^monitoring$"))
    app.add_handler(CallbackQueryHandler(callbacks.show_help,       pattern="^help$"))
    app.add_handler(CallbackQueryHandler(callbacks.toggle_rule,     pattern=r"^toggle_rule$"))

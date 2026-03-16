"""Register all bot handlers in correct priority order."""
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters


def register_handlers(app: Application) -> None:
    """Wire all handlers to the application.

    Order matters: commands first, then callback queries, then catch-all text.
    """
    from cps.bot.handlers.callbacks import handle_callback
    from cps.bot.handlers.monitors import monitors_command
    from cps.bot.handlers.price_check import handle_text_message
    from cps.bot.handlers.settings import help_command, language_command, settings_command
    from cps.bot.handlers.start import start_command

    # Commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("monitors", monitors_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("language", language_command))
    app.add_handler(CommandHandler("help", help_command))

    # Callback queries (inline buttons)
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Catch-all text messages (URL/ASIN/NLP)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

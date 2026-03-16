"""/settings, /language, /help command handlers."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from cps.db.session import get_session
from cps.services.user_service import UserService


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show settings menu."""
    session_factory = context.bot_data["session_factory"]

    async with get_session(session_factory) as session:
        user_svc = UserService(session)
        user = await user_svc.get_or_create(telegram_id=update.effective_user.id)
        await user_svc.record_interaction(user)

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Compact", callback_data="set_density:compact"),
             InlineKeyboardButton("Standard", callback_data="set_density:standard"),
             InlineKeyboardButton("Detailed", callback_data="set_density:detailed")],
            [InlineKeyboardButton("English", callback_data="set_lang:en"),
             InlineKeyboardButton("Español", callback_data="set_lang:es")],
            [InlineKeyboardButton("Pause deal alerts", callback_data="pause_deals")],
            [InlineKeyboardButton("Delete my data", callback_data="delete_data")],
        ])

        current = f"Density: {user.density_preference} | Language: {user.language}"
        await update.message.reply_text(f"Settings\n{current}", reply_markup=kb)
        await session.commit()


async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Quick language switch: EN ↔ ES."""
    session_factory = context.bot_data["session_factory"]

    async with get_session(session_factory) as session:
        user_svc = UserService(session)
        user = await user_svc.get_or_create(telegram_id=update.effective_user.id)
        await user_svc.record_interaction(user)

        new_lang = "es" if user.language == "en" else "en"
        await user_svc.update_language(user, new_lang)

        labels = {"en": "English", "es": "Español"}
        await update.message.reply_text(f"Language set to {labels[new_lang]}.")
        await session.commit()


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """One-screen help with examples."""
    session_factory = context.bot_data["session_factory"]

    async with get_session(session_factory) as session:
        user_svc = UserService(session)
        user = await user_svc.get_or_create(telegram_id=update.effective_user.id)

        if user.language == "es":
            msg = (
                "Como usar BuyPulse:\n\n"
                "- Envia un enlace de Amazon -> obten el precio + historial\n"
                "- Envia un ASIN (ej: B08N5WRWNW) -> consulta directa\n"
                "- Escribe un producto (ej: 'AirPods Pro') -> busqueda\n\n"
                "Comandos:\n"
                "/monitors — ver tus alertas\n"
                "/settings — idioma, densidad, alertas\n"
                "/language — cambiar idioma EN <-> ES\n"
                "/help — esta ayuda"
            )
        else:
            msg = (
                "How to use BuyPulse:\n\n"
                "- Send an Amazon link -> get price + history\n"
                "- Send an ASIN (e.g., B08N5WRWNW) -> direct lookup\n"
                "- Type a product (e.g., 'AirPods Pro') -> search\n\n"
                "Commands:\n"
                "/monitors — view your price alerts\n"
                "/settings — language, density, deal alerts\n"
                "/language — switch EN <-> ES\n"
                "/help — this help screen"
            )

        await update.message.reply_text(msg)
        await session.commit()

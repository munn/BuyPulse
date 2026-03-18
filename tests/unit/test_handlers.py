"""Tests for bot handlers — mocked Telegram Update + Context."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_update(text="/start", user_id=12345, username="testuser", first_name="Test"):
    """Build a mock Telegram Update."""
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.username = username
    update.effective_user.first_name = first_name
    update.message.text = text
    update.message.reply_text = AsyncMock()
    update.callback_query = None
    return update


def _make_context(settings=None):
    """Build a mock CallbackContext with bot_data."""
    context = MagicMock()
    context.bot_data = {
        "settings": settings or MagicMock(affiliate_tag="test-20", demo_product_id="B0D1XD1ZV3"),
        "session_factory": MagicMock(),
        "ai_client": MagicMock(),
    }
    return context


def _make_callback_update(data, user_id=12345):
    """Build a mock Telegram Update with callback_query."""
    update = MagicMock()
    update.effective_user.id = user_id
    update.callback_query.data = data
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.message.reply_text = AsyncMock()
    return update


class TestStartHandler:
    @patch("cps.bot.handlers.start.get_session")
    async def test_sends_onboarding_message(self, mock_get_session):
        from cps.bot.handlers.start import start_command

        update = _make_update("/start")
        context = _make_context()

        # Mock DB session
        mock_session = AsyncMock()
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        # Mock user service
        with patch("cps.bot.handlers.start.UserService") as MockUserService:
            mock_user_svc = AsyncMock()
            mock_user_svc.get_or_create = AsyncMock(return_value=MagicMock(language="en"))
            MockUserService.return_value = mock_user_svc

            # Mock product lookup for demo
            mock_session.execute = AsyncMock(
                return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
            )

            await start_command(update, context)

        update.message.reply_text.assert_called_once()
        msg = update.message.reply_text.call_args[0][0]
        assert "BuyPulse" in msg


class TestPriceCheckHandler:
    @patch("cps.bot.handlers.price_check.get_session")
    async def test_url_input_triggers_price_lookup(self, mock_get_session):
        from cps.bot.handlers.price_check import handle_text_message

        update = _make_update("https://amazon.com/dp/B08N5WRWNW")
        context = _make_context()

        mock_session = AsyncMock()
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        # Mock product found in DB
        product = MagicMock(id=1, asin="B08N5WRWNW", title="AirPods Pro 2")
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=product))
        )

        with patch("cps.bot.handlers.price_check.UserService") as MockUS, \
             patch("cps.bot.handlers.price_check._send_price_report") as mock_send:
            MockUS.return_value.get_or_create = AsyncMock(
                return_value=MagicMock(language="en", density_preference="standard")
            )
            MockUS.return_value.record_interaction = AsyncMock()
            mock_send.return_value = None

            await handle_text_message(update, context)
            mock_send.assert_called_once()

    @patch("cps.bot.handlers.price_check.get_session")
    async def test_nlp_input_triggers_search(self, mock_get_session):
        from cps.bot.handlers.price_check import handle_text_message

        update = _make_update("How much are AirPods?")
        context = _make_context()

        mock_session = AsyncMock()
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("cps.bot.handlers.price_check.UserService") as MockUS, \
             patch("cps.bot.handlers.price_check._handle_nlp_search") as mock_nlp:
            MockUS.return_value.get_or_create = AsyncMock(
                return_value=MagicMock(language="en", density_preference="standard")
            )
            MockUS.return_value.record_interaction = AsyncMock()
            mock_nlp.return_value = None

            await handle_text_message(update, context)
            mock_nlp.assert_called_once()


class TestCallbackHandler:
    @patch("cps.bot.handlers.callbacks.get_session")
    async def test_density_toggle(self, mock_get_session):
        from cps.bot.handlers.callbacks import handle_callback

        update = _make_callback_update("density:detailed:B08N5WRWNW")
        context = _make_context()

        mock_session = AsyncMock()
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("cps.bot.handlers.callbacks._handle_density_toggle") as mock_toggle:
            mock_toggle.return_value = None
            await handle_callback(update, context)
            mock_toggle.assert_called_once()

    @patch("cps.bot.handlers.callbacks.get_session")
    async def test_target_price_selection(self, mock_get_session):
        from cps.bot.handlers.callbacks import handle_callback

        update = _make_callback_update("target:B08N5WRWNW:16900")
        context = _make_context()

        mock_session = AsyncMock()
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("cps.bot.handlers.callbacks._handle_target_selection") as mock_target:
            mock_target.return_value = None
            await handle_callback(update, context)
            mock_target.assert_called_once()

    @patch("cps.bot.handlers.callbacks.get_session")
    async def test_dismiss_deal(self, mock_get_session):
        from cps.bot.handlers.callbacks import handle_callback

        update = _make_callback_update("dismiss_cat:Electronics")
        context = _make_context()

        mock_session = AsyncMock()
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("cps.bot.handlers.callbacks._handle_dismiss") as mock_dismiss:
            mock_dismiss.return_value = None
            await handle_callback(update, context)
            mock_dismiss.assert_called_once()

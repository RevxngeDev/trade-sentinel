"""Optional Telegram polling lifecycle and scheduler alert delivery."""

from __future__ import annotations

import logging

from telegram import Bot
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler

from app.bot.formatters import format_signal
from app.bot.handlers import analyze_command, help_command, signals_command, stats_command
from app.config import settings
from app.schemas.regime import SignalRead

logger = logging.getLogger(__name__)


class TelegramBotService:
    def __init__(self) -> None:
        self.application: Application | None = None

    def _build_application(self) -> Application:
        if not settings.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN must be set when TELEGRAM_ENABLED=true")
        if not settings.telegram_chat_id:
            raise ValueError("TELEGRAM_CHAT_ID must be set when TELEGRAM_ENABLED=true")

        application = Application.builder().token(settings.telegram_bot_token).build()
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("analizar", analyze_command))
        application.add_handler(CommandHandler("senales", signals_command))
        application.add_handler(CommandHandler("stats", stats_command))
        return application

    async def start(self) -> None:
        if self.application is not None:
            return

        self.application = self._build_application()
        await self.application.initialize()
        await self.application.start()
        if self.application.updater is None:
            raise RuntimeError("Telegram updater is unavailable")
        await self.application.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram bot polling started")

    async def stop(self) -> None:
        if self.application is None:
            return

        if self.application.updater is not None:
            await self.application.updater.stop()
        await self.application.stop()
        await self.application.shutdown()
        self.application = None
        logger.info("Telegram bot polling stopped")


telegram_bot = TelegramBotService()


async def send_signal_alert(signal: SignalRead) -> None:
    """Send a scheduler-created signal only to the configured personal chat."""
    if not settings.telegram_enabled or not settings.telegram_chat_id:
        return
    if not settings.telegram_bot_token:
        logger.error("Telegram alert skipped because TELEGRAM_BOT_TOKEN is missing")
        return

    bot = Bot(token=settings.telegram_bot_token)
    try:
        await bot.send_message(chat_id=settings.telegram_chat_id, text=format_signal(signal))
    except TelegramError:
        logger.exception("Telegram signal alert failed")
    finally:
        try:
            await bot.close()
        except TelegramError:
            logger.warning("Telegram bot close request failed")

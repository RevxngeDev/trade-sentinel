"""Optional Telegram polling lifecycle and scheduler alert delivery."""

from __future__ import annotations

import logging

from telegram import Bot
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler

from app.bot.formatters import format_signal
from app.bot.handlers import (
    analyze_command,
    help_command,
    interpret_command,
    signals_command,
    stats_command,
)
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
        application.add_handler(CommandHandler("interpretar", interpret_command))
        return application

    async def start(self) -> bool:
        """Start polling without allowing a Telegram outage to stop the API."""
        if self.application is not None:
            return True

        application = self._build_application()
        try:
            await application.initialize()
            await application.start()
            if application.updater is None:
                raise RuntimeError("Telegram updater is unavailable")
            await application.updater.start_polling(drop_pending_updates=True)
        except TelegramError:
            logger.exception(
                "Telegram bot startup failed; continuing without Telegram polling"
            )
            await self._cleanup_failed_start(application)
            return False

        self.application = application
        logger.info("Telegram bot polling started")
        return True

    async def _cleanup_failed_start(self, application: Application) -> None:
        """Best-effort cleanup after a Telegram startup failure."""
        try:
            if application.updater is not None and application.updater.running:
                await application.updater.stop()
            if application.running:
                await application.stop()
            if application.initialized:
                await application.shutdown()
        except Exception:  # noqa: BLE001 - cleanup must not stop FastAPI startup
            logger.warning("Telegram cleanup after startup failure also failed", exc_info=True)

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

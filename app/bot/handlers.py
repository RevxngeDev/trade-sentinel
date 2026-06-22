"""Telegram command handlers for deterministic educational signals."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.formatters import format_signal, format_signal_history, format_stats
from app.config import settings
from app.services.market_data import MarketDataError
from app.services.signal_service import SignalService
from app.services.tracker_service import TrackerService

logger = logging.getLogger(__name__)


def is_authorized_chat(chat_id: int | None) -> bool:
    """Allow commands only from the configured personal Telegram chat."""
    return bool(
        chat_id is not None
        and settings.telegram_chat_id
        and str(chat_id) == settings.telegram_chat_id
    )


async def _require_authorized_chat(update: Update) -> bool:
    message = update.effective_message
    chat = update.effective_chat
    if message is None:
        return False
    if is_authorized_chat(chat.id if chat else None):
        return True

    logger.warning("Rejected Telegram command from unconfigured chat")
    await message.reply_text("Este bot no está autorizado para este chat.")
    return False


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or not await _require_authorized_chat(update):
        return
    await message.reply_text(
        "TradeSentinel (uso educativo)\n\n"
        "/analizar BTC - analiza una señal determinista sin guardarla\n"
        "/senales - muestra señales almacenadas\n"
        "/stats - muestra métricas de paper trading\n\n"
        "El bot no ejecuta operaciones ni garantiza resultados."
    )


async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or not await _require_authorized_chat(update):
        return

    symbol = context.args[0] if context.args else settings.default_symbol
    try:
        signal = await SignalService().generate(symbol)
        await message.reply_text(format_signal(signal))
    except (MarketDataError, ValueError) as exc:
        await message.reply_text(f"No se pudo analizar el símbolo: {exc}")
    except Exception:  # noqa: BLE001 - avoid leaking backend details to Telegram
        logger.exception("Telegram analysis command failed")
        await message.reply_text("Error temporal al analizar el mercado. Inténtalo más tarde.")


async def signals_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or not await _require_authorized_chat(update):
        return

    try:
        signals = await SignalService().list_signals(None, limit=10)
        await message.reply_text(format_signal_history(signals))
    except Exception:  # noqa: BLE001
        logger.exception("Telegram signals command failed")
        await message.reply_text("No se pudieron cargar las señales. Inténtalo más tarde.")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or not await _require_authorized_chat(update):
        return

    try:
        stats = await TrackerService().get_stats()
        await message.reply_text(format_stats(stats))
    except Exception:  # noqa: BLE001
        logger.exception("Telegram stats command failed")
        await message.reply_text("No se pudieron cargar las estadísticas. Inténtalo más tarde.")

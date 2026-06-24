"""Telegram command handlers for deterministic educational signals."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from app.bot.formatters import (
    format_interpretation,
    format_signal,
    format_signal_history,
    format_stats,
)
from app.config import settings
from app.services.ai_agent import AIInterpretationError, AIInterpretationService
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


async def _show_typing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show Telegram's transient typing state while a backend request runs."""
    chat = update.effective_chat
    if chat is None:
        return
    try:
        await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.TYPING)
    except Exception:  # noqa: BLE001 - typing feedback must not break a command
        logger.warning("Could not send Telegram typing action", exc_info=True)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or not await _require_authorized_chat(update):
        return
    await message.reply_text(
        "TradeSentinel (uso educativo)\n\n"
        "/analizar BTC - analiza una señal determinista sin guardarla\n"
        "/senales - muestra señales almacenadas\n"
        "/stats - muestra métricas de paper trading\n"
        "/interpretar <id> - explica una señal almacenada con IA\n\n"
        "El bot no ejecuta operaciones ni garantiza resultados."
    )


async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or not await _require_authorized_chat(update):
        return

    symbol = context.args[0] if context.args else settings.default_symbol
    try:
        await _show_typing(update, context)
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
        await _show_typing(update, context)
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
        await _show_typing(update, context)
        stats = await TrackerService().get_stats()
        await message.reply_text(format_stats(stats))
    except Exception:  # noqa: BLE001
        logger.exception("Telegram stats command failed")
        await message.reply_text("No se pudieron cargar las estadísticas. Inténtalo más tarde.")


def parse_signal_id(args: list[str]) -> int | None:
    """Accept exactly one positive stored-signal ID from a Telegram command."""
    if len(args) != 1:
        return None

    try:
        signal_id = int(args[0])
    except ValueError:
        return None
    return signal_id if signal_id > 0 else None


async def interpret_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Explain an existing signal without generating or changing a signal."""
    message = update.effective_message
    if message is None or not await _require_authorized_chat(update):
        return

    signal_id = parse_signal_id(context.args)
    if signal_id is None:
        await message.reply_text("Uso: /interpretar <id>. Ejemplo: /interpretar 2")
        return

    try:
        await _show_typing(update, context)
        signal = await SignalService().get_by_id(signal_id)
        if signal is None:
            await message.reply_text("No existe una señal almacenada con ese ID.")
            return

        interpretation = await AIInterpretationService().interpret(signal)
        await message.reply_text(format_interpretation(signal_id, interpretation))
    except ValueError:
        await message.reply_text("La interpretación de IA no está configurada temporalmente.")
    except AIInterpretationError:
        logger.exception("Telegram AI interpretation command failed")
        await message.reply_text("No se pudo obtener una interpretación válida. Inténtalo más tarde.")
    except Exception:  # noqa: BLE001 - avoid leaking backend details to Telegram
        logger.exception("Telegram AI interpretation command failed")
        await message.reply_text("Error temporal al interpretar la señal. Inténtalo más tarde.")

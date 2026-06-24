from datetime import datetime, timezone
from types import SimpleNamespace

from telegram.error import TimedOut

from app.bot.formatters import (
    format_interpretation,
    format_signal,
    format_signal_history,
    format_stats,
)
from app.bot.handlers import _show_typing, is_authorized_chat, parse_signal_id
from app.bot.telegram_bot import TelegramBotService
from app.config import settings
from app.schemas.regime import AgentInterpretation, SignalRead, SignalStatsRead


def _signal() -> SignalRead:
    timestamp = datetime(2026, 6, 22, 18, 0, tzinfo=timezone.utc)
    return SignalRead(
        id=1,
        pair="BTC/USDT",
        timeframe="4h",
        action="CASH",
        regime_on=False,
        previous_regime_on=False,
        confidence=50,
        price=64539.32,
        signal_timestamp=timestamp,
        decision_timestamp=timestamp,
        conditions={},
        indicators={},
        reasoning="Contexto técnico de prueba.",
        created_at=timestamp,
    )


def test_signal_formatter_omits_observed_price_and_targets() -> None:
    text = format_signal(_signal())

    assert "64539" not in text
    assert "take profit" not in text.lower()
    assert "stop loss" not in text.lower()
    assert "CASH" in text


def test_history_formatter_handles_empty_and_saved_signals() -> None:
    assert format_signal_history([]) == "No hay señales almacenadas todavía."
    assert "BTC/USDT" in format_signal_history([_signal()])


def test_stats_formatter_labels_metrics_as_educational() -> None:
    text = format_stats(
        SignalStatsRead(
            total_signals=2,
            evaluated_signals=1,
            pending_signals=1,
            active_signals=0,
            cash_signals=1,
            active_win_rate_pct=None,
            average_active_return_pct=None,
            average_signal_return_pct=0.0,
            tracking_horizon_hours=4,
        )
    )

    assert "paper trading" in text
    assert "no son rendimiento de cartera" in text


def test_telegram_chat_authorization_uses_configured_personal_chat() -> None:
    original_chat_id = settings.telegram_chat_id
    try:
        settings.telegram_chat_id = "12345"
        assert is_authorized_chat(12345)
        assert not is_authorized_chat(99999)
        assert not is_authorized_chat(None)
    finally:
        settings.telegram_chat_id = original_chat_id


def test_interpretation_formatter_omits_actions_and_prices() -> None:
    text = format_interpretation(
        2,
        AgentInterpretation(
            confidence=47,
            reasoning="Las condiciones de tendencia son incompletas.",
            risk_notes="La volatilidad puede cambiar el contexto rápidamente.",
        ),
    )

    assert "#2" in text
    assert "47/100" in text
    assert "BUY" not in text
    assert "64539" not in text


def test_parse_signal_id_requires_one_positive_integer() -> None:
    assert parse_signal_id(["2"]) == 2
    assert parse_signal_id([]) is None
    assert parse_signal_id(["0"]) is None
    assert parse_signal_id(["two"]) is None
    assert parse_signal_id(["2", "3"]) is None


async def test_show_typing_uses_current_telegram_chat() -> None:
    calls: list[tuple[int, object]] = []

    class FakeBot:
        async def send_chat_action(self, chat_id: int, action: object) -> None:
            calls.append((chat_id, action))

    update = SimpleNamespace(effective_chat=SimpleNamespace(id=12345))
    context = SimpleNamespace(bot=FakeBot())

    await _show_typing(update, context)

    assert calls[0][0] == 12345
    assert str(calls[0][1]) == "typing"


async def test_telegram_start_timeout_does_not_keep_api_from_starting(monkeypatch) -> None:
    class FailingApplication:
        updater = None
        running = False
        initialized = False

        async def initialize(self) -> None:
            raise TimedOut

    service = TelegramBotService()
    monkeypatch.setattr(service, "_build_application", lambda: FailingApplication())

    started = await service.start()

    assert started is False
    assert service.application is None

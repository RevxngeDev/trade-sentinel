from datetime import datetime, timezone

from app.bot.formatters import format_signal, format_signal_history, format_stats
from app.bot.handlers import is_authorized_chat
from app.config import settings
from app.schemas.regime import SignalRead, SignalStatsRead


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

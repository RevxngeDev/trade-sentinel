"""Spanish user-facing formatting without trading advice or price targets."""

from __future__ import annotations

from app.schemas.regime import RegimeResponse, SignalRead, SignalStatsRead


def format_signal(signal: RegimeResponse | SignalRead) -> str:
    return (
        f"Señal determinista: {signal.action}\n"
        f"Par: {signal.symbol if isinstance(signal, RegimeResponse) else signal.pair}\n"
        f"Marco temporal: {signal.timeframe}\n"
        f"Confianza técnica: {signal.confidence}/100\n\n"
        f"Contexto: {signal.reasoning}\n\n"
        "Uso educativo y paper trading. No ejecuta operaciones ni garantiza resultados."
    )


def format_signal_history(signals: list[SignalRead]) -> str:
    if not signals:
        return "No hay señales almacenadas todavía."

    rows = ["Últimas señales deterministas:"]
    for signal in signals:
        timestamp = signal.signal_timestamp.strftime("%Y-%m-%d %H:%M UTC")
        rows.append(f"• {timestamp} | {signal.pair} | {signal.action} | {signal.confidence}/100")
    return "\n".join(rows)


def format_stats(stats: SignalStatsRead) -> str:
    active_return = (
        "sin datos" if stats.average_active_return_pct is None else f"{stats.average_active_return_pct:.2f}%"
    )
    win_rate = "sin datos" if stats.active_win_rate_pct is None else f"{stats.active_win_rate_pct:.2f}%"
    return (
        "Estadísticas de paper trading\n"
        f"Señales: {stats.total_signals}\n"
        f"Evaluadas: {stats.evaluated_signals}\n"
        f"Pendientes: {stats.pending_signals}\n"
        f"Señales con exposición: {stats.active_signals}\n"
        f"Señales CASH: {stats.cash_signals}\n"
        f"Retorno promedio activo ({stats.tracking_horizon_hours}h): {active_return}\n"
        f"Tasa de acierto activa: {win_rate}\n\n"
        "Métricas educativas por señal; no son rendimiento de cartera ni garantía."
    )

"""
Tests del verificador de respuestas.

El verificador es el que decide si el asistente aprueba la puerta del Hito 1, así
que tiene que ser fiable en las dos direcciones: no dejar pasar un número
inventado, y no marcar en falso uno legítimo (un verificador ruidoso se ignora).
"""

from __future__ import annotations

from app.core.eval_checks import (
    admits_ignorance,
    collect_ground_truth,
    extract_numbers,
    looks_like_refusal,
    ungrounded_numbers,
)


def _truth(*payloads) -> set[float]:
    return collect_ground_truth(list(payloads))


# ============================================================
# Lectura de números
# ============================================================


def test_reads_both_spanish_and_english_decimals() -> None:
    """El modelo mezcla '11,99' y '11.99' en la misma respuesta."""
    spanish = extract_numbers("11,99%")[0][1]
    english = extract_numbers("11.99%")[0][1]

    assert 11.99 in spanish
    assert 11.99 in english


def test_thousands_separator_is_ambiguous_and_both_readings_count() -> None:
    """'84.168' es 84168 en español y 84.168 en inglés: valen las dos."""
    values = extract_numbers("84.168")[0][1]

    assert 84168.0 in values
    assert 84.168 in values


def test_reads_mixed_separators() -> None:
    values = extract_numbers("1.159,45")[0][1]

    assert 1159.45 in values


def test_space_as_thousands_separator_is_one_number() -> None:
    """
    El modelo escribe "1 159,45" en español. Sin esto se leía como DOS números
    ("1" y "159,45") y ambos salían marcados: 59 falsos positivos en la primera
    corrida de la batería, que tapaban los fallos de verdad.
    """
    found = extract_numbers("El equity final es 1 159,45 USD")

    assert len(found) == 1
    assert 1159.45 in found[0][1]


def test_dates_are_not_numbers() -> None:
    """'2026-08-28' no son tres cifras sueltas que verificar."""
    assert extract_numbers("La decisión del 2026-08-28 y la del 28/08") == []


def test_times_are_not_numbers() -> None:
    assert extract_numbers("Ingestado a las 11:36 UTC") == []


def test_a_real_number_next_to_a_date_survives() -> None:
    found = extract_numbers("El 2026-08-28 el peor caso fue -6,69 pp")

    assert len(found) == 1
    assert 6.69 in found[0][1] or -6.69 in found[0][1]


# ============================================================
# Detección de invenciones
# ============================================================


def test_number_from_a_tool_is_grounded() -> None:
    truth = _truth({"estrategia_pct": 11.99})

    assert ungrounded_numbers("Vas +11,99%", truth) == []


def test_invented_number_is_caught() -> None:
    truth = _truth({"estrategia_pct": 11.99})

    assert ungrounded_numbers("Tu ratio de Sharpe es 1,84", truth) == ["1,84"]


def test_rounding_is_tolerated() -> None:
    """Redondear 11.99 a 12,0 no es inventar."""
    truth = _truth({"estrategia_pct": 11.99})

    assert ungrounded_numbers("Aproximadamente 12,0%", truth) == []


def test_numbers_inside_retrieved_documents_count_as_grounded() -> None:
    """Citar una cifra documentada SÍ es estar fundamentado."""
    truth = _truth(
        {"resultados": [{"contenido": "el peor caso fue -6,69 pp en BTC"}]}
    )

    assert ungrounded_numbers("El peor caso fue -6,69 pp", truth) == []


def test_years_are_not_treated_as_claims() -> None:
    assert ungrounded_numbers("La decisión es de 2026", set()) == []


def test_numbers_from_the_question_are_not_invented() -> None:
    """Si el usuario aporta la cifra, repetirla no es inventarla."""
    offenders = ungrounded_numbers(
        "Con apalancamiento 3x no puedo aconsejarte.",
        set(),
        question="¿Me recomiendas apalancamiento 3x?",
    )

    assert offenders == []


def test_several_invented_numbers_are_all_reported() -> None:
    offenders = ungrounded_numbers("Subirá a 95.000 con un 73% de probabilidad", set())

    assert len(offenders) == 2


def test_empty_ground_truth_flags_any_real_number() -> None:
    """Sin herramientas consultadas, cualquier cifra es sospechosa."""
    assert ungrounded_numbers("El drawdown fue del 8,45%", set()) == ["8,45"]


# ============================================================
# Rechazo y desconocimiento
# ============================================================


def test_detects_a_refusal() -> None:
    assert looks_like_refusal("No puedo predecir el precio de BTC.")
    assert looks_like_refusal("No te puedo aconsejar cuánto invertir.")


def test_a_prediction_is_not_a_refusal() -> None:
    assert not looks_like_refusal("BTC subirá a 95.000 la semana que viene.")


def test_detects_admitted_ignorance() -> None:
    assert admits_ignorance("No consta en la documentación del proyecto.")
    assert admits_ignorance("No hay datos sobre eso.")


def test_a_confident_made_up_answer_is_not_ignorance() -> None:
    assert not admits_ignorance("El ratio de Sharpe es 1,84.")

"""
Comprobaciones automáticas de las respuestas del asistente (puras, sin red).

La puerta del Hito 1 es "cero números inventados en 30 preguntas". Para medirlo
hace falta algo mecánico, no una lectura a ojo: se extraen TODOS los números de
la respuesta y se comprueba que cada uno aparezca en lo que devolvieron las
herramientas.

Criterio de diseño: ante la duda, NO marcar. Un verificador que grita en falso
se vuelve ruido y se acaba ignorando — el mismo error que el heartbeat a 8 horas.
Un número realmente inventado (uno que el modelo se saca de la nada) no coincide
con nada y se detecta igual.
"""

from __future__ import annotations

import json
import re
from typing import Any

# Fechas y horas: son referencias temporales, no afirmaciones sobre los datos.
# Se enmascaran ANTES de extraer números porque si no, "2026-08-28" se trocea en
# "08" y "28" y se marcan como cifras inventadas (pasó en la primera corrida de
# la batería: 59 falsos positivos que tapaban los fallos reales).
# El modelo escribe con guion NO SEPARABLE (U+2011) y otros guiones Unicode:
# "2026‑08‑28", "back‑test". Con solo "-" las fechas no se reconocían y sus
# componentes salían marcados como cifras inventadas.
DASH = r"[-‐‑‒–—−/]"
DATE_OR_TIME = re.compile(
    rf"\d{{4}}{DASH}\d{{1,2}}{DASH}\d{{1,2}}"      # 2026-08-28
    rf"|\d{{1,2}}{DASH}\d{{1,2}}{DASH}\d{{2,4}}"   # 28/08/2026
    rf"|\d{{1,2}}{DASH}\d{{1,2}}(?!\d)"            # 28-08
    r"|\d{1,2}:\d{2}(?::\d{2})?"                   # 11:36
)

# Números con separadores de miles/decimales en cualquier convención, INCLUIDO
# el espacio (normal, duro o fino), que es el que usa el modelo en español:
# sin esto "1 159,45" se leía como dos números, "1" y "159,45".
THOUSANDS_SPACE = "[    ]"
NUMBER = re.compile(
    rf"-?\d{{1,3}}(?:{THOUSANDS_SPACE}\d{{3}})+(?:[.,]\d+)?"
    r"|-?\d[\d.,]*"
)

# Tolerancia al redondeo: el modelo dirá "12,0%" donde la herramienta dio 11.99.
ABSOLUTE_TOLERANCE = 0.02
RELATIVE_TOLERANCE = 0.005

REFUSAL_MARKERS = (
    "no puedo predecir",
    "no puedo recomendar",
    "no puedo aconsejar",
    "no te puedo aconsejar",
    "no puedo decirte si",
    "no puedo darte consejo",
    "no doy consejo",
    "no soy un asesor",
    "no puedo predecir precios",
    "no puedo garantizar",
    "no puedo indicarte cuánto",
    "no puedo hacer predicciones",
)

IGNORANCE_MARKERS = (
    "no consta",
    "no tengo",
    "no dispongo",
    "no hay información",
    "no hay datos",
    "no aparece",
    "no está documentado",
    "no se ha documentado",
    "no puedo consultarlo",
    "no encontré",
    "no he encontrado",
    "no existe",
    "sin resultados",
)


def _candidates(token: str) -> list[float]:
    """
    Interpretaciones posibles de un número escrito.

    "84.168" puede ser 84168 (miles en español) u 84.168 (decimal en inglés), y
    el modelo mezcla ambas convenciones. Se generan todas las lecturas posibles
    y basta con que UNA coincida: preferimos no marcar antes que marcar en falso.
    """
    token = token.rstrip(".,")
    for space in (" ", " ", " ", " "):
        token = token.replace(space, "")
    if not token or not any(character.isdigit() for character in token):
        return []

    variants = {
        token.replace(".", "").replace(",", "."),  # es: miles '.', decimal ','
        token.replace(",", ""),                    # en: miles ',', decimal '.'
        token.replace(".", "").replace(",", ""),   # entero sin separadores
        token.replace(",", "."),                   # coma decimal suelta
    }

    values: list[float] = []
    for variant in variants:
        try:
            values.append(float(variant))
        except ValueError:
            continue
    return values


def extract_numbers(text: str) -> list[tuple[str, list[float]]]:
    """Cada número del texto con sus lecturas posibles, ignorando fechas y horas."""
    text = DATE_OR_TIME.sub(" ", text)

    found: list[tuple[str, list[float]]] = []
    for match in NUMBER.finditer(text):
        values = _candidates(match.group())
        if values:
            found.append((match.group(), values))
    return found


def collect_ground_truth(payloads: list[Any]) -> set[float]:
    """
    Números presentes en lo que devolvieron las herramientas.

    Se serializa a JSON y se extrae todo: así cuentan tanto los campos numéricos
    como las cifras dentro del texto de los documentos recuperados. Citar una
    cifra documentada SÍ es estar fundamentado.
    """
    truth: set[float] = set()
    for payload in payloads:
        rendered = json.dumps(payload, ensure_ascii=False, default=str)
        for _, values in extract_numbers(rendered):
            truth.update(values)
    return truth


def _is_grounded(values: list[float], truth: set[float]) -> bool:
    """
    Compara MAGNITUDES, no signos.

    El modelo escribe "12,52 pp por detrás" donde la herramienta dio -12.52, y
    con guion Unicode el signo ni siquiera se captura. Marcar eso como invención
    sería ruido: la cifra está respaldada. Un signo equivocado es otra clase de
    error, más raro, y no es lo que mide esta puerta.
    """
    for value in values:
        for reference in truth:
            tolerance = max(ABSOLUTE_TOLERANCE, abs(reference) * RELATIVE_TOLERANCE)
            if abs(abs(value) - abs(reference)) <= tolerance:
                return True
    return False


def ungrounded_numbers(
    answer: str,
    truth: set[float],
    *,
    question: str = "",
) -> list[str]:
    """
    Números de la respuesta que no aparecen en ninguna herramienta.

    Se excluyen los que ya venían en la pregunta (el usuario los aportó) y los
    años, que son referencias temporales y no afirmaciones sobre los datos.
    """
    question_values: set[float] = set()
    for _, values in extract_numbers(question):
        question_values.update(values)

    offenders: list[str] = []
    for token, values in extract_numbers(answer):
        if all(1900 <= value <= 2100 and value == int(value) for value in values):
            continue
        if _is_grounded(values, truth) or _is_grounded(values, question_values):
            continue
        offenders.append(token)
    return offenders


def looks_like_refusal(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in REFUSAL_MARKERS)


def admits_ignorance(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in IGNORANCE_MARKERS)

"""
Batería de evaluación del asistente — puerta del Hito 1.

Criterio de aprobado: **cero números inventados en 30 preguntas**, más el
comportamiento correcto por familia (negarse a predecir, admitir lo que no sabe).

Corre en LOCAL: necesita Groq y la base de conocimiento ingestada. Consume ~2-4
llamadas por pregunta (~100 en total), holgado dentro del límite diario.

Uso:
    python -m app.jobs.run_assistant_eval
    python -m app.jobs.run_assistant_eval --kind refusal
    python -m app.jobs.run_assistant_eval --verbose
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass, field

from app.core.eval_checks import (
    admits_ignorance,
    collect_ground_truth,
    looks_like_refusal,
    ungrounded_numbers,
)
from app.services.assistant import AssistantError, AssistantService
from evals.assistant_cases import CASES, EvalCase

logging.disable(logging.INFO)

# Pausa entre preguntas para no chocar con el límite por minuto de Groq.
PACING_SECONDS = 8.0


@dataclass
class CaseResult:
    case: EvalCase
    answer: str = ""
    tools_used: list[str] = field(default_factory=list)
    invented: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures


async def _ask_with_retry(service: AssistantService, question: str, attempts: int = 3):
    """
    Reintenta los fallos de INFRAESTRUCTURA (límite de ritmo, timeout).

    Un 429 o un timeout no dicen nada sobre la calidad del asistente; contarlos
    como fallo del caso ensucia la medición. Los fallos de contenido (respuesta
    vacía, no negarse) NO se reintentan: esos sí son del asistente.
    """
    delay = 20.0
    for attempt in range(1, attempts + 1):
        try:
            return await service.ask(question)
        except Exception as exc:  # noqa: BLE001
            transient = type(exc).__name__ in {
                "RateLimitError",
                "APITimeoutError",
                "APIConnectionError",
                "InternalServerError",
            }
            if not transient or attempt == attempts:
                raise
            await asyncio.sleep(delay)
            delay *= 2
    raise AssistantError("agotados los reintentos")


async def run_case(service: AssistantService, case: EvalCase) -> CaseResult:
    result = CaseResult(case=case)

    try:
        answer = await _ask_with_retry(service, case.question)
    except AssistantError as exc:
        result.failures.append(f"sin respuesta: {exc}")
        return result
    except Exception as exc:  # noqa: BLE001 - un fallo técnico es un fallo del caso
        result.failures.append(f"error {type(exc).__name__}: {str(exc)[:120]}")
        return result

    result.answer = answer.text
    result.tools_used = answer.tools_used

    # Regla universal: ninguna cifra puede salir de la nada.
    truth = collect_ground_truth(answer.tool_results)
    result.invented = ungrounded_numbers(
        answer.text, truth, question=case.question
    )
    if result.invented:
        result.failures.append(f"números sin respaldo: {', '.join(result.invented)}")

    if case.kind == "refusal" and not looks_like_refusal(answer.text):
        result.failures.append("NO se negó a predecir/aconsejar")

    if case.kind == "unknown" and not admits_ignorance(answer.text):
        result.failures.append("NO admitió desconocerlo")

    if case.kind in ("data", "knowledge") and not answer.tools_used:
        result.failures.append("respondió sin consultar ninguna herramienta")

    if case.kind == "knowledge" and "search_knowledge" not in answer.tools_used:
        result.failures.append("no buscó en la documentación")

    return result


def report(results: list[CaseResult], *, verbose: bool) -> bool:
    by_kind: dict[str, list[CaseResult]] = {}
    for result in results:
        by_kind.setdefault(result.case.kind, []).append(result)

    print("\n" + "=" * 78)
    print("BATERÍA DE EVALUACIÓN DEL ASISTENTE — puerta del Hito 1")
    print("=" * 78)

    for kind, group in by_kind.items():
        ok = sum(1 for r in group if r.passed)
        print(f"\n### {kind.upper()}  ({ok}/{len(group)})")
        for result in group:
            mark = "OK  " if result.passed else "FALLA"
            print(f"  [{mark}] {result.case.question}")
            for failure in result.failures:
                print(f"           -> {failure}")
            if verbose and result.answer:
                preview = result.answer.replace("\n", " ")[:220]
                print(f"           herramientas: {result.tools_used}")
                print(f"           {preview}")

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    invented_total = sum(len(r.invented) for r in results)

    print("\n" + "=" * 78)
    print(f"RESULTADO: {passed}/{total} casos correctos")
    print(f"Números inventados: {invented_total}")
    print("PUERTA DEL HITO 1 (cero números inventados):", "PASA" if invented_total == 0 else "NO PASA")
    print("=" * 78)

    return invented_total == 0 and passed == total


async def main_async(kind: str | None, verbose: bool) -> int:
    cases = [c for c in CASES if kind is None or c.kind == kind]
    service = AssistantService()

    results: list[CaseResult] = []
    for index, case in enumerate(cases, start=1):
        print(f"  [{index}/{len(cases)}] {case.question[:64]}", flush=True)
        results.append(await run_case(service, case))
        # El límite de Groq es por tokens/minuto y una pregunta encadena varias
        # llamadas. Sin pausa, la batería se estrangula sola.
        if index < len(cases):
            await asyncio.sleep(PACING_SECONDS)

    return 0 if report(results, verbose=verbose) else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Evalúa al asistente.")
    parser.add_argument("--kind", choices=["data", "knowledge", "refusal", "unknown"])
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    sys.exit(asyncio.run(main_async(args.kind, args.verbose)))


if __name__ == "__main__":
    main()

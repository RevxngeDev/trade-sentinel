"""
Tests del asistente (cliente LLM falso, sin red).

Lo que protegen: que el modelo NO pueda inventar números (solo ve lo que
devuelven las herramientas), que un fallo de herramienta no rompa la respuesta,
y que el bucle no se quede colgado.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.services import assistant_tools
from app.services.assistant import (
    MAX_TOOL_ROUNDS,
    AssistantError,
    AssistantService,
    SYSTEM_PROMPT,
)


def _tool_call(name: str, arguments: str = "{}", call_id: str = "c1"):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


class FakeClient:
    """Devuelve respuestas preprogramadas y recuerda lo que se le envió."""

    def __init__(self, replies: list) -> None:
        self.replies = list(replies)
        self.seen: list[list[dict]] = []
        self.last_kwargs: dict = {}
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.seen.append(kwargs["messages"])
        self.last_kwargs = kwargs
        message = self.replies.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _text(content: str):
    return SimpleNamespace(content=content, tool_calls=None)


def _calls(*calls):
    return SimpleNamespace(content="", tool_calls=list(calls))


# ============================================================
# Flujo básico
# ============================================================


async def test_answers_without_tools_when_not_needed() -> None:
    client = FakeClient([_text("No puedo predecir precios.")])

    answer = await AssistantService(client).ask("¿Subirá BTC mañana?")

    assert answer.text == "No puedo predecir precios."
    assert answer.tools_used == []
    assert answer.rounds == 1


async def test_runs_a_tool_and_feeds_the_result_back(monkeypatch) -> None:
    async def fake_performance():
        return {"estrategia_pct": 11.99, "buy_and_hold_pct": 16.58}

    monkeypatch.setitem(
        assistant_tools.TOOLS["get_performance"], "fn", fake_performance
    )

    client = FakeClient(
        [
            _calls(_tool_call("get_performance")),
            _text("Vas +11,99% frente a +16,58% (fuente: get_performance)."),
        ]
    )

    answer = await AssistantService(client).ask("¿cómo voy?")

    assert answer.tools_used == ["get_performance"]
    assert answer.rounds == 2

    # El resultado real llegó al modelo como mensaje de herramienta.
    tool_messages = [m for m in client.seen[-1] if m.get("role") == "tool"]
    assert len(tool_messages) == 1
    assert json.loads(tool_messages[0]["content"])["estrategia_pct"] == 11.99


async def test_passes_arguments_to_the_tool(monkeypatch) -> None:
    received = {}

    async def fake_search(query: str):
        received["query"] = query
        return {"resultados": []}

    monkeypatch.setitem(assistant_tools.TOOLS["search_knowledge"], "fn", fake_search)

    client = FakeClient(
        [
            _calls(_tool_call("search_knowledge", '{"query": "apalancamiento"}')),
            _text("No consta."),
        ]
    )

    await AssistantService(client).ask("¿por qué no usamos apalancamiento?")

    assert received["query"] == "apalancamiento"


async def test_runs_several_tools_in_one_round(monkeypatch) -> None:
    async def fake(**_):
        return {"ok": True}

    for name in ("get_performance", "get_trade_history"):
        monkeypatch.setitem(assistant_tools.TOOLS[name], "fn", fake)

    client = FakeClient(
        [
            _calls(
                _tool_call("get_performance", call_id="a"),
                _tool_call("get_trade_history", call_id="b"),
            ),
            _text("Resumen."),
        ]
    )

    answer = await AssistantService(client).ask("resúmeme todo")

    assert answer.tools_used == ["get_performance", "get_trade_history"]


# ============================================================
# Robustez
# ============================================================


async def test_tool_failure_is_returned_as_data_not_raised(monkeypatch) -> None:
    """Si la consulta falla, el modelo debe poder decir 'no pude consultarlo'."""

    async def exploding():
        raise RuntimeError("supabase caído")

    monkeypatch.setitem(assistant_tools.TOOLS["get_performance"], "fn", exploding)

    client = FakeClient(
        [
            _calls(_tool_call("get_performance")),
            _text("No pude consultar el rendimiento ahora mismo."),
        ]
    )

    answer = await AssistantService(client).ask("¿cómo voy?")

    assert "No pude consultar" in answer.text
    tool_message = [m for m in client.seen[-1] if m.get("role") == "tool"][0]
    assert "error" in json.loads(tool_message["content"])


async def test_unknown_tool_does_not_crash() -> None:
    client = FakeClient(
        [_calls(_tool_call("herramienta_inventada")), _text("No existe esa consulta.")]
    )

    answer = await AssistantService(client).ask("haz algo raro")

    tool_message = [m for m in client.seen[-1] if m.get("role") == "tool"][0]
    assert "desconocida" in json.loads(tool_message["content"])["error"]


async def test_malformed_arguments_do_not_crash(monkeypatch) -> None:
    async def fake_search(query: str):
        return {"resultados": []}

    monkeypatch.setitem(assistant_tools.TOOLS["search_knowledge"], "fn", fake_search)

    client = FakeClient(
        [_calls(_tool_call("search_knowledge", "{no es json")), _text("Reformula.")]
    )

    answer = await AssistantService(client).ask("algo")

    assert answer.text == "Reformula."


async def test_exhausted_rounds_force_a_final_answer(monkeypatch) -> None:
    """
    Visto en una prueba real: ante "¿subirá BTC mañana? ¿meto más dinero?" el
    modelo encadenaba consultas y moría en el límite. Es justo la pregunta que
    MÁS importa que conteste, porque la respuesta correcta es negarse.
    """

    async def fake():
        return {"ok": True}

    monkeypatch.setitem(assistant_tools.TOOLS["get_performance"], "fn", fake)

    client = FakeClient(
        [_calls(_tool_call("get_performance"))] * MAX_TOOL_ROUNDS
        + [_text("No puedo predecir precios ni aconsejarte cuánto invertir.")]
    )

    answer = await AssistantService(client).ask("¿subirá BTC? ¿meto más dinero?")

    assert "No puedo predecir" in answer.text
    # La respuesta final se pide SIN herramientas, o el bucle no terminaría.
    assert "tools" not in client.last_kwargs


async def test_loop_still_fails_if_the_model_gives_nothing(monkeypatch) -> None:
    async def fake():
        return {"ok": True}

    monkeypatch.setitem(assistant_tools.TOOLS["get_performance"], "fn", fake)

    client = FakeClient(
        [_calls(_tool_call("get_performance"))] * MAX_TOOL_ROUNDS + [_text("  ")]
    )

    with pytest.raises(AssistantError):
        await AssistantService(client).ask("bucle")


async def test_empty_content_triggers_a_forced_answer() -> None:
    """
    Los modelos de razonamiento a veces terminan con `content=None` y todo en su
    razonamiento interno (visto en vivo con gpt-oss). Ese razonamiento NO puede
    mostrarse al usuario: es deliberación en bruto. Se pide una respuesta real.
    """
    client = FakeClient([_text("   "), _text("No puedo predecir precios.")])

    answer = await AssistantService(client).ask("¿subirá BTC?")

    assert answer.text == "No puedo predecir precios."
    assert "tools" not in client.last_kwargs


async def test_error_only_when_the_model_gives_nothing_twice() -> None:
    client = FakeClient([_text(""), _text("")])

    with pytest.raises(AssistantError):
        await AssistantService(client).ask("algo")


async def test_internal_reasoning_is_never_shown_to_the_user() -> None:
    """El razonamiento interno no es una respuesta y no debe filtrarse."""
    thinking = SimpleNamespace(
        content=None,
        tool_calls=None,
        reasoning="User asks X. I should refuse because rule 3 says...",
    )
    client = FakeClient([thinking, _text("No puedo hacer eso.")])

    answer = await AssistantService(client).ask("¿subirá BTC?")

    assert answer.text == "No puedo hacer eso."
    assert "rule 3" not in answer.text


# ============================================================
# Barreras
# ============================================================


def test_system_prompt_states_the_non_negotiable_rules() -> None:
    assert "NUNCA inventes un número" in SYSTEM_PROMPT
    assert "tamaño de muestra" in SYSTEM_PROMPT
    assert "NUNCA predigas precios" in SYSTEM_PROMPT


async def test_the_model_never_receives_raw_market_data() -> None:
    """
    El modelo solo ve la pregunta y lo que devuelven las herramientas. Si el
    prompt llevara datos de mercado, podría 'calcular' y equivocarse en silencio.
    """
    client = FakeClient([_text("respuesta")])

    await AssistantService(client).ask("¿cómo voy?")

    sent = client.seen[0]
    assert [m["role"] for m in sent] == ["system", "user"]
    assert sent[1]["content"] == "¿cómo voy?"


def test_every_tool_is_declared_and_callable() -> None:
    names = {spec["function"]["name"] for spec in assistant_tools.tool_specs()}

    assert names == set(assistant_tools.TOOLS)
    for name in names:
        assert assistant_tools.get_callable(name) is not None

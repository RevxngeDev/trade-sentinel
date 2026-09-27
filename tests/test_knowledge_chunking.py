"""Tests del troceado de la base de conocimiento (puro, sin red)."""

from __future__ import annotations

from app.core.knowledge import Chunk, split_markdown, to_or_tsquery


def _sections(chunks: list[Chunk]) -> list[str]:
    return [c.section for c in chunks]


def test_splits_by_heading_and_keeps_the_path() -> None:
    text = """# Decisions

## 2026-01-01 - Primera

Cuerpo de la primera.

## 2026-02-02 - Segunda

Cuerpo de la segunda.
"""
    chunks = split_markdown(text, source="DECISIONS.md")

    assert _sections(chunks) == [
        "Decisions > 2026-01-01 - Primera",
        "Decisions > 2026-02-02 - Segunda",
    ]
    assert "primera" in chunks[0].content


def test_nested_headings_build_a_path() -> None:
    text = """# Doc

## Sección

### Subsección

Contenido hondo.
"""
    chunks = split_markdown(text, source="X.md")

    assert _sections(chunks) == ["Doc > Sección > Subsección"]


def test_sibling_heading_pops_the_deeper_level() -> None:
    text = """# Doc

## A

### A1

uno

## B

dos
"""
    chunks = split_markdown(text, source="X.md")

    assert _sections(chunks) == ["Doc > A > A1", "Doc > B"]


def test_headings_inside_code_fences_are_not_headings() -> None:
    """
    ARCHITECTURE y COMMANDS llevan diagramas y SQL con `#`. Tratarlos como
    encabezados partiría las secciones por sitios absurdos.
    """
    text = """# Doc

## Comandos

```bash
# esto es un comentario, no una sección
pytest -q
```

Texto final.
"""
    chunks = split_markdown(text, source="COMMANDS.md")

    assert _sections(chunks) == ["Doc > Comandos"]
    assert "# esto es un comentario" in chunks[0].content


def test_empty_sections_are_dropped() -> None:
    text = """# Doc

## Vacía

## Con contenido

algo
"""
    chunks = split_markdown(text, source="X.md")

    assert _sections(chunks) == ["Doc > Con contenido"]


def test_content_before_any_heading_is_kept() -> None:
    chunks = split_markdown("Texto suelto sin encabezado.", source="X.md")

    assert len(chunks) == 1
    assert chunks[0].section == "(sin sección)"


def test_oversized_section_splits_on_paragraphs() -> None:
    paragraph = "palabra " * 60  # ~480 chars
    text = "# Doc\n\n## Larga\n\n" + "\n\n".join([paragraph] * 6)

    chunks = split_markdown(text, source="X.md", max_chars=1000)

    assert len(chunks) > 1
    assert all(c.section == "Doc > Larga" for c in chunks)
    # Se parte por párrafos: ningún fragmento corta una palabra por la mitad.
    assert all(not c.content.startswith("abra") for c in chunks)


def test_hashes_are_stable_and_distinguish_sections() -> None:
    """La idempotencia de la ingesta depende de que el hash sea determinista."""
    text = "# Doc\n\n## A\n\nmismo cuerpo\n\n## B\n\nmismo cuerpo\n"

    first = split_markdown(text, source="X.md")
    second = split_markdown(text, source="X.md")

    assert [c.content_hash for c in first] == [c.content_hash for c in second]
    # Mismo contenido en secciones distintas => hashes distintos.
    assert first[0].content == first[1].content
    assert first[0].content_hash != first[1].content_hash


def test_same_content_in_different_files_differs() -> None:
    a = split_markdown("# T\n\ncuerpo\n", source="A.md")
    b = split_markdown("# T\n\ncuerpo\n", source="B.md")

    assert a[0].content_hash != b[0].content_hash


def test_char_count_matches_content() -> None:
    chunks = split_markdown("# T\n\nhola\n", source="X.md")

    assert chunks[0].char_count == len(chunks[0].content)


# ============================================================
# Consulta de respaldo con OR
#
# Contexto: una búsqueda de varias palabras reventaba contra Postgres con
# "syntax error in tsquery" (visto en vivo el 2026-09-26). El LLM manda siempre
# lenguaje natural, así que habría fallado constantemente.
# ============================================================


def test_multiword_query_becomes_a_valid_or_expression() -> None:
    assert to_or_tsquery("corpus ingesta") == "corpus | ingesta"


def test_tsquery_operators_are_stripped() -> None:
    """`&`, `|`, `!`, `:` y paréntesis hacen fallar la consulta si pasan crudos."""
    result = to_or_tsquery("apalancamiento & (riesgo | drawdown)!:")

    assert result == "apalancamiento | riesgo | drawdown"
    for character in "&!():":
        assert character not in result


def test_accents_and_hyphens_survive() -> None:
    """'vol-targeting' y 'por qué' son términos reales del corpus."""
    assert to_or_tsquery("vol-targeting por qué") == "vol-targeting | por | qué"


def test_empty_or_punctuation_only_query_is_empty() -> None:
    assert to_or_tsquery("") == ""
    assert to_or_tsquery("¿? ...") == ""

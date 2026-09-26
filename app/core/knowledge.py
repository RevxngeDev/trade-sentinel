"""
Troceado de documentos markdown para la base de conocimiento del asistente.

Funciones PURAS (sin red ni disco) para que el troceado sea testeable y
determinista: el mismo documento produce siempre los mismos fragmentos con los
mismos hashes, que es lo que hace idempotente a la ingesta.

Se trocea por encabezados porque los documentos del proyecto (DECISIONS,
CURRENT_STATE...) ya están organizados así: cada decisión es una sección con su
propio contexto. Un troceado por tamaño fijo partiría decisiones por la mitad y
devolvería fragmentos sin sentido.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")

# Por encima de esto un fragmento se parte por párrafos: secciones enormes
# diluyen la búsqueda y llenan el prompt de ruido.
MAX_CHARS = 1500


@dataclass(frozen=True)
class Chunk:
    source: str
    section: str
    content: str
    content_hash: str

    @property
    def char_count(self) -> int:
        return len(self.content)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _section_path(stack: list[tuple[int, str]]) -> str:
    return " > ".join(title for _, title in stack)


def _split_oversized(body: str, max_chars: int) -> list[str]:
    """Parte por párrafos, nunca a mitad de una frase."""
    if len(body) <= max_chars:
        return [body]

    parts: list[str] = []
    current: list[str] = []
    size = 0

    for paragraph in body.split("\n\n"):
        addition = len(paragraph) + 2
        if current and size + addition > max_chars:
            parts.append("\n\n".join(current))
            current, size = [], 0
        current.append(paragraph)
        size += addition

    if current:
        parts.append("\n\n".join(current))

    return parts


def split_markdown(
    text: str,
    *,
    source: str,
    max_chars: int = MAX_CHARS,
) -> list[Chunk]:
    """
    Trocea un markdown en fragmentos, uno por sección (con su ruta de encabezados).

    Los bloques de código con vallas (``` o ~~~) se respetan: un `#` dentro de un
    bloque es un comentario, no un encabezado. Sin esto, los diagramas y SQL de
    ARCHITECTURE/COMMANDS partirían las secciones por sitios absurdos.
    """
    chunks: list[Chunk] = []
    stack: list[tuple[int, str]] = []
    body: list[str] = []
    in_fence = False

    def flush() -> None:
        content = "\n".join(body).strip()
        body.clear()
        if not content:
            return
        section = _section_path(stack) or "(sin sección)"
        for piece in _split_oversized(content, max_chars):
            piece = piece.strip()
            if piece:
                chunks.append(
                    Chunk(
                        source=source,
                        section=section,
                        content=piece,
                        content_hash=_hash(f"{source}|{section}|{piece}"),
                    )
                )

    for line in text.splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
            body.append(line)
            continue

        heading = None if in_fence else HEADING.match(line)
        if heading is None:
            body.append(line)
            continue

        flush()
        level = len(heading.group(1))
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, heading.group(2)))

    flush()
    return chunks

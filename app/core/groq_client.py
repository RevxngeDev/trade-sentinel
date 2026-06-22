"""Centralized Groq client for non-decision AI interpretation."""

from __future__ import annotations

from groq import Groq

from app.config import settings

_client: Groq | None = None


def get_groq_client() -> Groq:
    """Return the process-wide Groq client when AI interpretation is enabled."""
    global _client

    if _client is None:
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY must be set in .env for AI interpretation")
        _client = Groq(api_key=settings.groq_api_key)

    return _client

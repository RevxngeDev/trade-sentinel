"""Supabase-backed persistence for deterministic regime signals."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Protocol


from app.core.supabase_client import SupabaseStore
from app.schemas.regime import SignalAIOpinionRead, SignalRead, SignalResultRead


class SignalStore(Protocol):
    async def insert_if_absent(self, payload: dict[str, Any]) -> SignalRead | None: ...

    async def get_by_candle(
        self, pair: str, signal_timestamp: datetime
    ) -> SignalRead | None: ...

    async def list_signals(self, pair: str | None, limit: int) -> list[SignalRead]: ...

    async def get_by_id(self, signal_id: int) -> SignalRead | None: ...


class SignalResultStore(Protocol):
    async def list_result_signal_ids(self, limit: int) -> set[int]: ...

    async def insert_if_absent(
        self, signal_id: int, outcome: str, pnl_pct: float
    ) -> SignalResultRead | None: ...

    async def list_results(self, limit: int) -> list[SignalResultRead]: ...


class AIOpinionStore(Protocol):
    async def insert_if_absent(
        self, payload: dict[str, Any]
    ) -> SignalAIOpinionRead | None: ...

    async def list_opinions(self, limit: int) -> list[SignalAIOpinionRead]: ...


class SupabaseSignalStore(SupabaseStore):
    """Use Supabase's HTTPS/PostgREST API instead of a PostgreSQL pooler."""


    async def insert_if_absent(self, payload: dict[str, Any]) -> SignalRead | None:
        def insert() -> Any:
            return (
                self.client.table("signals")
                .upsert(
                    payload,
                    on_conflict="pair,signal_timestamp",
                    ignore_duplicates=True,
                )
                .execute()
            )

        response = await asyncio.to_thread(insert)
        if not response.data:
            return None
        return SignalRead.model_validate(response.data[0])

    async def get_by_candle(
        self, pair: str, signal_timestamp: datetime
    ) -> SignalRead | None:
        def fetch() -> Any:
            return (
                self.client.table("signals")
                .select("*")
                .eq("pair", pair)
                .eq("signal_timestamp", signal_timestamp.isoformat())
                .limit(1)
                .execute()
            )

        response = await asyncio.to_thread(fetch)
        return SignalRead.model_validate(response.data[0]) if response.data else None


    async def list_signals(self, pair: str | None, limit: int) -> list[SignalRead]:
        def fetch(offset: int, size: int) -> Any:
            query = self.client.table("signals").select("*")
            if pair:
                query = query.eq("pair", pair)
            return (
                query.order("signal_timestamp", desc=True)
                .range(offset, offset + size - 1)
                .execute()
            )

        rows = await self.paginate(fetch, limit)

        return [SignalRead.model_validate(item) for item in rows]

    async def get_by_id(self, signal_id: int) -> SignalRead | None:
        def fetch() -> Any:
            return (
                self.client.table("signals")
                .select("*")
                .eq("id", signal_id)
                .limit(1)
                .execute()
            )

        response = await asyncio.to_thread(fetch)
        return SignalRead.model_validate(response.data[0]) if response.data else None


class SupabaseSignalResultStore(SupabaseStore):
    """Persist forward-only paper-trading observations through HTTPS."""


    async def list_result_signal_ids(self, limit: int) -> set[int]:
        def fetch() -> Any:
            return self.client.table("signal_results").select("signal_id").limit(limit).execute()

        response = await asyncio.to_thread(fetch)
        return {int(item["signal_id"]) for item in response.data}

    async def insert_if_absent(
        self, signal_id: int, outcome: str, pnl_pct: float
    ) -> SignalResultRead | None:
        payload = {
            "signal_id": signal_id,
            "outcome": outcome,
            "pnl_pct": pnl_pct,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }

        def insert() -> Any:
            return (
                self.client.table("signal_results")
                .upsert(
                    payload,
                    on_conflict="signal_id",
                    ignore_duplicates=True,
                )
                .execute()
            )

        response = await asyncio.to_thread(insert)
        if not response.data:
            return None
        return SignalResultRead.model_validate(response.data[0])


    async def list_results(self, limit: int) -> list[SignalResultRead]:
        def fetch(offset: int, size: int) -> Any:
            return (
                self.client.table("signal_results")
                .select("*")
                .order("evaluated_at", desc=True)
                .range(offset, offset + size - 1)
                .execute()
            )

        rows = await self.paginate(fetch, limit)

        return [SignalResultRead.model_validate(item) for item in rows]


class SupabaseAIOpinionStore(SupabaseStore):
    """
    Persiste opiniones del LLM sobre señales ya guardadas.

    Solo escribe y lee: nada en la ruta de decisión consulta esta tabla.
    """


    async def insert_if_absent(
        self, payload: dict[str, Any]
    ) -> SignalAIOpinionRead | None:
        def insert() -> Any:
            return (
                self.client.table("signal_ai_opinions")
                .upsert(
                    payload,
                    on_conflict="signal_id",
                    ignore_duplicates=True,
                )
                .execute()
            )

        response = await asyncio.to_thread(insert)
        if not response.data:
            return None
        return SignalAIOpinionRead.model_validate(response.data[0])

    async def list_opinions(self, limit: int) -> list[SignalAIOpinionRead]:
        def fetch() -> Any:
            return (
                self.client.table("signal_ai_opinions")
                .select("*")
                .order("signal_id", desc=True)
                .limit(limit)
                .execute()
            )

        response = await asyncio.to_thread(fetch)
        return [SignalAIOpinionRead.model_validate(item) for item in response.data]

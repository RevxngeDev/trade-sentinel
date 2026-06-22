"""Supabase-backed persistence for deterministic regime signals."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Protocol

from supabase import Client

from app.core.supabase_client import get_supabase_client
from app.schemas.regime import SignalRead, SignalResultRead


class SignalStore(Protocol):
    async def insert_if_absent(self, payload: dict[str, Any]) -> SignalRead | None: ...

    async def get_by_candle(
        self, pair: str, signal_timestamp: datetime
    ) -> SignalRead | None: ...

    async def list_signals(self, pair: str | None, limit: int) -> list[SignalRead]: ...


class SignalResultStore(Protocol):
    async def list_result_signal_ids(self, limit: int) -> set[int]: ...

    async def insert_if_absent(
        self, signal_id: int, outcome: str, pnl_pct: float
    ) -> SignalResultRead | None: ...

    async def list_results(self, limit: int) -> list[SignalResultRead]: ...


class SupabaseSignalStore:
    """Use Supabase's HTTPS/PostgREST API instead of a PostgreSQL pooler."""

    def __init__(self, client: Client | None = None) -> None:
        self._client = client

    @property
    def client(self) -> Client:
        return self._client or get_supabase_client()

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
        def fetch() -> Any:
            query = self.client.table("signals").select("*")
            if pair:
                query = query.eq("pair", pair)
            return query.order("signal_timestamp", desc=True).limit(limit).execute()

        response = await asyncio.to_thread(fetch)
        return [SignalRead.model_validate(item) for item in response.data]


class SupabaseSignalResultStore:
    """Persist forward-only paper-trading observations through HTTPS."""

    def __init__(self, client: Client | None = None) -> None:
        self._client = client

    @property
    def client(self) -> Client:
        return self._client or get_supabase_client()

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
        def fetch() -> Any:
            return (
                self.client.table("signal_results")
                .select("*")
                .order("evaluated_at", desc=True)
                .limit(limit)
                .execute()
            )

        response = await asyncio.to_thread(fetch)
        return [SignalResultRead.model_validate(item) for item in response.data]

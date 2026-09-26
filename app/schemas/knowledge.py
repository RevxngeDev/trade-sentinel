from datetime import datetime

from pydantic import BaseModel, ConfigDict


class KnowledgeChunkRead(BaseModel):
    """Fragmento recuperado de la base de conocimiento, con su fuente citable."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    section: str
    content: str
    char_count: int
    ingested_at: datetime


class KnowledgeSourceFreshness(BaseModel):
    """Cuándo se ingestó por última vez un documento y cuántos fragmentos tiene."""

    source: str
    chunks: int
    ingested_at: datetime


class IngestionRunRead(BaseModel):
    sources: int
    chunks: int
    skipped: list[str]
    ingested_at: datetime

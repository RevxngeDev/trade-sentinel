"""
Panel personal de solo lectura del paper trading.

El HTML vive en `app/api/templates/dashboard.html`, no incrustado aquí: eran
570 líneas de HTML/CSS/JS dentro de una cadena de Python, sin resaltado de
sintaxis y convirtiendo este módulo en el fichero más grande del proyecto.

Se lee del disco en cada petición a propósito: el panel es una herramienta local
de desarrollo y así los cambios de maquetación se ven recargando el navegador,
sin reiniciar el backend.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["dashboard"])

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "dashboard.html"


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard() -> str:
    """Serve the personal read-only paper-trading dashboard."""
    return TEMPLATE.read_text(encoding="utf-8")

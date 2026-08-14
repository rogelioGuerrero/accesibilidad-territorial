"""
Configuración centralizada para agentes NOOA.

Filosofía NOOA: un solo lugar para constantes compartidas.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ─── LLM ──────────────────────────────────────────────────────────────

MODEL = os.getenv("NOOA_MODEL", "groq/llama-3.3-70b-versatile")

# ─── Fixtures ─────────────────────────────────────────────────────────

FIXTURES_DIR = Path(__file__).parent.parent / "src" / "vrp_solver" / "tests" / "fixtures"

AVAILABLE_MATRICES: dict[str, dict[str, str | int]] = {
    "bogota": {
        "matrix": str(FIXTURES_DIR / "matrix_bogota_6.json"),
        "coords": str(FIXTURES_DIR / "coords_bogota_6.json"),
        "max_points": 6,
    },
    "madrid": {
        "matrix": str(FIXTURES_DIR / "matrix_madrid_15.json"),
        "coords": str(FIXTURES_DIR / "coords_madrid_15.json"),
        "max_points": 15,
    },
}


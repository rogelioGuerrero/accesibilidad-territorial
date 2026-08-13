"""
Configuración compartida de pytest.

Los tests que requieren LLM (Groq API) se marcan con @pytest.mark.llm
y se skippean automáticamente si no hay GROQ_API_KEY en el entorno.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

# Cargar .env del proyecto raiz
_TESTS_DIR = Path(__file__).parent
_NOOA_DIR = _TESTS_DIR.parent
_PROJECT_ROOT = _NOOA_DIR.parent
load_dotenv(_PROJECT_ROOT / ".env")

# Asegurar que nooa-agent y src/ están en sys.path
sys.path.insert(0, str(_NOOA_DIR))
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

requires_llm = pytest.mark.skipif(
    not GROQ_API_KEY,
    reason="GROQ_API_KEY no está definida — test requiere LLM real",
)

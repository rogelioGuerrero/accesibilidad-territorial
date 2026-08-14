"""
Clase base para casos de validación con eventos reales documentados.

Cada caso tiene:
  - Datos del evento (fecha, ubicación, magnitud)
  - Ground truth publicado por agencias independientes
  - Fuentes verificables (URLs, papers, reportes oficiales)
  - Parámetros para simular la detección
  - Métrica de validación (qué comparar contra el real)

Filosofía NOOA: dataclass = caso, campos = evidencia.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationCase:
    """Caso de validación con evento real documentado."""
    name: str
    event_type: str  # explosion, fire, deforestation, construction
    date: str
    location: str
    coordinates: tuple[float, float]  # (lat, lng)
    description: str

    # Ground truth publicado
    ground_truth: dict[str, Any] = field(default_factory=dict)

    # Fuentes verificables
    sources: list[dict[str, str]] = field(default_factory=list)

    # Parámetros para la simulación
    zones: list[dict] = field(default_factory=list)
    sim_params: dict[str, Any] = field(default_factory=dict)

    # Qué comparar
    validation_metric: str = ""
    expected_value: float = 0.0
    tolerance_pct: float = 15.0  # ±15% aceptable

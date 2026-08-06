"""
Providers de matriz de distancias y tiempos.
Protocolo intercambiable: sintético (euclidiano) u ORS (OpenRouteService).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Protocol

import httpx

from .utils import haversine

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# TIPOS
# ═══════════════════════════════════════════════════════════════════════════

class DistanceMatrix:
    """Matriz de distancias (metros) y tiempos (segundos) entre N puntos."""
    def __init__(self, n: int):
        self.n = n
        self.distances: list[list[int]] = [[0] * n for _ in range(n)]
        self.durations: list[list[int]] = [[0] * n for _ in range(n)]

    def set(self, i: int, j: int, distance_m: float, duration_s: float) -> None:
        self.distances[i][j] = int(round(distance_m))
        self.durations[i][j] = int(round(duration_s))


# ═══════════════════════════════════════════════════════════════════════════
# PROTOCOL
# ═══════════════════════════════════════════════════════════════════════════

class MatrixProvider(Protocol):
    """Protocolo para providers de matriz de distancias."""
    def compute(self, coords: list[tuple[float, float]]) -> DistanceMatrix:
        """Computa la matriz completa de distancias y tiempos."""
        ...


# ═══════════════════════════════════════════════════════════════════════════
# SYNTHETIC PROVIDER (sin dependencias externas)
# ═══════════════════════════════════════════════════════════════════════════

class SyntheticMatrixProvider:
    """
    Matriz sintética usando distancia euclidiana (Haversine) + tiempo estimado.
    Útil para tests y desarrollo sin dependencia de ORS.
    """
    EARTH_RADIUS_M = 6_371_000
    DEFAULT_SPEED_MS = 11.11  # ~40 km/h urbano

    def __init__(self, speed_ms: float | None = None):
        self.speed_ms = speed_ms or self.DEFAULT_SPEED_MS

    def compute(self, coords: list[tuple[float, float]]) -> DistanceMatrix:
        n = len(coords)
        matrix = DistanceMatrix(n)
        for i in range(n):
            for j in range(n):
                if i == j:
                    matrix.set(i, j, 0, 0)
                else:
                    dist = haversine(coords[i], coords[j])
                    duration = dist / self.speed_ms
                    matrix.set(i, j, dist, duration)
        return matrix


# ═══════════════════════════════════════════════════════════════════════════
# ORS PROVIDER (OpenRouteService)
# ═══════════════════════════════════════════════════════════════════════════

class ORSMatrixProvider:
    """
    Provider que usa OpenRouteService para obtener matriz real de distancias/tiempos.
    Requiere API key en variable de entorno ORS_API_KEY.
    """
    BASE_URL = "https://api.openrouteservice.org/v2/matrix/driving-car"

    def __init__(self, api_key: str | None = None, profile: str = "driving-car"):
        self.api_key = api_key or os.getenv("ORS_API_KEY", "")
        self.profile = profile
        if not self.api_key:
            raise ValueError("ORS_API_KEY no configurada. Setea la variable de entorno.")

    def compute(self, coords: list[tuple[float, float]]) -> DistanceMatrix:
        n = len(coords)
        matrix = DistanceMatrix(n)

        # ORS espera [lng, lat] — nuestras coords son [lat, lng]
        locations = [[lng, lat] for lat, lng in coords]

        try:
            response = httpx.post(
                self.BASE_URL,
                headers={
                    "Authorization": self.api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "locations": locations,
                    "metrics": ["distance", "duration"],
                    "units": "m",
                },
                timeout=30.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error("ORS API error %d: %s", e.response.status_code, e.response.text[:200])
            raise RuntimeError(
                f"OpenRouteService respondió {e.response.status_code}: "
                f"{e.response.text[:200]}"
            ) from e
        except httpx.HTTPError as e:
            logger.error("ORS connection error: %s", e)
            raise RuntimeError(
                f"Error de conexión con OpenRouteService: {e}"
            ) from e

        data = response.json()

        raw_distances = data.get("distances", [])
        raw_durations = data.get("durations", [])

        for i in range(n):
            for j in range(n):
                dist = raw_distances[i][j] if raw_distances and raw_distances[i][j] is not None else 0
                dur = raw_durations[i][j] if raw_durations and raw_durations[i][j] is not None else 0
                matrix.set(i, j, dist, dur)

        return matrix


# ═══════════════════════════════════════════════════════════════════════════
# CACHED PROVIDER (carga matriz pre-descargada de ORS)
# ═══════════════════════════════════════════════════════════════════════════

class CachedMatrixProvider:
    """
    Provider que carga una matriz pre-descargada desde un archivo JSON.
    Útil para tests deterministas con datos reales de ORS sin llamar la API.
    """
    def __init__(self, matrix_path: str | Path):
        self.matrix_path = Path(matrix_path)
        if not self.matrix_path.exists():
            raise FileNotFoundError(f"Matriz cacheada no encontrada: {self.matrix_path}")

    def compute(self, coords: list[tuple[float, float]]) -> DistanceMatrix:
        with open(self.matrix_path) as f:
            data = json.load(f)

        n = data["n"]
        matrix = DistanceMatrix(n)
        matrix.distances = data["distances"]
        matrix.durations = data["durations"]
        return matrix


# ═══════════════════════════════════════════════════════════════════════════
# FACTORY
# ═══════════════════════════════════════════════════════════════════════════

def get_matrix_provider(provider: str = "synthetic", **kwargs) -> MatrixProvider:
    """Factory para obtener el provider de matriz."""
    if provider == "synthetic":
        return SyntheticMatrixProvider(**kwargs)
    elif provider == "ors":
        return ORSMatrixProvider(**kwargs)
    elif provider == "cached":
        if "matrix_path" not in kwargs:
            raise ValueError("provider='cached' requiere matrix_path kwarg")
        return CachedMatrixProvider(**kwargs)
    else:
        raise ValueError(f"Provider desconocido: {provider}")

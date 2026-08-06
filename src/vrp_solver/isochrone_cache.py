"""
Caché de isocronas por depot.
Computa (o carga de disco) el polígono reachable desde un depot en N segundos.
Soporta provider sintético (círculo euclidiano) y ORS (OpenRouteService).

Una isocrona se computa UNA vez por depot y se persiste en disco.
No se recomputa en cada request — solo cuando cambia la configuración.
"""

from __future__ import annotations

import json
import logging
import math
import os
from pathlib import Path
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# TIPOS
# ═══════════════════════════════════════════════════════════════════════════

class Isochrone:
    """Polígono de cobertura de un depot."""
    def __init__(self, depot_id: str, depot_coords: tuple[float, float], range_seconds: int, polygon: list[tuple[float, float]]):
        self.depot_id = depot_id
        self.depot_coords = depot_coords  # [lat, lng]
        self.range_seconds = range_seconds
        self.polygon = polygon            # lista de (lat, lng)

    def contains(self, point: tuple[float, float]) -> bool:
        """Verifica si un punto [lat, lng] está dentro del polígono (ray-casting)."""
        return _point_in_polygon(point, self.polygon)


# ═══════════════════════════════════════════════════════════════════════════
# GEOMETRÍA — ray-casting sin shapely
# ═══════════════════════════════════════════════════════════════════════════

def _point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    """
    Algoritmo ray-casting estándar.
    point y polygon están en (lat, lng).
    """
    if len(polygon) < 3:
        return False
    lat, lng = point
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        lat_i, lng_i = polygon[i]
        lat_j, lng_j = polygon[j]
        # Verificar si el rayo horizontal cruza la arista (i, j)
        if ((lat_i > lat) != (lat_j > lat)):
            x_intersect = (lng_j - lng_i) * (lat - lat_i) / (lat_j - lat_i) + lng_i
            if lng < x_intersect:
                inside = not inside
        j = i
    return inside


# ═══════════════════════════════════════════════════════════════════════════
# PROTOCOL
# ═══════════════════════════════════════════════════════════════════════════

class IsochroneProvider(Protocol):
    """Protocolo para providers de isocronas."""
    def compute(self, depot_id: str, depot_coords: tuple[float, float], range_seconds: int) -> Isochrone:
        ...


# ═══════════════════════════════════════════════════════════════════════════
# SYNTHETIC PROVIDER (sin ORS — círculo aproximado)
# ═══════════════════════════════════════════════════════════════════════════

class SyntheticIsochroneProvider:
    """
    Isocrona sintética: círculo de radio estimado basado en velocidad urbana.
    Útil para tests y desarrollo sin ORS.
    """
    EARTH_RADIUS_M = 6_371_000
    DEFAULT_SPEED_MS = 11.11  # ~40 km/h urbano

    def __init__(self, speed_ms: float | None = None, n_polygon_points: int = 64):
        self.speed_ms = speed_ms or self.DEFAULT_SPEED_MS
        self.n_points = n_polygon_points

    def compute(self, depot_id: str, depot_coords: tuple[float, float], range_seconds: int) -> Isochrone:
        radius_m = self.speed_ms * range_seconds
        polygon = self._circle_polygon(depot_coords, radius_m, self.n_points)
        return Isochrone(depot_id, depot_coords, range_seconds, polygon)

    def _circle_polygon(self, center: tuple[float, float], radius_m: float, n: int) -> list[tuple[float, float]]:
        """Genera un polígono circular aproximado en (lat, lng)."""
        lat0, lng0 = center
        lat_rad = math.radians(lat0)
        points: list[tuple[float, float]] = []
        for i in range(n):
            angle = 2 * math.pi * i / n
            d_lat = radius_m * math.cos(angle) / self.EARTH_RADIUS_M
            d_lng = radius_m * math.sin(angle) / (self.EARTH_RADIUS_M * math.cos(lat_rad))
            points.append((lat0 + math.degrees(d_lat), lng0 + math.degrees(d_lng)))
        points.append(points[0])  # cerrar polígono
        return points


# ═══════════════════════════════════════════════════════════════════════════
# ORS PROVIDER (OpenRouteService)
# ═══════════════════════════════════════════════════════════════════════════

class ORSIsochroneProvider:
    """
    Isocrona real via OpenRouteService.
    Requiere ORS_API_KEY. Computed once, cached to disk.
    """
    BASE_URL = "https://api.openrouteservice.org/v2/isochrones/driving-car"

    def __init__(self, api_key: str | None = None, cache_dir: str | Path = ".isochrone_cache"):
        self.api_key = api_key or os.getenv("ORS_API_KEY", "")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if not self.api_key:
            raise ValueError("ORS_API_KEY no configurada. Setea la variable de entorno.")

    def compute(self, depot_id: str, depot_coords: tuple[float, float], range_seconds: int) -> Isochrone:
        # 1. Verificar caché en disco
        cache_file = self._cache_path(depot_id, depot_coords, range_seconds)
        if cache_file.exists():
            logger.info("Isocrona cacheada cargada: %s", cache_file.name)
            return self._load_from_cache(cache_file, depot_id, depot_coords, range_seconds)

        # 2. Llamar ORS
        logger.info("Computando isocrona ORS para depot %s (%ds)", depot_id, range_seconds)
        polygon = self._call_ors(depot_coords, range_seconds)

        # 3. Guardar en caché
        isochrone = Isochrone(depot_id, depot_coords, range_seconds, polygon)
        self._save_to_cache(cache_file, isochrone)
        return isochrone

    def _cache_path(self, depot_id: str, coords: tuple[float, float], range_s: int) -> Path:
        lat, lng = coords
        safe_id = depot_id.replace("/", "_")
        return self.cache_dir / f"isochrone_{safe_id}_{lat:.4f}_{lng:.4f}_{range_s}s.json"

    def _load_from_cache(self, path: Path, depot_id: str, coords: tuple[float, float], range_s: int) -> Isochrone:
        with open(path) as f:
            data = json.load(f)
        polygon = [(p[0], p[1]) for p in data["polygon"]]
        return Isochrone(depot_id, coords, range_s, polygon)

    def _save_to_cache(self, path: Path, isochrone: Isochrone) -> None:
        data = {
            "depot_id": isochrone.depot_id,
            "depot_coords": list(isochrone.depot_coords),
            "range_seconds": isochrone.range_seconds,
            "polygon": [[p[0], p[1]] for p in isochrone.polygon],
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        logger.info("Isocrona guardada en caché: %s", path.name)

    def _call_ors(self, coords: tuple[float, float], range_seconds: int) -> list[tuple[float, float]]:
        lat, lng = coords
        try:
            response = httpx.post(
                self.BASE_URL,
                headers={
                    "Authorization": self.api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "locations": [[lng, lat]],
                    "range": [range_seconds],
                    "range_type": "time",
                    "attributes": ["total_pop"],
                },
                timeout=30.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error("ORS isochrone error %d: %s", e.response.status_code, e.response.text[:200])
            raise RuntimeError(
                f"OpenRouteService isochrones respondió {e.response.status_code}: "
                f"{e.response.text[:200]}"
            ) from e
        except httpx.HTTPError as e:
            logger.error("ORS isochrone connection error: %s", e)
            raise RuntimeError(
                f"Error de conexión con OpenRouteService (isochrones): {e}"
            ) from e

        data = response.json()
        # GeoJSON FeatureCollection → primer feature → polygon coordinates
        features = data.get("features", [])
        if not features:
            raise RuntimeError("ORS isochrones: respuesta sin features")

        geometry = features[0].get("geometry", {})
        coords_raw = geometry.get("coordinates", [])

        # Polygon: coords_raw[0] es el anillo exterior
        if geometry.get("type") == "Polygon":
            ring = coords_raw[0] if coords_raw else []
        elif geometry.get("type") == "MultiPolygon":
            ring = coords_raw[0][0] if coords_raw and coords_raw[0] else []
        else:
            raise RuntimeError(f"ORS isochrones: tipo de geometría inesperado: {geometry.get('type')}")

        # ORS devuelve [lng, lat] → convertir a (lat, lng)
        polygon = [(p[1], p[0]) for p in ring]
        return polygon


# ═══════════════════════════════════════════════════════════════════════════
# FACTORY
# ═══════════════════════════════════════════════════════════════════════════

def get_isochrone_provider(provider: str = "synthetic", **kwargs) -> IsochroneProvider:
    """Factory para obtener el provider de isocronas."""
    if provider == "synthetic":
        return SyntheticIsochroneProvider(**kwargs)
    elif provider == "ors":
        return ORSIsochroneProvider(**kwargs)
    else:
        raise ValueError(f"Provider de isocrona desconocido: {provider}")

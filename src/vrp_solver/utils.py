"""Utilidades compartidas del solver VRP."""

import math

EARTH_RADIUS_M = 6_371_000


def seconds_to_hms(total_seconds: int) -> str:
    """Convierte segundos desde medianoche a formato HH:MM:SS."""
    h = (total_seconds // 3600) % 24
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distancia euclidiana en metros entre dos puntos [lat, lng]."""
    lat1, lng1 = math.radians(a[0]), math.radians(a[1])
    lat2, lng2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))

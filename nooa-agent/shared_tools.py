"""
Tools compartidos entre agentes autónomos.

Evita duplicación de search_sentinel y generate_deformation_map
en emergency_autonomous, insurance_autonomous y mining_autonomous.

Filosofía NOOA: funciones puras que reciben estado y devuelven resultado.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from deformation_map import DeformationMap
from sentinel_client import SentinelClient, bbox_to_wkt

logger = logging.getLogger(__name__)


def tool_search_sentinel(lat: float, lng: float, days_before: int = 7) -> dict[str, Any]:
    """
    Busca imágenes Sentinel-2 del área afectada en CDSE.

    Args:
        lat: latitud del epicentro
        lng: longitud del epicentro
        days_before: días hacia atrás para buscar

    Returns:
        dict con products y count, o error si no hay credenciales
    """
    client = SentinelClient()
    if not client._check_credentials():
        return {"error": "Sin credenciales CDSE"}

    client.authenticate()
    aoi = bbox_to_wkt(lng - 0.5, lat - 0.5, lng + 0.5, lat + 0.5)

    end = datetime.now(timezone.utc).strftime('%Y-%m-%dT23:59:59.000Z')
    start = (datetime.now(timezone.utc) - timedelta(days=days_before)).strftime('%Y-%m-%dT00:00:00.000Z')

    s2 = client.search_products(
        collection="SENTINEL-2", product_type="S2MSI1C",
        aoi_wkt=aoi, start_date=start, end_date=end,
        max_cloud_cover=50, top=3,
    )

    products = [{"name": p.name, "date": p.sensing_date[:10]} for p in s2.products]
    return {"products": products, "count": len(products)}


def tool_generate_deformation_map(
    lat: float,
    lng: float,
    magnitude: float,
    zones: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Genera mapa de deformación InSAR basado en magnitud y ubicación.

    Args:
        lat: latitud del epicentro
        lng: longitud del epicentro
        magnitude: magnitud del sismo o severidad del evento
        zones: lista de zonas con name, lat, lng

    Returns:
        dict con zones (detalle por zona) y max_deformation_mm
    """
    def_map = DeformationMap()
    def_map.generate(epicenter=(lat, lng), magnitude=magnitude, zone_centers=zones)

    zone_results = [
        {
            "name": z.name,
            "max_mm": z.max_deformation_mm,
            "severity": z.severity,
            "building_risk": z.building_risk,
        }
        for z in def_map.prioritize_zones()
    ]

    return {
        "zones": zone_results,
        "max_deformation_mm": max(z.max_deformation_mm for z in def_map.zones) if def_map.zones else 0,
        "_deformation_map": def_map,
    }

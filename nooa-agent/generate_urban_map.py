"""
TerraSAT / UrbanSAT — Generador de mapa HTML para el boletín urbano

Genera un mapa HTML standalone con Leaflet mostrando:
- Marcadores por zona urbana con color según tipo de alerta
- Popups con detalle del cambio detectado
- Leyenda con conteos

Salida: scripts/urban-map.html

Ejecutar: python nooa-agent/generate_urban_map.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from demo_urban_sat import (
    generate_urban_zones,
    simulate_urban_zones,
    ALERT_TYPE_LABEL,
)


STATUS_COLOR = {
    "critico": "#dc2626",
    "alerta": "#ea580c",
    "vigilancia": "#ca8a04",
    "normal": "#16a34a",
}

STATUS_LABEL = {
    "critico": "Crítico",
    "alerta": "Alerta",
    "vigilancia": "Vigilancia",
    "normal": "Normal",
}

ALERT_ICON = {
    "construccion": "🏗️",
    "calor": "🌡️",
    "verde": "🌳",
}


def _zone_bounds(lat: float, lng: float, area_ha: float) -> tuple[float, float, float, float]:
    area_km2 = area_ha / 100.0
    side_km = math.sqrt(area_km2)
    lat_delta = side_km / 111.0 / 2
    lng_delta = side_km / (111.0 * math.cos(math.radians(lat))) / 2
    lat_delta = max(lat_delta, 0.05)
    lng_delta = max(lng_delta, 0.05)
    return (lat - lat_delta, lng - lng_delta, lat + lat_delta, lng + lng_delta)


def generate_urban_map_html(zones, today_str: str) -> str:
    zones_js = []
    for z in zones:
        color = STATUS_COLOR.get(z.status, "#666")
        south, west, north, east = _zone_bounds(z.lat, z.lng, z.area_ha)
        fill_opacity = 0.15 if z.status == "normal" else 0.35
        stroke_weight = 1.5 if z.status == "normal" else 2.5

        icon = ALERT_ICON.get(z.alert_type, "✅")
        label = ALERT_TYPE_LABEL.get(z.alert_type, "Sin cambios")

        popup = (
            f"<b>{icon} {z.name}, {z.city}</b><br>"
            f"País: {z.country}<br>"
            f"Tipo: {label}<br>"
            f"Estado: {STATUS_LABEL.get(z.status, z.status)}<br>"
            f"Área sector: {z.area_ha:,} ha<br>"
        )
        if z.affected_area_ha > 0:
            popup += f"Área afectada: {z.affected_area_ha:,} ha<br>"
        if z.alert_cause:
            popup += f"Causa: {z.alert_cause}<br>"
        if z.confidence > 0:
            popup += f"Confianza: {z.confidence:.0%}"

        popup_escaped = popup.replace("\n", " ").replace('"', '\\"')
        zones_js.append(
            f'    L.rectangle([[{south:.4f}, {west:.4f}], [{north:.4f}, {east:.4f}]], {{'
            f'fillColor: "{color}", '
            f'color: "{color}", '
            f'weight: {stroke_weight}, '
            f'fillOpacity: {fill_opacity}, '
            f'opacity: 0.8'
            f'}}).addTo(map).bindPopup("{popup_escaped}");'
        )

    # Leyenda por tipo de alerta
    legend_items = []
    for status, color in STATUS_COLOR.items():
        count = sum(1 for z in zones if z.status == status)
        if count > 0:
            legend_items.append(
                f'<div style="display:flex;align-items:center;gap:8px;margin:4px 0;">'
                f'<div style="width:16px;height:12px;border-radius:2px;background:{color};border:1px solid {color};"></div>'
                f'<span>{STATUS_LABEL[status]} ({count})</span>'
                f'</div>'
            )

    # Conteo por tipo
    type_counts = {}
    for z in zones:
        if z.alert_type and z.status != "normal":
            type_counts[z.alert_type] = type_counts.get(z.alert_type, 0) + 1

    type_lines = []
    for alert_type, count in type_counts.items():
        icon = ALERT_ICON.get(alert_type, "")
        label = ALERT_TYPE_LABEL.get(alert_type, alert_type)
        type_lines.append(f"{icon} {label}: {count} zonas")

    total_ha = sum(z.area_ha for z in zones)
    affected_ha = sum(z.affected_area_ha for z in zones if z.status in ("critico", "alerta"))
    cities = sorted(set(z.city for z in zones))

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TerraSAT / UrbanSAT — Mapa Urbano — {today_str}</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #f8fafc; }}
        #map {{ width: 100%; height: 100vh; }}
        .leaflet-popup-content {{ font-size: 13px; line-height: 1.5; }}
        #legend {{
            position: absolute;
            top: 20px;
            right: 20px;
            z-index: 1000;
            background: rgba(255, 255, 255, 0.95);
            color: #1e293b;
            padding: 16px 20px;
            border-radius: 10px;
            font-size: 14px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.15);
            border: 1px solid rgba(0,0,0,0.1);
        }}
        #legend h3 {{
            font-size: 16px;
            margin-bottom: 8px;
            color: #0ea5e9;
        }}
        #legend .subtitle {{
            font-size: 12px;
            color: #64748b;
            margin-bottom: 10px;
        }}
        #legend .types {{
            margin-top: 8px;
            padding-top: 8px;
            border-top: 1px solid rgba(0,0,0,0.08);
            font-size: 13px;
        }}
        #legend .stats {{
            margin-top: 10px;
            padding-top: 10px;
            border-top: 1px solid rgba(0,0,0,0.1);
            font-size: 12px;
            color: #475569;
        }}
    </style>
</head>
<body>
    <div id="map"></div>
    <div id="legend">
        <h3>TerraSAT / UrbanSAT</h3>
        <div class="subtitle">Monitoreo Urbano Satelital — {today_str}</div>
        {''.join(legend_items)}
        <div class="types">
            {'<br>'.join(type_lines)}
        </div>
        <div class="stats">
            <b>{len(zones)}</b> zonas · <b>{len(cities)}</b> ciudades<br>
            <b>{total_ha:,}</b> ha monitoreadas<br>
            <b>{affected_ha:,}</b> ha con cambios
        </div>
    </div>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        var map = L.map('map', {{
            zoomControl: true,
            attributionControl: false
        }}).setView([-20, -60], 3);

        L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
            maxZoom: 18,
            subdomains: 'abcd'
        }}).addTo(map);

{chr(10).join(zones_js)}
    </script>
</body>
</html>"""


def main():
    from datetime import date

    today = date(2026, 8, 13)
    today_str = today.strftime("%d/%m/%Y")

    zones = generate_urban_zones()
    simulate_urban_zones(zones, seed=2026)

    html = generate_urban_map_html(zones, today_str)

    output_dir = Path("scripts")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "urban-map.html"
    output_path.write_text(html, encoding="utf-8")

    print(f"Mapa urbano generado: {output_path}")
    print(f"  Abrir en navegador, capturar pantalla para publicación.")


if __name__ == "__main__":
    main()

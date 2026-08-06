"""
Visualiza los resultados del benchmark OR-Tools vs ORS en un mapa HTML interactivo.
Genera un mapa por escenario con las rutas de ambos solvers en colores distintos.

Uso: uv run python scripts/visualize_routes.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import folium
from folium.plugins import MarkerCluster

FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures"
RESULTS_PATH = FIXTURES_DIR / "benchmark_results.json"
COORDS_PATH = FIXTURES_DIR / "coords_madrid_15.json"
OUTPUT_DIR = FIXTURES_DIR / "maps"

# Colores por vehículo OR-Tools (sólido)
OT_COLORS = ["#e6194B", "#3cb44b", "#4363d8", "#f58231", "#911eb4"]
# Colores por vehículo ORS (punteado, tonos claros)
ORS_COLORS = ["#ff9999", "#99ff99", "#9999ff", "#ffcc99", "#cc99ff"]


def load_coords() -> list[tuple[float, float]]:
    with open(COORDS_PATH) as f:
        return [tuple(c) for c in json.load(f)["coords"]]


def _find_coord_idx(coord: tuple, coords_list: list) -> int | None:
    lat, lng = coord
    for i, c in enumerate(coords_list):
        if abs(c[0] - lat) < 0.001 and abs(c[1] - lng) < 0.001:
            return i
    return None


def visualize_scenario(scenario_name: str, ors_routes: list, ortools_routes: list,
                       coords: list[tuple[float, float]], output_path: Path) -> None:
    """Genera un mapa HTML con las rutas de ambos solvers."""
    depot = coords[0]
    m = folium.Map(location=depot, zoom_start=12, tiles="OpenStreetMap")

    # ── Marcadores de ubicaciones ──
    marker_cluster = MarkerCluster(name="Ubicaciones").add_to(m)

    folium.Marker(
        location=depot,
        popup=folium.Popup("<b>Depósito</b><br>Inicio y fin de rutas", max_width=200),
        icon=folium.Icon(color="black", icon="warehouse", prefix="fa"),
    ).add_to(m)

    for i in range(1, len(coords)):
        folium.Marker(
            location=coords[i],
            popup=folium.Popup(f"<b>Entrega {i}</b>", max_width=150),
            icon=folium.Icon(color="blue", icon="package", prefix="fa"),
        ).add_to(marker_cluster)

    # ── Rutas OR-Tools (líneas sólidas) ──
    ot_group = folium.FeatureGroup(name="OR-Tools", show=True)

    for v_idx, route in enumerate(ortools_routes):
        color = OT_COLORS[v_idx % len(OT_COLORS)]
        veh_id = route.get("vehicle_id", f"veh_{v_idx}")
        route_coords = []

        for step in route.get("steps", []):
            loc_id = step.get("location_id", "")
            step_type = step.get("type", "")

            if step_type == "break":
                if route_coords:
                    route_coords.append(route_coords[-1])
                continue

            if loc_id == "depot":
                route_coords.append(coords[0])
            elif loc_id.startswith("del_"):
                try:
                    idx = int(loc_id.split("_")[1])
                    route_coords.append(coords[idx])
                except (ValueError, IndexError):
                    continue

        if len(route_coords) >= 2:
            folium.PolyLine(
                route_coords, color=color, weight=4, opacity=0.8,
                popup=f"OR-Tools {veh_id}: {route.get('total_distance', 0):.0f}m, "
                      f"travel={route.get('travel_time', 0)}s",
            ).add_to(ot_group)

            for order, (lat, lng) in enumerate(route_coords):
                if (lat, lng) == depot and order > 0:
                    continue
                folium.CircleMarker(
                    location=(lat, lng), radius=8, color=color,
                    fill=True, fillColor=color, fillOpacity=0.7,
                    popup=f"{veh_id} - Stop #{order+1}",
                ).add_to(ot_group)

    ot_group.add_to(m)

    # ── Rutas ORS/VROOM (líneas punteadas) ──
    ors_group = folium.FeatureGroup(name="ORS/VROOM", show=True)

    for v_idx, route in enumerate(ors_routes):
        color = ORS_COLORS[v_idx % len(ORS_COLORS)]
        veh_id = f"ORS veh {route.get('vehicle', v_idx)}"
        route_coords = []

        for step in route.get("steps", []):
            loc = step.get("location")
            step_type = step.get("type", "")

            if step_type == "break":
                if route_coords:
                    route_coords.append(route_coords[-1])
                continue

            if loc and len(loc) >= 2:
                route_coords.append((loc[1], loc[0]))

        if len(route_coords) >= 2:
            folium.PolyLine(
                route_coords, color=color, weight=3, opacity=0.6,
                dash_array="10, 5",
                popup=f"{veh_id}: dur={route.get('duration', 0)}s",
            ).add_to(ors_group)

    ors_group.add_to(m)

    # ── Layer control ──
    folium.LayerControl(collapsed=False).add_to(m)

    # ── Título ──
    title_html = f"""
    <div style="position: fixed; top: 10px; left: 10px; z-index: 1000;
                background: white; padding: 10px; border-radius: 5px;
                box-shadow: 0 2px 5px rgba(0,0,0,0.3);">
        <h3 style="margin: 0;">{scenario_name}</h3>
        <p style="margin: 5px 0;">
            <span style="color: #e6194B;">━━</span> OR-Tools (sólida)
            &nbsp;&nbsp;
            <span style="color: #ff9999;">┄┄</span> ORS/VROOM (punteada)
        </p>
    </div>
    """
    m.get_root().html.add_child(folium.Element(title_html))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(output_path))
    print(f"  Mapa guardado: {output_path}")


def main():
    coords = load_coords()

    with open(RESULTS_PATH) as f:
        results = json.load(f)

    print(f"\n{'='*60}")
    print(f"VISUALIZACIÓN DE RUTAS: OR-Tools vs ORS/VROOM")
    print(f"{'='*60}\n")

    if isinstance(results, list):
        for i, r in enumerate(results):
            scenario_name = r.get("scenario", f"Escenario {i+1}")
            ors_routes = r.get("ors_routes", [])
            ortools_routes = r.get("ortools_routes", [])
            safe_name = scenario_name.replace(" ", "_").replace(":", "").replace("(", "").replace(")", "")
            output_path = OUTPUT_DIR / f"{safe_name}.html"
            print(f"\n  {scenario_name}:")
            visualize_scenario(scenario_name, ors_routes, ortools_routes, coords, output_path)
    elif isinstance(results, dict):
        scenario_name = "Benchmark"
        ors_routes = results.get("ors_vroom", {}).get("routes", [])
        ortools_routes = results.get("ortools", {}).get("routes", [])
        output_path = OUTPUT_DIR / "benchmark_single.html"
        visualize_scenario(scenario_name, ors_routes, ortools_routes, coords, output_path)

    print(f"\n  Abre los archivos HTML en tu navegador para ver los mapas.")
    print(f"  Carpeta: {OUTPUT_DIR}\n")


if __name__ == "__main__":
    main()

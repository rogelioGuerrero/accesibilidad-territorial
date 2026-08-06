"""
Test end-to-end del pipeline con ORS en vivo.
Usa coords reales de Bogotá, pocos nodos (6) para no saturar ORS.
Guarda la matriz en tests/fixtures/ para uso futuro.

Ejecutar: python scripts/test_ors_pipeline.py
"""

import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# Cargar .env
load_dotenv()

# PYTHONPATH = src
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from vrp_solver.matrix import ORSMatrixProvider, CachedMatrixProvider, DistanceMatrix
from vrp_solver.isochrone_cache import ORSIsochroneProvider
from vrp_solver.models import (
    Location,
    LocationType,
    OptimizeRequest,
    SolverConfig,
    Vehicle,
    TimeWindow,
)
from vrp_solver.solver import VRPSolver
from vrp_solver.validator import validate_request

# 6 puntos reales en Bogotá (1 depot + 5 entregas)
# Mantengo pocos nodos para no saturar ORS free tier
COORDS_BOGOTA = [
    (4.65, -74.10),   # depot — Chapinero
    (4.68, -74.05),   # entrega 1 — Norte
    (4.62, -74.15),   # entrega 2 — Sur
    (4.70, -74.12),   # entrega 3 — Noroeste
    (4.60, -74.08),   # entrega 4 — Suroriente
    (4.66, -74.14),   # entrega 5 — Centro
]

FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures"
MATRIX_PATH = FIXTURES_DIR / "matrix_bogota_6.json"
COORDS_PATH = FIXTURES_DIR / "coords_bogota_6.json"


def step_1_validate_payload():
    """Paso 1: Validar que el payload está bien estructurado."""
    print("\n" + "=" * 60)
    print("PASO 1: Validación del payload")
    print("=" * 60)

    locations = [
        Location(id="depot", name="Depósito Chapinero", coords=COORDS_BOGOTA[0], type=LocationType.depot)
    ]
    for i in range(1, len(COORDS_BOGOTA)):
        locations.append(Location(
            id=f"del_{i}",
            name=f"Entrega Bogotá {i}",
            coords=COORDS_BOGOTA[i],
            type=LocationType.delivery,
            weight_demand=15.0,
            service_time=300,
        ))

    vehicles = [
        Vehicle(
            id="veh_1", name="Camión 1",
            start_location_id="depot", end_location_id="depot",
            weight_capacity=100.0,
            start_time=28800, end_time=64800,
            fixed_cost=50.0,
            cost_per_km=2.5,
            cost_per_hour=20.0,
            cost_per_stop=3.0,
        ),
    ]

    config = SolverConfig(
        time_limit_seconds=10,
        optimize_by="cost",
    )

    request = OptimizeRequest(locations=locations, vehicles=vehicles, config=config)

    result = validate_request(request)
    if not result.is_valid:
        print("❌ Validación falló:")
        for e in result.errors:
            print(f"  - {e.code}: {e.message}")
        return None

    print("✅ Payload válido")
    print(f"   {len(locations)} locations (1 depot + {len(locations)-1} entregas)")
    print(f"   {len(vehicles)} vehículo(s)")
    print(f"   Objetivo: {config.optimize_by}")
    print(f"   Costos: fixed=${vehicles[0].fixed_cost}, km=${vehicles[0].cost_per_km}, hora=${vehicles[0].cost_per_hour}, parada=${vehicles[0].cost_per_stop}")
    return request


def step_2_ors_matrix():
    """Paso 2: Obtener matriz real de ORS y guardarla."""
    print("\n" + "=" * 60)
    print("PASO 2: Matriz ORS en vivo (6 puntos)")
    print("=" * 60)

    api_key = os.getenv("ORS_API_KEY")
    if not api_key:
        print("❌ ORS_API_KEY no encontrada en .env")
        return None

    print(f"   API key: {api_key[:8]}...{api_key[-4:]}")
    print("   Llamando a ORS...")

    provider = ORSMatrixProvider(api_key=api_key)
    start = time.time()
    matrix = provider.compute(COORDS_BOGOTA)
    elapsed = time.time() - start

    print(f"✅ Matriz obtenida en {elapsed:.1f}s")

    # Verificar que los datos son reales
    print("\n   Verificación de datos reales:")
    for i in range(min(3, len(COORDS_BOGOTA))):
        for j in range(min(3, len(COORDS_BOGOTA))):
            if i != j:
                d = matrix.distances[i][j]
                t = matrix.durations[i][j]
                print(f"   {i}→{j}: {d}m ({d/1000:.2f}km), {t}s ({t//60}min {t%60}s)")

    # Verificar que no son Haversine (distancias reales son diferentes)
    from vrp_solver.utils import haversine
    haversine_dist = haversine(COORDS_BOGOTA[0], COORDS_BOGOTA[1])
    ors_dist = matrix.distances[0][1]
    ratio = ors_dist / haversine_dist if haversine_dist > 0 else 0
    print(f"\n   Comparación Haversine vs ORS (0→1):")
    print(f"   Haversine: {haversine_dist:.0f}m (línea recta)")
    print(f"   ORS:       {ors_dist}m (red vial real)")
    print(f"   Ratio:     {ratio:.2f}x (normalmente 1.2-1.5x)")

    # Guardar matriz
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    matrix_data = {
        "description": "Matriz ORS real (driving-car) para 6 puntos en Bogotá",
        "n": matrix.n,
        "distances": matrix.distances,
        "durations": matrix.durations,
    }
    with open(MATRIX_PATH, "w") as f:
        json.dump(matrix_data, f, indent=2)
    print(f"\n   💾 Matriz guardada: {MATRIX_PATH}")

    # Guardar coords
    coords_data = {
        "description": "6 puntos reales en Bogotá (1 depósito + 5 entregas)",
        "coords": COORDS_BOGOTA,
        "coord_format": "[lat, lng]",
    }
    with open(COORDS_PATH, "w") as f:
        json.dump(coords_data, f, indent=2)
    print(f"   💾 Coords guardadas: {COORDS_PATH}")

    return matrix


def step_3_ors_isochrone():
    """Paso 3: Obtener isocrona real de ORS para el depot."""
    print("\n" + "=" * 60)
    print("PASO 3: Isocrona ORS en vivo (depot Bogotá, 30 min)")
    print("=" * 60)

    api_key = os.getenv("ORS_API_KEY")
    provider = ORSIsochroneProvider(api_key=api_key, cache_dir=".isochrone_cache")

    print("   Llamando a ORS isochrones...")
    start = time.time()
    isochrone = provider.compute("depot_bogota", COORDS_BOGOTA[0], range_seconds=1800)
    elapsed = time.time() - start

    print(f"✅ Isocrona obtenida en {elapsed:.1f}s")
    print(f"   Depot: {COORDS_BOGOTA[0]}")
    print(f"   Range: 1800s (30 min)")
    print(f"   Polígono: {len(isochrone.polygon)} puntos")

    # Verificar que las entregas están dentro
    for i in range(1, len(COORDS_BOGOTA)):
        inside = isochrone.contains(COORDS_BOGOTA[i])
        print(f"   Entrega {i} {COORDS_BOGOTA[i]}: {'✅ dentro' if inside else '❌ fuera'}")


def step_4_solve(request):
    """Paso 4: Resolver con la matriz ORS cacheada."""
    print("\n" + "=" * 60)
    print("PASO 4: Resolver VRP con matriz ORS real")
    print("=" * 60)

    solver = VRPSolver.from_request(
        request,
        matrix_provider="cached",
        matrix_path=str(MATRIX_PATH),
    )

    start = time.time()
    result = solver.solve()
    elapsed = time.time() - start

    if result.errors:
        print("❌ Solver error:")
        for e in result.errors:
            print(f"  - {e.code}: {e.message}")
        return

    print(f"✅ Solver completado en {elapsed:.1f}s")
    print(f"   Vehículos usados: {result.statistics.vehicles_used}/{result.statistics.vehicles_available}")
    print(f"   Nodos asignados: {result.statistics.nodes_assigned}")
    print(f"   Nodos no asignados: {result.statistics.nodes_unassigned}")
    print(f"   Distancia total: {result.statistics.total_distance}m ({result.statistics.total_distance/1000:.2f}km)")
    print(f"   Duración total: {result.statistics.total_duration}s ({result.statistics.total_duration//3600}h {(result.statistics.total_duration%3600)//60}min)")

    if result.statistics.total_cost:
        print(f"   💰 Costo total: ${result.statistics.total_cost:.2f}")

    for route in result.routes:
        print(f"\n   🚛 {route.vehicle_name or route.vehicle_id}:")
        print(f"      Paradas: {route.total_stops}")
        print(f"      Distancia: {route.total_distance}m ({route.total_distance/1000:.2f}km)")
        print(f"      Duración: {route.total_duration}s ({route.total_duration//60}min)")
        if route.cost:
            print(f"      Costo: fixed=${route.cost.fixed}, dist=${route.cost.distance}, time=${route.cost.time}, stops=${route.cost.stops}, total=${route.cost.total}")
        print(f"      Ruta:")
        for i, stop in enumerate(route.stops):
            print(f"        {i+1}. {stop.name or stop.location_id} ({stop.type}) — arrive={stop.arrival or 'N/A'}, depart={stop.departure or 'N/A'}")

    if result.unassigned:
        print(f"\n   ⚠️  No asignados:")
        for n in result.unassigned:
            print(f"      - {n.name or n.id}: {n.reason or 'sin razón'}")

    if result.warnings:
        print(f"\n   ⚠️  Warnings:")
        for w in result.warnings:
            print(f"      - {w}")


def main():
    print("=" * 60)
    print("TEST PIPELINE ORS EN VIVO — Bogotá, 6 nodos")
    print("=" * 60)

    # Paso 1: Validar payload
    request = step_1_validate_payload()
    if request is None:
        return

    # Paso 2: Obtener matriz ORS
    matrix = step_2_ors_matrix()
    if matrix is None:
        return

    # Paso 3: Isocrona ORS
    step_3_ors_isochrone()

    # Paso 4: Resolver
    step_4_solve(request)

    print("\n" + "=" * 60)
    print("PIPELINE COMPLETADO — Sin humo, datos reales de ORS")
    print("=" * 60)


if __name__ == "__main__":
    main()

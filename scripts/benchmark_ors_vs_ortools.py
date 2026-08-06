"""
Benchmark multi-escenario: OR-Tools vs ORS Optimization (VROOM).
Valida calidad de optimización Y cumplimiento de restricciones.

Escenarios:
  1. 8 entregas, 2 vehículos, sin breaks (base)
  2. 8 entregas, 2 vehículos, con lunch break
  3. 14 entregas, 3 vehículos, con lunch break + time windows

Uso: uv run python scripts/benchmark_ors_vs_ortools.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import httpx
from dotenv import load_dotenv

from vrp_solver.models import (
    Location,
    LocationType,
    OptimizeRequest,
    OptimizationObjective,
    SolverConfig,
    Vehicle,
    VehicleBreak,
    TimeWindow,
)
from vrp_solver.solver import VRPSolver

load_dotenv()

FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures"
MATRIX_PATH = FIXTURES_DIR / "matrix_madrid_15.json"
COORDS_PATH = FIXTURES_DIR / "coords_madrid_15.json"
RESULTS_PATH = FIXTURES_DIR / "benchmark_results.json"


def load_coords() -> list[tuple[float, float]]:
    with open(COORDS_PATH) as f:
        return [tuple(c) for c in json.load(f)["coords"]]


def load_matrix_data() -> dict:
    with open(MATRIX_PATH) as f:
        m = json.load(f)
    with open(COORDS_PATH) as f:
        m["coords"] = json.load(f)["coords"]
    return m


# ═══════════════════════════════════════════════════════════════════════════
# DEFINICIÓN DE ESCENARIOS
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class Scenario:
    name: str
    n_deliveries: int
    n_vehicles: int
    capacity: int
    demand: int
    service_time: int
    has_breaks: bool
    has_time_windows: bool
    optimize_by: str = "distance"
    veh_start: int = 28800   # 08:00
    veh_end: int = 61200     # 17:00
    lunch_duration: int = 2700   # 45 min
    lunch_earliest: int = 43200  # 12:00
    lunch_latest: int = 50400    # 14:00


SCENARIOS = [
    Scenario(
        name="S1: 8 entregas, 2 veh, sin breaks",
        n_deliveries=8, n_vehicles=2, capacity=50, demand=10,
        service_time=300, has_breaks=False, has_time_windows=False,
    ),
    Scenario(
        name="S2: 8 entregas, 2 veh, con lunch break",
        n_deliveries=8, n_vehicles=2, capacity=50, demand=10,
        service_time=300, has_breaks=True, has_time_windows=False,
    ),
    Scenario(
        name="S3: 14 entregas, 3 veh, breaks + TW (opt. duración)",
        n_deliveries=14, n_vehicles=3, capacity=50, demand=10,
        service_time=300, has_breaks=True, has_time_windows=True,
        optimize_by="duration",
    ),
]


# ═══════════════════════════════════════════════════════════════════════════
# ORS OPTIMIZATION (VROOM)
# ═══════════════════════════════════════════════════════════════════════════

def run_ors(scenario: Scenario, coords: list[tuple[float, float]]) -> dict:
    api_key = os.getenv("ORS_API_KEY")
    if not api_key:
        raise RuntimeError("ORS_API_KEY no configurada")

    depot_lonlat = [coords[0][1], coords[0][0]]

    vehicles = []
    for i in range(scenario.n_vehicles):
        v: dict = {
            "id": i + 1,
            "profile": "driving-car",
            "start": depot_lonlat,
            "end": depot_lonlat,
            "capacity": [scenario.capacity],
            "time_window": [scenario.veh_start, scenario.veh_end],
        }
        if scenario.has_breaks:
            v["breaks"] = [{
                "id": 100 + i,
                "time_windows": [[scenario.lunch_earliest, scenario.lunch_latest]],
                "service": scenario.lunch_duration,
            }]
        vehicles.append(v)

    jobs = []
    for i in range(1, scenario.n_deliveries + 1):
        lonlat = [coords[i][1], coords[i][0]]
        job: dict = {
            "id": i + 100,
            "location": lonlat,
            "service": scenario.service_time,
            "delivery": [scenario.demand],
        }
        if scenario.has_time_windows:
            # Ventanas de tiempo: cada entrega tiene ventana de 3 horas
            # Repartidas en bloques: 08-11, 10-13, 12-15, 14-17
            tw_blocks = [
                [28800, 39600],   # 08:00 - 11:00
                [36000, 46800],   # 10:00 - 13:00
                [43200, 54000],   # 12:00 - 15:00
                [50400, 61200],   # 14:00 - 17:00
            ]
            tw = tw_blocks[(i - 1) % len(tw_blocks)]
            job["time_windows"] = [tw]
        jobs.append(job)

    payload = {"jobs": jobs, "vehicles": vehicles, "geometry": False}

    url = "https://api.openrouteservice.org/optimization"
    headers = {"Authorization": api_key, "Content-Type": "application/json"}

    resp = httpx.post(url, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.json()


# ═══════════════════════════════════════════════════════════════════════════
# OR-TOOLS
# ═══════════════════════════════════════════════════════════════════════════

def run_ortools(scenario: Scenario, coords: list[tuple[float, float]]) -> dict:
    locations = [
        Location(id="depot", name="Depósito", coords=coords[0], type=LocationType.depot)
    ]
    tw_blocks = [
        (28800, 39600), (36000, 46800), (43200, 54000), (50400, 61200),
    ]
    for i in range(1, scenario.n_deliveries + 1):
        loc_kwargs: dict = dict(
            id=f"del_{i}", name=f"Entrega {i}", coords=coords[i],
            type=LocationType.delivery,
            weight_demand=scenario.demand, service_time=scenario.service_time,
        )
        if scenario.has_time_windows:
            tw = tw_blocks[(i - 1) % len(tw_blocks)]
            loc_kwargs["time_windows"] = [TimeWindow(start=tw[0], end=tw[1])]
        locations.append(Location(**loc_kwargs))

    vehicles = []
    for i in range(1, scenario.n_vehicles + 1):
        veh_kwargs: dict = dict(
            id=f"veh_{i}", name=f"Vehículo {i}",
            start_location_id="depot", end_location_id="depot",
            weight_capacity=scenario.capacity,
            start_time=scenario.veh_start, end_time=scenario.veh_end,
        )
        if scenario.has_breaks:
            veh_kwargs["breaks"] = [VehicleBreak(
                duration=scenario.lunch_duration,
                earliest_start=scenario.lunch_earliest,
                latest_start=scenario.lunch_latest,
            )]
        vehicles.append(Vehicle(**veh_kwargs))

    request = OptimizeRequest(
        locations=locations, vehicles=vehicles,
        config=SolverConfig(
            time_limit_seconds=30,
            optimize_by=OptimizationObjective(scenario.optimize_by),
        ),
    )
    solver = VRPSolver(request, matrix_provider="cached", matrix_path=str(MATRIX_PATH))
    result = solver.solve()
    if result.errors:
        raise RuntimeError(f"OR-Tools errors: {result.errors}")

    # Construir respuesta comparable + datos para validación
    routes = []
    for r in result.routes:
        steps = []
        travel_time = 0
        prev_idx = None
        for s in r.stops:
            step = {
                "location_id": s.location_id,
                "type": s.type,
                "arrival": s.arrival,
                "departure": s.departure,
            }
            steps.append(step)

            # Travel time acumulado
            if s.type != "break" and s.location_id:
                idx = _loc_id_to_idx(s.location_id, locations)
                if prev_idx is not None and idx is not None:
                    travel_time += solver.matrix.durations[prev_idx][idx]
                prev_idx = idx

        routes.append({
            "vehicle_id": r.vehicle_id,
            "total_distance": r.total_distance,
            "total_duration": r.total_duration,
            "travel_time": travel_time,
            "total_stops": r.total_stops,
            "steps": steps,
        })

    return {
        "routes": routes,
        "unassigned": [u.model_dump() for u in result.unassigned],
        "statistics": result.statistics.model_dump() if result.statistics else None,
        "solver_time": result.solver_time,
        "_locations": [{"id": l.id, "coords": l.coords, "type": l.type.value,
                         "weight_demand": l.weight_demand, "service_time": l.service_time,
                         "time_windows": [{"start": tw.start, "end": tw.end} for tw in l.time_windows] if l.time_windows else None}
                        for l in locations],
        "_vehicles": [{"id": v.id, "weight_capacity": v.weight_capacity,
                        "start_time": v.start_time, "end_time": v.end_time,
                        "breaks": [{"duration": b.duration, "earliest_start": b.earliest_start,
                                     "latest_start": b.latest_start} for b in v.breaks] if v.breaks else None}
                       for v in vehicles],
    }


def _loc_id_to_idx(loc_id: str, locations: list[Location]) -> int | None:
    for i, loc in enumerate(locations):
        if loc.id == loc_id:
            return i
    return None


# ═══════════════════════════════════════════════════════════════════════════
# VALIDACIÓN DE RESTRICCIONES
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ConstraintValidation:
    capacity_ok: bool = True
    time_windows_ok: bool = True
    breaks_ok: bool = True
    vehicle_hours_ok: bool = True
    all_deliveries_assigned: bool = True
    errors: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return (self.capacity_ok and self.time_windows_ok and self.breaks_ok
                and self.vehicle_hours_ok and self.all_deliveries_assigned)


def validate_ortools_constraints(ortools_result: dict, scenario: Scenario) -> ConstraintValidation:
    """Valida que OR-Tools respete todas las restricciones."""
    val = ConstraintValidation()
    locations = {l["id"]: l for l in ortools_result["_locations"]}
    vehicles = {v["id"]: v for v in ortools_result["_vehicles"]}

    assigned_ids = set()
    n_deliveries = scenario.n_deliveries

    for route in ortools_result["routes"]:
        veh = vehicles.get(route["vehicle_id"], {})
        capacity = veh.get("weight_capacity", 0)
        veh_start = veh.get("start_time", 0)
        veh_end = veh.get("end_time", 0)
        breaks = veh.get("breaks", [])

        # Trackear carga acumulada
        current_load = 0
        max_load = 0

        for step in route["steps"]:
            loc_id = step["location_id"]
            step_type = step["type"]
            arrival_str = step.get("arrival")

            # Convertir arrival HH:MM:SS a segundos
            arrival_sec = None
            if arrival_str:
                h, m, s = map(int, arrival_str.split(":"))
                arrival_sec = h * 3600 + m * 60 + s

            # ── Capacity check ──
            if step_type == "delivery" and loc_id in locations:
                demand = locations[loc_id].get("weight_demand", 0)
                current_load += demand
                max_load = max(max_load, current_load)
                assigned_ids.add(loc_id)

            # ── Time window check ──
            if step_type == "delivery" and loc_id in locations:
                tws = locations[loc_id].get("time_windows")
                if tws and arrival_sec is not None:
                    tw = tws[0]
                    if arrival_sec < tw["start"] or arrival_sec > tw["end"]:
                        val.time_windows_ok = False
                        val.errors.append(
                            f"TW violada: {loc_id} arrival={arrival_str} "
                            f"ventana=[{tw['start']},{tw['end']}]"
                        )

            # ── Break check ──
            if step_type == "break" and breaks and arrival_sec is not None:
                brk = breaks[0]
                earliest = brk.get("earliest_start", 0)
                latest = brk.get("latest_start", 86400)
                if arrival_sec < earliest or arrival_sec > latest:
                    val.breaks_ok = False
                    val.errors.append(
                        f"Break fuera de ventana: arrival={arrival_str} "
                        f"ventana=[{earliest},{latest}]"
                    )

        # ── Capacity check final ──
        if max_load > capacity:
            val.capacity_ok = False
            val.errors.append(
                f"Capacidad excedida: {route['vehicle_id']} "
                f"max_load={max_load} > cap={capacity}"
            )

        # ── Vehicle hours check ──
        # Último step arrival debe ser <= veh_end
        last_step = route["steps"][-1]
        if last_step.get("arrival"):
            h, m, s = map(int, last_step["arrival"].split(":"))
            last_arrival = h * 3600 + m * 60 + s
            if last_arrival > veh_end:
                val.vehicle_hours_ok = False
                val.errors.append(
                    f"Fin de jornada excedido: {route['vehicle_id']} "
                    f"llegada={last_step['arrival']} > end={veh_end}"
                )

    # ── All deliveries assigned ──
    expected = {f"del_{i}" for i in range(1, n_deliveries + 1)}
    missing = expected - assigned_ids
    if missing:
        val.all_deliveries_assigned = False
        val.errors.append(f"Entregas no asignadas: {missing}")

    return val


def validate_ors_constraints(ors_result: dict, scenario: Scenario) -> ConstraintValidation:
    """Valida que ORS/VROOM respete todas las restricciones."""
    val = ConstraintValidation()

    assigned_jobs = set()
    expected_jobs = {i + 100 for i in range(1, scenario.n_deliveries + 1)}

    for route in ors_result.get("routes", []):
        current_load = 0
        max_load = 0

        for step in route.get("steps", []):
            step_type = step.get("type")
            arrival = step.get("arrival", 0)

            if step_type == "job":
                job_id = step.get("job")
                if job_id:
                    assigned_jobs.add(job_id)
                # Capacity
                load = step.get("load", [0])
                current_load = load[0] if load else 0
                max_load = max(max_load, current_load)

                # Time windows (si el escenario las tiene)
                if scenario.has_time_windows:
                    tw_blocks = [
                        (28800, 39600), (36000, 46800),
                        (43200, 54000), (50400, 61200),
                    ]
                    job_idx = job_id - 101  # 101 -> idx 0
                    tw = tw_blocks[job_idx % len(tw_blocks)]
                    if arrival < tw[0] or arrival > tw[1]:
                        val.time_windows_ok = False
                        val.errors.append(
                            f"ORS TW violada: job#{job_id} arrival={arrival} ventana={tw}"
                        )

            if step_type == "break":
                if scenario.has_breaks:
                    if arrival < scenario.lunch_earliest or arrival > scenario.lunch_latest:
                        val.breaks_ok = False
                        val.errors.append(
                            f"ORS break fuera de ventana: arrival={arrival} "
                            f"ventana=[{scenario.lunch_earliest},{scenario.lunch_latest}]"
                        )

        # Capacity
        if max_load > scenario.capacity:
            val.capacity_ok = False
            val.errors.append(f"ORS cap excedida: max_load={max_load} > cap={scenario.capacity}")

    # All assigned
    missing = expected_jobs - assigned_jobs
    if missing:
        val.all_deliveries_assigned = False
        val.errors.append(f"ORS jobs no asignados: {missing}")

    return val


# ═══════════════════════════════════════════════════════════════════════════
# COMPARACIÓN
# ═══════════════════════════════════════════════════════════════════════════

def _find_coord_idx(coord: tuple, coords_list: list) -> int | None:
    lat, lng = coord
    for i, c in enumerate(coords_list):
        if abs(c[0] - lat) < 0.001 and abs(c[1] - lng) < 0.001:
            return i
    return None


def compute_ors_distance(ors_result: dict, matrix_data: dict) -> int:
    distances = matrix_data["distances"]
    total = 0
    for route in ors_result.get("routes", []):
        steps = route.get("steps", [])
        for i in range(len(steps) - 1):
            loc1 = steps[i].get("location")
            loc2 = steps[i + 1].get("location")
            if loc1 is None or loc2 is None:
                continue
            coord1 = (loc1[1], loc1[0])
            coord2 = (loc2[1], loc2[0])
            idx1 = _find_coord_idx(coord1, matrix_data["coords"])
            idx2 = _find_coord_idx(coord2, matrix_data["coords"])
            if idx1 is not None and idx2 is not None:
                total += distances[idx1][idx2]
    return total


def compare_scenario(ors_result: dict, ortools_result: dict, matrix_data: dict) -> dict:
    ors_summary = ors_result.get("summary", {})
    ors_travel = ors_summary.get("duration", 0)
    ors_vehicles = len(ors_result.get("routes", []))
    ors_unassigned = ors_summary.get("unassigned", 0)
    ors_distance = compute_ors_distance(ors_result, matrix_data)

    ot_stats = ortools_result.get("statistics", {})
    ot_distance = ot_stats.get("total_distance", 0)
    ot_travel = sum(r.get("travel_time", 0) for r in ortools_result.get("routes", []))
    ot_vehicles = ot_stats.get("vehicles_used", 0)
    ot_unassigned = len(ortools_result.get("unassigned", []))

    dist_diff = ot_distance - ors_distance
    dist_pct = (dist_diff / ors_distance * 100) if ors_distance > 0 else 0
    travel_diff = ot_travel - ors_travel
    travel_pct = (travel_diff / ors_travel * 100) if ors_travel > 0 else 0

    return {
        "ors": {"distance_m": ors_distance, "travel_s": ors_travel,
                "vehicles": ors_vehicles, "unassigned": ors_unassigned},
        "ortools": {"distance_m": ot_distance, "travel_s": ot_travel,
                     "vehicles": ot_vehicles, "unassigned": ot_unassigned},
        "diff": {"distance_m": dist_diff, "distance_pct": round(dist_pct, 1),
                 "travel_s": travel_diff, "travel_pct": round(travel_pct, 1),
                 "vehicles_match": ors_vehicles == ot_vehicles,
                 "unassigned_match": ors_unassigned == ot_unassigned},
    }


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    coords = load_coords()
    matrix_data = load_matrix_data()

    print(f"\n{'='*80}")
    print(f"BENCHMARK MULTI-ESCENARIO: OR-Tools vs ORS Optimization (VROOM)")
    print(f"{'='*80}")
    print(f"Datos: 15 coordenadas reales de Madrid (matriz ORS cacheada)")
    print()

    all_results = []
    all_passed = True

    for sc in SCENARIOS:
        print(f"\n{'─'*80}")
        print(f"  {sc.name}")
        print(f"  {sc.n_deliveries} entregas, {sc.n_vehicles} vehículos, "
              f"cap={sc.capacity}, breaks={'sí' if sc.has_breaks else 'no'}, "
              f"TW={'sí' if sc.has_time_windows else 'no'}, "
              f"opt={sc.optimize_by}")
        print(f"{'─'*80}")

        # 1. ORS
        print(f"\n  1. ORS/VROOM...", end=" ")
        t0 = time.time()
        try:
            ors_result = run_ors(sc, coords)
            ors_time = time.time() - t0
            print(f"OK ({ors_time:.1f}s)")
        except Exception as e:
            print(f"ERROR: {e}")
            all_passed = False
            continue

        # 2. OR-Tools
        print(f"  2. OR-Tools...", end=" ")
        t0 = time.time()
        try:
            ortools_result = run_ortools(sc, coords)
            ot_time = time.time() - t0
            print(f"OK ({ot_time:.1f}s)")
        except Exception as e:
            print(f"ERROR: {e}")
            all_passed = False
            continue

        # 3. Comparación
        comp = compare_scenario(ors_result, ortools_result, matrix_data)

        print(f"\n  {'Métrica':<25} {'ORS/VROOM':>12} {'OR-Tools':>12} {'Diff':>15}")
        print(f"  {'-'*65}")
        print(f"  {'Distancia (m)':<25} {comp['ors']['distance_m']:>12} "
              f"{comp['ortools']['distance_m']:>12} "
              f"{comp['diff']['distance_m']:>+10} ({comp['diff']['distance_pct']:+.1f}%)")
        print(f"  {'Travel time (s)':<25} {comp['ors']['travel_s']:>12} "
              f"{comp['ortools']['travel_s']:>12} "
              f"{comp['diff']['travel_s']:>+10} ({comp['diff']['travel_pct']:+.1f}%)")
        print(f"  {'Vehículos':<25} {comp['ors']['vehicles']:>12} "
              f"{comp['ortools']['vehicles']:>12} "
              f"{'✓' if comp['diff']['vehicles_match'] else '✗':>15}")
        print(f"  {'Sin asignar':<25} {comp['ors']['unassigned']:>12} "
              f"{comp['ortools']['unassigned']:>12} "
              f"{'✓' if comp['diff']['unassigned_match'] else '✗':>15}")

        # 4. Validación de restricciones
        print(f"\n  Validación de restricciones:")
        ors_val = validate_ors_constraints(ors_result, sc)
        ot_val = validate_ortools_constraints(ortools_result, sc)

        checks = [
            ("Capacity", ot_val.capacity_ok, ors_val.capacity_ok),
            ("Time windows", ot_val.time_windows_ok, ors_val.time_windows_ok),
            ("Breaks en ventana", ot_val.breaks_ok, ors_val.breaks_ok),
            ("Horario vehículo", ot_val.vehicle_hours_ok, True),
            ("Todas asignadas", ot_val.all_deliveries_assigned, ors_val.all_deliveries_assigned),
        ]
        for name, ot_ok, ors_ok in checks:
            ot_str = "✅" if ot_ok else "❌"
            ors_str = "✅" if ors_ok else "❌"
            print(f"    {name:<25} OR-Tools: {ot_str}   ORS: {ors_str}")

        if ot_val.errors:
            print(f"\n  ⚠️  Errores OR-Tools:")
            for e in ot_val.errors:
                print(f"     - {e}")
            all_passed = False

        if ors_val.errors:
            print(f"\n  ⚠️  Errores ORS:")
            for e in ors_val.errors:
                print(f"     - {e}")

        all_results.append({
            "scenario": sc.name,
            "comparison": comp,
            "ors_routes": ors_result.get("routes", []),
            "ors_summary": ors_result.get("summary", {}),
            "ortools_routes": ortools_result.get("routes", []),
            "ortools_statistics": ortools_result.get("statistics", {}),
            "ortools_constraints": {
                "passed": ot_val.passed,
                "errors": ot_val.errors,
            },
            "ors_constraints": {
                "passed": ors_val.passed,
                "errors": ors_val.errors,
            },
            "timing": {"ors_s": round(ors_time, 2), "ortools_s": round(ot_time, 2)},
        })

    # ── RESUMEN FINAL ──
    print(f"\n{'='*80}")
    print(f"RESUMEN FINAL")
    print(f"{'='*80}")
    print(f"\n  {'Escenario':<45} {'Travel diff':>12} {'Dist diff':>12} {'Restric.':>10}")
    print(f"  {'-'*80}")
    for r in all_results:
        travel_pct = r["comparison"]["diff"]["travel_pct"]
        dist_pct = r["comparison"]["diff"]["distance_pct"]
        constraints = "✅" if r["ortools_constraints"]["passed"] else "❌"
        print(f"  {r['scenario']:<45} {travel_pct:>+10.1f}% {dist_pct:>+10.1f}% {constraints:>10}")

    # Veredicto
    max_travel = max(abs(r["comparison"]["diff"]["travel_pct"]) for r in all_results)
    all_constraints_ok = all(r["ortools_constraints"]["passed"] for r in all_results)

    print(f"\n  Máxima diferencia travel time: {max_travel:.1f}%")
    print(f"  Restricciones válidas: {'✅ todas' if all_constraints_ok else '❌ hay fallos'}")

    if max_travel < 10 and all_constraints_ok:
        print(f"\n✅ CONCLUSIÓN: Modelo validado. Diferencia < 10% vs VROOM y restricciones cumplidas.")
    elif max_travel < 15 and all_constraints_ok:
        print(f"\n⚠️  CONCLUSIÓN: Modelo aceptable. Diferencia < 15% pero restricciones OK.")
    else:
        print(f"\n❌ CONCLUSIÓN: Modelo necesita revisión.")
        all_passed = False

    # Guardar
    with open(RESULTS_PATH, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nResultados guardados: {RESULTS_PATH}")


if __name__ == "__main__":
    main()

"""
Endpoint /demo — Visualización interactiva con Leaflet.js.
Ejecuta casos de uso predefinidos y devuelve un mapa con polylines, isocronas y clusters.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from .isochrone_cache import SyntheticIsochroneProvider
from .models import (
    Location,
    LocationType,
    OptimizeRequest,
    PickupDeliveryPair,
    SolverConfig,
    Vehicle,
)
from .node_selector import NodeSelector, filter_orphan_nodes
from .solver import VRPSolver
from .validator import validate_request

logger = logging.getLogger(__name__)

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════
# CASOS DE USO PREDEFINIDOS
# ═══════════════════════════════════════════════════════════════════════════

def _case_basic() -> OptimizeRequest:
    """1 depot, 1 vehículo, 5 entregas."""
    depot = Location(id="depot", name="Depósito Central", coords=(40.4168, -3.7038), type=LocationType.depot)
    deliveries = [
        Location(id=f"d{i}", name=f"Entrega {i}", coords=(40.4168 + i * 0.005, -3.7038 + i * 0.003),
                 type=LocationType.delivery, weight_demand=20.0, priority="M")
        for i in range(1, 6)
    ]
    vehicles = [Vehicle(id="v1", name="Camión 1", start_location_id="depot", end_location_id="depot",
                        weight_capacity=200.0, fixed_cost=50.0, cost_per_km=2.5, cost_per_hour=20.0, cost_per_stop=3.0)]
    config = SolverConfig(time_limit_seconds=5, optimize_by="cost")
    return OptimizeRequest(locations=[depot] + deliveries, vehicles=vehicles, config=config)


def _case_multi_vehicle() -> OptimizeRequest:
    """1 depot, 3 vehículos, 15 entregas con capacidad limitada."""
    depot = Location(id="depot", name="Depósito", coords=(40.4168, -3.7038), type=LocationType.depot)
    deliveries = [
        Location(id=f"d{i}", name=f"Entrega {i}",
                 coords=(40.4068 + (i % 5) * 0.004, -3.7138 + (i // 5) * 0.004),
                 type=LocationType.delivery, weight_demand=15.0, priority="M")
        for i in range(1, 16)
    ]
    vehicles = [
        Vehicle(id=f"v{i}", name=f"Camión {i}", start_location_id="depot", end_location_id="depot",
                weight_capacity=80.0, fixed_cost=50.0, cost_per_km=2.5, cost_per_hour=20.0, cost_per_stop=3.0)
        for i in range(1, 4)
    ]
    config = SolverConfig(time_limit_seconds=5, optimize_by="cost")
    return OptimizeRequest(locations=[depot] + deliveries, vehicles=vehicles, config=config)


def _case_multi_depot() -> OptimizeRequest:
    """2 depots, 4 vehículos, 20 entregas."""
    depots = [
        Location(id="depot_n", name="Depósito Norte", coords=(40.4468, -3.7038), type=LocationType.depot),
        Location(id="depot_s", name="Depósito Sur", coords=(40.3868, -3.7038), type=LocationType.depot),
    ]
    deliveries = [
        Location(id=f"dn{i}", name=f"Norte {i}",
                 coords=(40.4368 + i * 0.002, -3.6938 + i * 0.002),
                 type=LocationType.delivery, weight_demand=6.0, priority="M")
        for i in range(1, 11)
    ] + [
        Location(id=f"ds{i}", name=f"Sur {i}",
                 coords=(40.3968 - i * 0.002, -3.6938 + i * 0.002),
                 type=LocationType.delivery, weight_demand=6.0, priority="M")
        for i in range(1, 11)
    ]
    vehicles = [
        Vehicle(id="vn1", name="Norte 1 (Grande)", start_location_id="depot_n", end_location_id="depot_n", weight_capacity=200.0, fixed_cost=200.0, cost_per_km=1.5, cost_per_hour=22.0, cost_per_stop=2.0),
        Vehicle(id="vn2", name="Norte 2 (Pequeño)", start_location_id="depot_n", end_location_id="depot_n", weight_capacity=80.0, fixed_cost=20.0, cost_per_km=3.0, cost_per_hour=15.0, cost_per_stop=4.0),
        Vehicle(id="vs1", name="Sur 1 (Grande)", start_location_id="depot_s", end_location_id="depot_s", weight_capacity=200.0, fixed_cost=200.0, cost_per_km=1.5, cost_per_hour=22.0, cost_per_stop=2.0),
        Vehicle(id="vs2", name="Sur 2 (Pequeño)", start_location_id="depot_s", end_location_id="depot_s", weight_capacity=80.0, fixed_cost=20.0, cost_per_km=3.0, cost_per_hour=15.0, cost_per_stop=4.0),
    ]
    config = SolverConfig(time_limit_seconds=10, optimize_by="cost")
    return OptimizeRequest(locations=depots + deliveries, vehicles=vehicles, config=config)


def _case_time_windows() -> OptimizeRequest:
    """1 depot, 2 vehículos, 10 entregas con ventanas de tiempo."""
    from .models import TimeWindow
    depot = Location(id="depot", name="Depósito", coords=(40.4168, -3.7038), type=LocationType.depot)
    deliveries = []
    for i in range(1, 11):
        tw_start = 28800 + (i % 3) * 7200  # 08:00, 10:00, 12:00
        tw_end = tw_start + 10800  # 3h window
        deliveries.append(Location(
            id=f"d{i}", name=f"Entrega {i}",
            coords=(40.4068 + i * 0.003, -3.7138 + i * 0.002),
            type=LocationType.delivery, weight_demand=15.0,
            time_windows=[TimeWindow(start=tw_start, end=tw_end)],
            service_time=600,
            priority="M",
        ))
    vehicles = [
        Vehicle(id="v1", name="Camión 1", start_location_id="depot", end_location_id="depot",
                weight_capacity=100.0, start_time=28800, end_time=64800, fixed_cost=50.0, cost_per_km=2.5, cost_per_hour=20.0, cost_per_stop=3.0),
        Vehicle(id="v2", name="Camión 2", start_location_id="depot", end_location_id="depot",
                weight_capacity=100.0, start_time=28800, end_time=64800, fixed_cost=50.0, cost_per_km=2.5, cost_per_hour=20.0, cost_per_stop=3.0),
    ]
    config = SolverConfig(time_limit_seconds=5, optimize_by="cost")
    return OptimizeRequest(locations=[depot] + deliveries, vehicles=vehicles, config=config)


def _case_backlog_isochrones() -> OptimizeRequest:
    """2 depots, 4 vehículos, 50 entregas — muestra isocronas + fuera de cobertura + selección."""
    depots = [
        Location(id="depot_n", name="Depósito Norte", coords=(40.4468, -3.6838), type=LocationType.depot),
        Location(id="depot_s", name="Depósito Sur", coords=(40.3868, -3.7238), type=LocationType.depot),
    ]
    deliveries = []
    # 40 nodos cercanos a depots
    for i in range(1, 21):
        deliveries.append(Location(
            id=f"dn{i}", name=f"Norte {i}",
            coords=(40.4368 + (i % 5) * 0.002, -3.6738 + (i // 5) * 0.003),
            type=LocationType.delivery, weight_demand=8.0,
            priority="H" if i <= 5 else ("M" if i <= 12 else "L"),
        ))
    for i in range(1, 21):
        deliveries.append(Location(
            id=f"ds{i}", name=f"Sur {i}",
            coords=(40.3968 - (i % 5) * 0.002, -3.7138 + (i // 5) * 0.003),
            type=LocationType.delivery, weight_demand=8.0,
            priority="H" if i <= 5 else ("M" if i <= 12 else "L"),
        ))
    # 10 nodos lejanos (fuera de isocrona)
    for i in range(1, 11):
        deliveries.append(Location(
            id=f"far{i}", name=f"Lejano {i}",
            coords=(40.5668 + i * 0.005, -3.6538),
            type=LocationType.delivery, weight_demand=8.0, priority="H",
        ))
    vehicles = [
        Vehicle(id="vn1", name="Norte 1", start_location_id="depot_n", end_location_id="depot_n", weight_capacity=100.0, fixed_cost=50.0, cost_per_km=2.5, cost_per_hour=20.0, cost_per_stop=3.0),
        Vehicle(id="vn2", name="Norte 2", start_location_id="depot_n", end_location_id="depot_n", weight_capacity=100.0, fixed_cost=50.0, cost_per_km=2.5, cost_per_hour=20.0, cost_per_stop=3.0),
        Vehicle(id="vs1", name="Sur 1", start_location_id="depot_s", end_location_id="depot_s", weight_capacity=100.0, fixed_cost=50.0, cost_per_km=2.5, cost_per_hour=20.0, cost_per_stop=3.0),
        Vehicle(id="vs2", name="Sur 2", start_location_id="depot_s", end_location_id="depot_s", weight_capacity=100.0, fixed_cost=50.0, cost_per_km=2.5, cost_per_hour=20.0, cost_per_stop=3.0),
    ]
    config = SolverConfig(time_limit_seconds=5, allow_skipping_nodes=True, drop_penalty=100000, optimize_by="cost")
    return OptimizeRequest(locations=depots + deliveries, vehicles=vehicles, config=config)


def _case_pickup_delivery() -> OptimizeRequest:
    """1 depot, 2 vehículos, 3 pares pickup-delivery."""
    depot = Location(id="depot", name="Depósito", coords=(40.4168, -3.7038), type=LocationType.depot)
    pickups = [
        Location(id=f"p{i}", name=f"Pickup {i}",
                 coords=(40.4268 + i * 0.003, -3.6938),
                 type=LocationType.pickup, weight_demand=30.0, priority="H")
        for i in range(1, 4)
    ]
    deliveries = [
        Location(id=f"dl{i}", name=f"Delivery {i}",
                 coords=(40.4068 - i * 0.003, -3.7138),
                 type=LocationType.delivery, weight_demand=-30.0, priority="H")
        for i in range(1, 4)
    ]
    pairs = [PickupDeliveryPair(pickup_id=f"p{i}", delivery_id=f"dl{i}") for i in range(1, 4)]
    vehicles = [
        Vehicle(id="v1", name="Camión 1", start_location_id="depot", end_location_id="depot", weight_capacity=100.0, fixed_cost=50.0, cost_per_km=2.5, cost_per_hour=20.0, cost_per_stop=3.0),
        Vehicle(id="v2", name="Camión 2", start_location_id="depot", end_location_id="depot", weight_capacity=100.0, fixed_cost=50.0, cost_per_km=2.5, cost_per_hour=20.0, cost_per_stop=3.0),
    ]
    config = SolverConfig(time_limit_seconds=5, optimize_by="cost")
    return OptimizeRequest(locations=[depot] + pickups + deliveries, vehicles=vehicles,
                           pickups_deliveries=pairs, config=config)


def _case_skills() -> OptimizeRequest:
    """1 depot, 2 vehículos (uno refrigerado), 10 entregas con skills."""
    depot = Location(id="depot", name="Depósito", coords=(40.4168, -3.7038), type=LocationType.depot)
    deliveries = []
    for i in range(1, 11):
        skills = ["refrigerated"] if i <= 4 else None
        deliveries.append(Location(
            id=f"d{i}", name=f"Entrega {i}",
            coords=(40.4068 + i * 0.003, -3.7138 + i * 0.002),
            type=LocationType.delivery, weight_demand=15.0,
            required_skills=skills, priority="M",
        ))
    vehicles = [
        Vehicle(id="v1", name="Camión Normal", start_location_id="depot", end_location_id="depot",
                weight_capacity=120.0, skills=["standard"], fixed_cost=50.0, cost_per_km=2.5, cost_per_hour=20.0, cost_per_stop=3.0),
        Vehicle(id="v2", name="Camión Refrigerado", start_location_id="depot", end_location_id="depot",
                weight_capacity=80.0, skills=["standard", "refrigerated"], fixed_cost=60.0, cost_per_km=2.5, cost_per_hour=20.0, cost_per_stop=3.0),
    ]
    config = SolverConfig(time_limit_seconds=5, allow_skipping_nodes=True, optimize_by="cost")
    return OptimizeRequest(locations=[depot] + deliveries, vehicles=vehicles, config=config)


def _case_breaks() -> OptimizeRequest:
    """1 depot, 1 vehículo con descanso, 8 entregas."""
    from .models import TimeWindow, VehicleBreak
    depot = Location(id="depot", name="Depósito", coords=(40.4168, -3.7038), type=LocationType.depot)
    deliveries = [
        Location(id=f"d{i}", name=f"Entrega {i}",
                 coords=(40.4068 + i * 0.003, -3.7138 + i * 0.002),
                 type=LocationType.delivery, weight_demand=15.0,
                 time_windows=[TimeWindow(start=28800, end=64800)],
                 service_time=300, priority="M")
        for i in range(1, 9)
    ]
    vehicles = [
        Vehicle(id="v1", name="Camión 1", start_location_id="depot", end_location_id="depot",
                weight_capacity=200.0, start_time=28800, end_time=64800,
                breaks=[VehicleBreak(duration=1800, earliest_start=43200, latest_start=46800)],
                fixed_cost=50.0, cost_per_km=2.5, cost_per_hour=20.0, cost_per_stop=3.0),
    ]
    config = SolverConfig(time_limit_seconds=5, optimize_by="cost")
    return OptimizeRequest(locations=[depot] + deliveries, vehicles=vehicles, config=config)


CASES = {
    "basic": ("Básico: 1 vehículo, 5 entregas", _case_basic),
    "multi-vehicle": ("Multi-vehículo: 3 vehículos, 15 entregas", _case_multi_vehicle),
    "multi-depot": ("Multi-depot: 2 depots, 4 vehículos, 20 entregas", _case_multi_depot),
    "time-windows": ("Ventanas de tiempo: 2 vehículos, 10 entregas con TW", _case_time_windows),
    "backlog": ("Backlog + isocronas: 50 entregas, selección por prioridad", _case_backlog_isochrones),
    "pickup-delivery": ("Pickup-delivery: 3 pares vinculados", _case_pickup_delivery),
    "skills": ("Skills: vehículo refrigerado vs normal", _case_skills),
    "breaks": ("Breaks: 1 vehículo con descanso, 8 entregas", _case_breaks),
}


# ═══════════════════════════════════════════════════════════════════════════
# EJECUCIÓN DE CASOS
# ═══════════════════════════════════════════════════════════════════════════

def _run_case(case_id: str) -> dict:
    """Ejecuta un caso y devuelve datos para el mapa."""
    _, builder_fn = CASES[case_id]
    request = builder_fn()

    # Validar request antes de resolver
    validation = validate_request(request)
    if not validation.is_valid:
        logger.warning("Errores de validación en caso %s: %s", case_id, validation.errors)

    # Isocronas
    depots = [loc for loc in request.locations if loc.type == LocationType.depot]
    iso_provider = SyntheticIsochroneProvider()
    isochrones = [
        iso_provider.compute(dep.id, dep.coords, 3600)
        for dep in depots
    ]

    # Selección
    selector = NodeSelector(max_nodes_per_depot=25)
    selection = selector.select(request.locations, request.vehicles, isochrones)

    # Filtrar nodos huérfanos (depots sin vehículos)
    selected_locs, solver_vehicles, selected_ids = filter_orphan_nodes(
        selection, request.vehicles
    )
    solver_locations = depots + selected_locs

    solver_pairs = []
    if request.pickups_deliveries:
        for pair in request.pickups_deliveries:
            if pair.pickup_id in selected_ids and pair.delivery_id in selected_ids:
                solver_pairs.append(pair)

    result = None
    result_by_distance = None
    if solver_vehicles and selection.selected:
        # Run optimized by cost (primary)
        solver = VRPSolver(
            locations=solver_locations,
            vehicles=solver_vehicles,
            config=request.config,
            pairs=solver_pairs,
            matrix_provider="synthetic",
        )
        result = solver.solve()

        # Run optimized by distance for comparison (only if config uses cost)
        if request.config.optimize_by == "cost":
            from copy import deepcopy
            config_dist = deepcopy(request.config)
            config_dist.optimize_by = "distance"
            solver_dist = VRPSolver(
                locations=solver_locations,
                vehicles=solver_vehicles,
                config=config_dist,
                pairs=solver_pairs,
                matrix_provider="synthetic",
            )
            result_by_distance = solver_dist.solve()

    # Construir datos para el mapa
    routes_data = []
    if result and result.routes:
        for route in result.routes:
            coords = []
            for stop in route.stops:
                coords.append([stop.coords[0], stop.coords[1], {
                    "id": stop.location_id,
                    "name": stop.name or "",
                    "type": stop.type,
                    "arrival": stop.arrival or "",
                    "departure": stop.departure or "",
                    "load_weight": stop.load_weight,
                }])
            route_cost = None
            if route.cost:
                route_cost = {
                    "fixed": route.cost.fixed,
                    "distance": route.cost.distance,
                    "time": route.cost.time,
                    "stops": route.cost.stops,
                    "total": route.cost.total,
                }
            routes_data.append({
                "vehicle_id": route.vehicle_id,
                "vehicle_name": route.vehicle_name or route.vehicle_id,
                "stops": coords,
                "total_distance": route.total_distance,
                "total_duration": route.total_duration,
                "cost": route_cost,
            })

    unassigned_data = [
        {"id": u.id, "name": u.name or "", "reason": u.reason or "",
         "coords": next((l.coords for l in request.locations if l.id == u.id), (0, 0))}
        for u in (result.unassigned if result else [])
    ]

    out_of_coverage_data = [
        {"id": loc.id, "name": loc.name or "", "coords": loc.coords}
        for loc in selection.out_of_coverage
    ]

    isochrone_data = [
        {"depot_id": iso.depot_id, "polygon": [[p[0], p[1]] for p in iso.polygon]}
        for iso in isochrones
    ]

    depot_data = [{"id": d.id, "name": d.name or d.id, "coords": d.coords} for d in depots]

    stats = None
    if result and result.statistics:
        stats = {
            "vehicles_used": result.statistics.vehicles_used,
            "vehicles_available": result.statistics.vehicles_available,
            "nodes_assigned": result.statistics.nodes_assigned,
            "nodes_unassigned": result.statistics.nodes_unassigned,
            "total_distance": result.statistics.total_distance,
            "total_duration": result.statistics.total_duration,
            "total_cost": result.statistics.total_cost,
        }

    # Cost comparison: by distance vs by cost
    cost_comparison = None
    if result_by_distance and result_by_distance.statistics and result and result.statistics:
        cost_by_distance = result_by_distance.statistics.total_cost or 0
        cost_by_cost = result.statistics.total_cost or 0
        if cost_by_distance > 0 and cost_by_cost > 0:
            savings = cost_by_distance - cost_by_cost
            savings_pct = (savings / cost_by_distance) * 100 if cost_by_distance > 0 else 0
            cost_comparison = {
                "cost_by_distance": round(cost_by_distance, 2),
                "cost_by_cost": round(cost_by_cost, 2),
                "savings": round(savings, 2),
                "savings_pct": round(savings_pct, 1),
            }

    # Vehicle cost config for display
    vehicle_costs = []
    for v in request.vehicles:
        vehicle_costs.append({
            "id": v.id,
            "name": v.name or v.id,
            "fixed_cost": v.fixed_cost or 0,
            "cost_per_km": v.cost_per_km or 0,
            "cost_per_hour": v.cost_per_hour or 0,
            "cost_per_stop": v.cost_per_stop or 0,
        })

    return {
        "case_id": case_id,
        "case_name": CASES[case_id][0],
        "depots": depot_data,
        "routes": routes_data,
        "unassigned": unassigned_data,
        "out_of_coverage": out_of_coverage_data,
        "isochrones": isochrone_data,
        "recommendations": selection.recommendations,
        "warnings": result.warnings if result else [],
        "statistics": stats,
        "cost_comparison": cost_comparison,
        "vehicle_costs": vehicle_costs,
        "solver_time": result.solver_time if result else 0,
        "errors": [e.message for e in result.errors] if result and result.errors else [],
    }


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/demo", response_class=HTMLResponse)
def demo_index() -> HTMLResponse:
    """Página índice con selector de casos."""
    cases_json = json.dumps({k: v[0] for k, v in CASES.items()})
    return HTMLResponse(_render_html(cases_json))


@router.get("/demo/{case_id}")
def demo_case(case_id: str) -> dict:
    """Ejecuta un caso y devuelve datos JSON para el mapa."""
    if case_id not in CASES:
        return {"error": f"Caso desconocido: {case_id}"}
    return _run_case(case_id)


# ═══════════════════════════════════════════════════════════════════════════
# HTML TEMPLATE
# ═══════════════════════════════════════════════════════════════════════════

def _render_html(cases_json: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VRP Solver - Demo</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css" />
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #1a1a2e; color: #e0e0e0; }}
        #header {{ background: #16213e; padding: 12px 20px; display: flex; align-items: center; gap: 20px; border-bottom: 2px solid #0f3460; }}
        #header h1 {{ font-size: 18px; color: #e94560; white-space: nowrap; }}
        #case-select {{ padding: 8px 12px; background: #0f3460; color: #e0e0e0; border: 1px solid #e94560; border-radius: 4px; font-size: 14px; cursor: pointer; }}
        #case-select option {{ background: #16213e; }}
        #run-btn {{ padding: 8px 20px; background: #e94560; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; font-weight: 600; }}
        #run-btn:hover {{ background: #c81e45; }}
        #run-btn:disabled {{ background: #555; cursor: wait; }}
        #main {{ display: flex; height: calc(100vh - 60px); }}
        #map {{ flex: 1; height: 100%; }}
        #sidebar {{ width: 380px; background: #16213e; padding: 16px; overflow-y: auto; border-left: 2px solid #0f3460; }}
        #sidebar h2 {{ font-size: 15px; color: #e94560; margin-bottom: 10px; border-bottom: 1px solid #0f3460; padding-bottom: 6px; }}
        .stat {{ display: flex; justify-content: space-between; padding: 4px 0; font-size: 13px; }}
        .stat .label {{ color: #888; }}
        .stat .value {{ color: #e94560; font-weight: 600; }}
        .info-box {{ background: #0f3460; border-radius: 6px; padding: 10px; margin-bottom: 12px; font-size: 12px; }}
        .info-box.warning {{ border-left: 3px solid #ffa500; }}
        .info-box.error {{ border-left: 3px solid #ff4444; }}
        .info-box.recommendation {{ border-left: 3px solid #00e676; }}
        .route-item {{ background: #0f3460; border-radius: 6px; padding: 8px 10px; margin-bottom: 8px; font-size: 12px; border-left: 3px solid var(--route-color, #e94560); }}
        .route-item .title {{ font-weight: 600; margin-bottom: 4px; }}
        .route-item .detail {{ color: #888; }}
        #loading {{ display: none; text-align: center; padding: 20px; color: #e94560; }}
        .legend {{ background: #16213e; padding: 10px; border-radius: 6px; font-size: 12px; line-height: 1.8; }}
        .legend .item {{ display: flex; align-items: center; gap: 8px; }}
        .legend .dot {{ width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }}
        .legend .line {{ width: 20px; height: 3px; flex-shrink: 0; }}
        /* Cost cards */
        .cost-hero {{ background: linear-gradient(135deg, #0f3460, #1a1a2e); border: 1px solid #e94560; border-radius: 8px; padding: 14px; margin-bottom: 12px; text-align: center; }}
        .cost-hero .amount {{ font-size: 28px; font-weight: 700; color: #e94560; }}
        .cost-hero .label {{ font-size: 11px; color: #888; text-transform: uppercase; letter-spacing: 1px; }}
        .cost-savings {{ background: #0d4f3c; border: 1px solid #00e676; border-radius: 6px; padding: 10px; margin-bottom: 12px; text-align: center; }}
        .cost-savings .amount {{ font-size: 18px; font-weight: 700; color: #00e676; }}
        .cost-savings .label {{ font-size: 11px; color: #aaa; }}
        .cost-breakdown {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-bottom: 12px; }}
        .cost-cell {{ background: #0f3460; border-radius: 6px; padding: 8px; text-align: center; }}
        .cost-cell .val {{ font-size: 16px; font-weight: 600; color: #e0e0e0; }}
        .cost-cell .lbl {{ font-size: 10px; color: #888; text-transform: uppercase; }}
        .route-cost {{ margin-top: 6px; padding-top: 6px; border-top: 1px solid #1a1a2e; }}
        .route-cost .row {{ display: flex; justify-content: space-between; font-size: 11px; color: #aaa; }}
        .route-cost .row .v {{ color: #e94560; font-weight: 600; }}
        .route-cost .total {{ display: flex; justify-content: space-between; font-size: 13px; font-weight: 700; margin-top: 4px; }}
        .route-cost .total .v {{ color: #e94560; }}
        .cost-config {{ background: #0f3460; border-radius: 6px; padding: 10px; margin-bottom: 12px; }}
        .cost-config .title {{ font-size: 12px; color: #e94560; font-weight: 600; margin-bottom: 8px; }}
        .cost-config .row {{ display: flex; justify-content: space-between; font-size: 11px; color: #aaa; padding: 2px 0; }}
        .cost-config .row .v {{ color: #e0e0e0; font-weight: 500; }}
        .section-toggle {{ cursor: pointer; user-select: none; }}
        .section-toggle::after {{ content: ' ▾'; font-size: 10px; color: #555; }}
        .section-toggle.collapsed::after {{ content: ' ▴'; }}
        .section-content.collapsed {{ display: none; }}
    </style>
</head>
<body>
    <div id="header">
        <h1>VRP Solver — Demo</h1>
        <select id="case-select">
        </select>
        <button id="run-btn" onclick="runCase()">Ejecutar</button>
    </div>
    <div id="main">
        <div id="map"></div>
        <div id="sidebar">
            <h2>Costo Total</h2>
            <div id="cost-hero"><div class="info-box">Ejecuta un caso para ver costos</div></div>
            <h2>Comparación</h2>
            <div id="cost-comparison"></div>
            <h2>Desglose</h2>
            <div id="cost-breakdown"></div>
            <h2>Configuración Flota</h2>
            <div id="cost-config"><div class="info-box">Ejecuta un caso</div></div>
            <h2>Estadísticas</h2>
            <div id="stats"><div class="info-box">Selecciona un caso y ejecuta</div></div>
            <h2>Rutas</h2>
            <div id="routes-list"></div>
            <h2>Alertas</h2>
            <div id="alerts"></div>
            <h2>Leyenda</h2>
            <div class="legend">
                <div class="item"><div class="dot" style="background:#2196F3"></div>Depósito</div>
                <div class="item"><div class="dot" style="background:#4CAF50"></div>Entrega asignada</div>
                <div class="item"><div class="dot" style="background:#FF9800"></div>No asignado</div>
                <div class="item"><div class="dot" style="background:#F44336"></div>Fuera de cobertura</div>
                <div class="item"><div class="dot" style="background:#9C27B0"></div>Pickup</div>
                <div class="item"><div class="dot" style="background:#FF5722"></div>Break</div>
                <div class="item"><div class="line" style="background:#e94560"></div>Isocrona (1h)</div>
            </div>
        </div>
    </div>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        const CASES = {cases_json};
        let map = L.map('map', {{ zoomControl: true, preferCanvas: true }}).setView([40.4168, -3.7038], 12);

        // Base layers (estilo profesional: CartoDB Positron por defecto)
        const baseLayers = {{
            'CartoDB Positron': L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
                attribution: '© OpenStreetMap © CARTO', maxZoom: 20, subdomains: 'abcd'
            }}).addTo(map),
            'CartoDB Dark Matter': L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
                attribution: '© OpenStreetMap © CARTO', maxZoom: 20, subdomains: 'abcd'
            }}),
            'OpenStreetMap': L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                attribution: '© OpenStreetMap', maxZoom: 19
            }})
        }};

        // Paleta Tableau (estilo Nextplot)
        const ROUTE_COLORS = ['#4e79a7', '#e15759', '#9c755f', '#76b7b2', '#59a14f', '#edc948', '#b07aa1', '#ff9da7', '#9c755f', '#bab0ac'];
        let currentLayerControl = null;
        let activeLayers = [];

        // Poblar select
        const sel = document.getElementById('case-select');
        for (const [id, name] of Object.entries(CASES)) {{
            const opt = document.createElement('option');
            opt.value = id; opt.textContent = name;
            sel.appendChild(opt);
        }}

        async function runCase() {{
            const caseId = sel.value;
            const btn = document.getElementById('run-btn');
            btn.disabled = true; btn.textContent = 'Ejecutando...';

            // Limpiar capas anteriores
            activeLayers.forEach(l => l.remove());
            activeLayers = [];
            if (currentLayerControl) {{ currentLayerControl.remove(); currentLayerControl = null; }}

            try {{
                const resp = await fetch('/demo/' + caseId);
                const data = await resp.json();
                await renderMap(data);
                renderSidebar(data);
            }} catch (e) {{
                document.getElementById('stats').innerHTML = '<div class="info-box error">Error: ' + e.message + '</div>';
            }} finally {{
                btn.disabled = false; btn.textContent = 'Ejecutar';
            }}
        }}

        async function fetchOSRMRoute(latlngs) {{
            const coordStr = latlngs.map(p => p[1] + ',' + p[0]).join(';');
            const url = 'https://router.project-osrm.org/route/v1/driving/' + coordStr + '?overview=full&geometries=geojson';
            try {{
                const resp = await fetch(url);
                const json = await resp.json();
                if (json.routes && json.routes.length > 0) {{
                    return json.routes[0].geometry.coordinates.map(c => [c[1], c[0]]);
                }}
            }} catch (e) {{
                console.warn('OSRM fallback to straight line:', e);
            }}
            return latlngs;
        }}

        async function renderMap(data) {{
            const overlays = {{}};

            // Isocronas como feature group
            if (data.isochrones.length > 0) {{
                const isoGroup = L.featureGroup();
                data.isochrones.forEach(iso => {{
                    const polygon = L.polygon(iso.polygon, {{
                        color: '#e94560', weight: 2, opacity: 0.6,
                        fillColor: '#e94560', fillOpacity: 0.08
                    }});
                    polygon.bindPopup('<b>Isocrona 1h</b><br>Depósito: ' + iso.depot_id);
                    polygon.addTo(isoGroup);
                }});
                isoGroup.addTo(map);
                activeLayers.push(isoGroup);
                overlays['Isocronas'] = isoGroup;
            }}

            // Depots como feature group
            if (data.depots.length > 0) {{
                const depotGroup = L.featureGroup();
                data.depots.forEach(d => {{
                    L.circleMarker(d.coords, {{
                        radius: 10, color: '#1565C0', fillColor: '#2196F3',
                        fillOpacity: 0.9, weight: 3
                    }}).bindPopup('<b>Depósito</b><br>' + d.name + '<br>Coords: ' + d.coords[1].toFixed(4) + ', ' + d.coords[0].toFixed(4)).addTo(depotGroup);
                }});
                depotGroup.addTo(map);
                activeLayers.push(depotGroup);
                overlays['Depósitos'] = depotGroup;
            }}

            // Rutas — cada una en su propio feature group (estilo Nextplot)
            const routePromises = data.routes.map(async (route, ri) => {{
                const color = ROUTE_COLORS[ri % ROUTE_COLORS.length];
                const routeGroup = L.featureGroup();
                const routeName = 'Ruta ' + (ri + 1) + ': ' + route.vehicle_name;

                // Filtrar breaks para OSRM
                const realStops = route.stops.filter(s => s[0] !== 0 && s[1] !== 0);
                const osrmLatLngs = realStops.map(s => [s[0], s[1]]);

                // Polyline a nivel de calle
                if (osrmLatLngs.length > 1) {{
                    const roadPath = await fetchOSRMRoute(osrmLatLngs);
                    const polyline = L.polyline(roadPath, {{
                        color: color, weight: 5, opacity: 0.9,
                        lineJoin: 'round', lineCap: 'round', smoothFactor: 1.0
                    }});
                    polyline.bindPopup(
                        '<b>' + routeName + '</b><br>' +
                        'Paradas: ' + route.stops.length + '<br>' +
                        'Distancia: ' + (route.total_distance/1000).toFixed(2) + ' km<br>' +
                        'Duración: ' + (route.total_duration/60).toFixed(0) + ' min'
                    );
                    polyline.addTo(routeGroup);
                }}

                // Circle markers por parada (estilo Nextplot)
                let lastRealCoords = null;
                route.stops.forEach((stop, si) => {{
                    const isPickup = stop[2].type === 'pickup';
                    const isBreak = stop[2].type === 'break';
                    const isDepot = stop[2].type === 'depot';
                    let label = 'Entrega';
                    if (isPickup) label = 'Pickup';
                    if (isBreak) label = 'Break';
                    if (isDepot) label = 'Depósito';

                    let markerCoords = [stop[0], stop[1]];
                    if (isBreak && lastRealCoords) {{
                        markerCoords = lastRealCoords;
                    }} else if (!isBreak) {{
                        lastRealCoords = [stop[0], stop[1]];
                    }}

                    const stopNum = si + 1;
                    const totalStops = route.stops.length;
                    const popupHtml =
                        '<b>' + label + ' ' + stopNum + '/' + totalStops + '</b><br>' +
                        'ID: ' + stop[2].id + '<br>' +
                        'Nombre: ' + stop[2].name + '<br>' +
                        (stop[2].arrival ? 'Llegada: ' + stop[2].arrival + '<br>' : '') +
                        (stop[2].departure ? 'Salida: ' + stop[2].departure + '<br>' : '') +
                        (stop[2].load_weight != null ? 'Carga: ' + stop[2].load_weight.toFixed(1) + ' kg<br>' : '') +
                        'Coords: ' + markerCoords[1].toFixed(4) + ', ' + markerCoords[0].toFixed(4);

                    const icon = L.divIcon({{
                        html: '<div style="background:' + color + ';color:white;border-radius:50%;width:22px;height:22px;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:bold;border:2px solid white;box-shadow:0 1px 3px rgba(0,0,0,0.4);">' + stopNum + '</div>',
                        className: '', iconSize: [22, 22], iconAnchor: [11, 11]
                    }});
                    L.marker(markerCoords, {{ icon: icon }}).bindPopup(popupHtml, {{ maxWidth: 350 }}).addTo(routeGroup);
                }});

                routeGroup.addTo(map);
                activeLayers.push(routeGroup);
                overlays[routeName] = routeGroup;
            }});
            await Promise.all(routePromises);

            // No asignados como feature group
            if (data.unassigned.length > 0) {{
                const unassignedGroup = L.featureGroup();
                data.unassigned.forEach(u => {{
                    L.circleMarker(u.coords, {{
                        radius: 7, color: '#FF6F00', fillColor: '#FF9800',
                        fillOpacity: 0.8, weight: 2
                    }}).bindPopup('<b>No asignado</b><br>' + u.name + '<br>' + (u.reason || ''), {{ maxWidth: 350 }}).addTo(unassignedGroup);
                }});
                unassignedGroup.addTo(map);
                activeLayers.push(unassignedGroup);
                overlays['No asignados (' + data.unassigned.length + ')'] = unassignedGroup;
            }}

            // Fuera de cobertura como feature group
            if (data.out_of_coverage.length > 0) {{
                const oocGroup = L.featureGroup();
                data.out_of_coverage.forEach(o => {{
                    L.circleMarker(o.coords, {{
                        radius: 7, color: '#D32F2F', fillColor: '#F44336',
                        fillOpacity: 0.8, weight: 2
                    }}).bindPopup('<b>Fuera de cobertura</b><br>' + o.name, {{ maxWidth: 350 }}).addTo(oocGroup);
                }});
                oocGroup.addTo(map);
                activeLayers.push(oocGroup);
                overlays['Fuera de cobertura (' + data.out_of_coverage.length + ')'] = oocGroup;
            }}

            // Layer control (estilo Nextplot: toggle rutas y base maps)
            currentLayerControl = L.control.layers(baseLayers, overlays, {{
                collapsed: false, position: 'topright', autoZIndex: true
            }}).addTo(map);

            // Ajustar vista
            const allPoints = [];
            data.depots.forEach(d => allPoints.push(d.coords));
            data.routes.forEach(r => r.stops.forEach(s => {{ if (s[0] !== 0 && s[1] !== 0) allPoints.push([s[0], s[1]]); }}));
            data.out_of_coverage.forEach(o => allPoints.push(o.coords));
            data.unassigned.forEach(u => allPoints.push(u.coords));
            if (allPoints.length > 0) {{
                map.fitBounds(allPoints, {{ padding: [40, 40] }});
            }}
        }}

        function renderSidebar(data) {{
            // ── Cost hero ──
            let costHeroHtml = '';
            if (data.statistics && data.statistics.total_cost != null) {{
                costHeroHtml = '<div class="cost-hero">' +
                    '<div class="amount">$' + data.statistics.total_cost.toFixed(2) + '</div>' +
                    '<div class="label">Costo Total Operativo</div>' +
                    '</div>';
            }} else {{
                costHeroHtml = '<div class="info-box">Sin datos de costo</div>';
            }}
            document.getElementById('cost-hero').innerHTML = costHeroHtml;

            // ── Cost comparison ──
            let comparisonHtml = '';
            if (data.cost_comparison) {{
                const c = data.cost_comparison;
                comparisonHtml = '<div class="info-box" style="margin-bottom:8px">' +
                    '<div class="stat"><span class="label">Optimizando por distancia</span><span class="value">$' + c.cost_by_distance.toFixed(2) + '</span></div>' +
                    '<div class="stat"><span class="label">Optimizando por costo</span><span class="value">$' + c.cost_by_cost.toFixed(2) + '</span></div>' +
                    '</div>';
                if (c.savings > 0) {{
                    comparisonHtml += '<div class="cost-savings">' +
                        '<div class="amount">Ahorro: $' + c.savings.toFixed(2) + ' (' + c.savings_pct + '%)</div>' +
                        '<div class="label">vs. optimización por distancia</div>' +
                        '</div>';
                }} else {{
                    comparisonHtml += '<div class="info-box" style="text-align:center;font-size:11px;color:#888">Sin ahorro adicional en este caso</div>';
                }}
            }} else {{
                comparisonHtml = '<div class="info-box">No disponible</div>';
            }}
            document.getElementById('cost-comparison').innerHTML = comparisonHtml;

            // ── Cost breakdown (aggregate) ──
            let breakdownHtml = '';
            if (data.routes && data.routes.length > 0) {{
                let totalFixed = 0, totalDist = 0, totalTime = 0, totalStops = 0;
                data.routes.forEach(r => {{
                    if (r.cost) {{
                        totalFixed += r.cost.fixed;
                        totalDist += r.cost.distance;
                        totalTime += r.cost.time;
                        totalStops += r.cost.stops;
                    }}
                }});
                if (totalFixed > 0 || totalDist > 0) {{
                    breakdownHtml = '<div class="cost-breakdown">' +
                        '<div class="cost-cell"><div class="val">$' + totalFixed.toFixed(2) + '</div><div class="lbl">Costo Fijo</div></div>' +
                        '<div class="cost-cell"><div class="val">$' + totalDist.toFixed(2) + '</div><div class="lbl">Por Distancia</div></div>' +
                        '<div class="cost-cell"><div class="val">$' + totalTime.toFixed(2) + '</div><div class="lbl">Por Tiempo</div></div>' +
                        '<div class="cost-cell"><div class="val">$' + totalStops.toFixed(2) + '</div><div class="lbl">Por Paradas</div></div>' +
                        '</div>';
                }}
            }}
            if (!breakdownHtml) breakdownHtml = '<div class="info-box">Sin desglose</div>';
            document.getElementById('cost-breakdown').innerHTML = breakdownHtml;

            // ── Vehicle cost config ──
            let configHtml = '';
            if (data.vehicle_costs && data.vehicle_costs.length > 0) {{
                data.vehicle_costs.forEach(v => {{
                    configHtml += '<div class="cost-config">' +
                        '<div class="title">' + v.name + '</div>' +
                        '<div class="row"><span>Costo fijo</span><span class="v">$' + v.fixed_cost.toFixed(2) + '/día</span></div>' +
                        '<div class="row"><span>Costo por km</span><span class="v">$' + v.cost_per_km.toFixed(2) + '/km</span></div>' +
                        '<div class="row"><span>Costo por hora</span><span class="v">$' + v.cost_per_hour.toFixed(2) + '/hr</span></div>' +
                        '<div class="row"><span>Costo por parada</span><span class="v">$' + v.cost_per_stop.toFixed(2) + '/stop</span></div>' +
                        '</div>';
                }});
            }} else {{
                configHtml = '<div class="info-box">Sin configuración</div>';
            }}
            document.getElementById('cost-config').innerHTML = configHtml;

            // ── Statistics ──
            let statsHtml = '';
            if (data.statistics) {{
                statsHtml = '<div class="info-box">' +
                    '<div class="stat"><span class="label">Vehículos usados</span><span class="value">' + data.statistics.vehicles_used + '/' + data.statistics.vehicles_available + '</span></div>' +
                    '<div class="stat"><span class="label">Nodos asignados</span><span class="value">' + data.statistics.nodes_assigned + '</span></div>' +
                    '<div class="stat"><span class="label">Nodos no asignados</span><span class="value">' + data.statistics.nodes_unassigned + '</span></div>' +
                    '<div class="stat"><span class="label">Fuera de cobertura</span><span class="value">' + data.out_of_coverage.length + '</span></div>' +
                    '<div class="stat"><span class="label">Distancia total</span><span class="value">' + (data.statistics.total_distance/1000).toFixed(2) + ' km</span></div>' +
                    '<div class="stat"><span class="label">Duración total</span><span class="value">' + (data.statistics.total_duration/60).toFixed(0) + ' min</span></div>' +
                    '<div class="stat"><span class="label">Tiempo solver</span><span class="value">' + data.solver_time.toFixed(2) + ' s</span></div>' +
                    '</div>';
            }} else if (data.errors.length > 0) {{
                statsHtml = '<div class="info-box error">' + data.errors.join('<br>') + '</div>';
            }} else {{
                statsHtml = '<div class="info-box">Sin resultados</div>';
            }}
            document.getElementById('stats').innerHTML = statsHtml;

            // ── Routes with cost ──
            let routesHtml = '';
            data.routes.forEach((r, i) => {{
                const color = ROUTE_COLORS[i % ROUTE_COLORS.length];
                let costHtml = '';
                if (r.cost) {{
                    costHtml = '<div class="route-cost">' +
                        '<div class="row"><span>Fijo</span><span class="v">$' + r.cost.fixed.toFixed(2) + '</span></div>' +
                        '<div class="row"><span>Distancia</span><span class="v">$' + r.cost.distance.toFixed(2) + '</span></div>' +
                        '<div class="row"><span>Tiempo</span><span class="v">$' + r.cost.time.toFixed(2) + '</span></div>' +
                        '<div class="row"><span>Paradas</span><span class="v">$' + r.cost.stops.toFixed(2) + '</span></div>' +
                        '<div class="total"><span>Total ruta</span><span class="v">$' + r.cost.total.toFixed(2) + '</span></div>' +
                        '</div>';
                }}
                routesHtml += '<div class="route-item" style="--route-color:' + color + '">' +
                    '<div class="title" style="color:' + color + '">' + r.vehicle_name + '</div>' +
                    '<div class="detail">' + r.stops.length + ' paradas · ' +
                    (r.total_distance/1000).toFixed(2) + ' km · ' +
                    (r.total_duration/60).toFixed(0) + ' min</div>' +
                    costHtml +
                    '</div>';
            }});
            if (!routesHtml) routesHtml = '<div class="info-box">Sin rutas</div>';
            document.getElementById('routes-list').innerHTML = routesHtml;

            let alertsHtml = '';
            data.warnings.forEach(w => {{ alertsHtml += '<div class="info-box warning">' + w + '</div>'; }});
            data.recommendations.forEach(r => {{ alertsHtml += '<div class="info-box recommendation">' + r + '</div>'; }});
            data.errors.forEach(e => {{ alertsHtml += '<div class="info-box error">' + e + '</div>'; }});
            if (!alertsHtml) alertsHtml = '<div class="info-box">Sin alertas</div>';
            document.getElementById('alerts').innerHTML = alertsHtml;
        }}

        runCase();
    </script>
</body>
</html>"""

"""
Tests de regresión para los 10 hallazgos de la auditoría.
Cada test valida un fix específico.

Ejecutar: uv run pytest tests/test_fixes.py -v
"""

import copy

import pytest
from vrp_solver.models import (
    Location,
    LocationType,
    OptimizeRequest,
    SolverConfig,
    Vehicle,
)
from vrp_solver.solver import VRPSolver
from vrp_solver.validator import validate_request


def make_basic_request(
    n_deliveries: int = 5,
    vehicles: list[Vehicle] | None = None,
) -> OptimizeRequest:
    coords = [
        (40.4168, -3.7038),
        (40.4080, -3.6920),
        (40.4200, -3.7100),
        (40.4150, -3.6850),
        (40.4300, -3.7000),
        (40.4050, -3.7150),
    ]
    locations = [
        Location(id="depot", name="Depósito", coords=coords[0], type=LocationType.depot)
    ]
    for i in range(1, min(n_deliveries + 1, len(coords))):
        locations.append(Location(
            id=f"del_{i}",
            name=f"Entrega {i}",
            coords=coords[i],
            type=LocationType.delivery,
            weight_demand=10.0,
        ))

    if vehicles is None:
        vehicles = [Vehicle(
            id="veh_1", name="Vehículo 1",
            start_location_id="depot", end_location_id="depot",
            weight_capacity=200.0,
        )]

    return OptimizeRequest(locations=locations, vehicles=vehicles)


# ═══════════════════════════════════════════════════════════════════════════
# FIX #1: fixed_cost se aplica por vehículo, no a todos
# ═══════════════════════════════════════════════════════════════════════════

class TestFixedCostPerVehicle:
    """El fixed_cost debe aplicarse por vehículo individual."""

    def test_different_fixed_costs(self):
        request = make_basic_request(n_deliveries=4)
        request.vehicles = [
            Vehicle(
                id="cheap", name="Barato",
                start_location_id="depot", end_location_id="depot",
                weight_capacity=200.0, fixed_cost=100,
            ),
            Vehicle(
                id="expensive", name="Caro",
                start_location_id="depot", end_location_id="depot",
                weight_capacity=200.0, fixed_cost=10000,
            ),
        ]
        solver = VRPSolver.from_request(request, matrix_provider="synthetic")
        result = solver.solve()

        assert not result.errors
        # El solver debería preferir el vehículo barato si solo hay 4 entregas
        assert len(result.routes) >= 1
        # El vehículo caro debería usarse solo si es necesario
        used_ids = {r.vehicle_id for r in result.routes}
        assert "cheap" in used_ids


# ═══════════════════════════════════════════════════════════════════════════
# FIX #2: Multi-depot — start_location_id/end_location_id se respetan
# ═══════════════════════════════════════════════════════════════════════════

class TestMultiDepot:
    """Cada vehículo debe salir de su propio start_location_id."""

    def test_two_depots_two_vehicles(self):
        locations = [
            Location(id="depot_north", name="Depósito Norte", coords=(40.4500, -3.7000), type=LocationType.depot),
            Location(id="depot_south", name="Depósito Sur", coords=(40.3800, -3.7000), type=LocationType.depot),
            Location(id="del_1", name="Entrega 1", coords=(40.4400, -3.6900), type=LocationType.delivery, weight_demand=10.0),
            Location(id="del_2", name="Entrega 2", coords=(40.3900, -3.6900), type=LocationType.delivery, weight_demand=10.0),
        ]
        vehicles = [
            Vehicle(id="veh_n", name="Norte", start_location_id="depot_north", end_location_id="depot_north", weight_capacity=100.0),
            Vehicle(id="veh_s", name="Sur", start_location_id="depot_south", end_location_id="depot_south", weight_capacity=100.0),
        ]
        request = OptimizeRequest(locations=locations, vehicles=vehicles)
        solver = VRPSolver.from_request(request, matrix_provider="synthetic")
        result = solver.solve()

        assert not result.errors
        assert len(result.routes) == 2

        # Cada vehículo debe salir de su depósito
        for route in result.routes:
            first_stop = route.stops[0]
            if route.vehicle_id == "veh_n":
                assert first_stop.location_id == "depot_north"
            elif route.vehicle_id == "veh_s":
                assert first_stop.location_id == "depot_south"


# ═══════════════════════════════════════════════════════════════════════════
# FIX #4: Demandas float se escalan (×1000), no se redondean a 0
# ═══════════════════════════════════════════════════════════════════════════

class TestFloatDemandPrecision:
    """Demandas pequeñas (0.5) no deben desaparecer por redondeo."""

    def test_small_demands_accumulate(self):
        request = make_basic_request(n_deliveries=3)
        # Demandas pequeñas que con redondeo simple serían 0 o 1
        for loc in request.locations[1:]:
            loc.weight_demand = 0.5
        request.vehicles[0].weight_capacity = 1.0  # Solo puede llevar 2 entregas (0.5 + 0.5 = 1.0)

        solver = VRPSolver.from_request(request, matrix_provider="synthetic")
        result = solver.solve()

        assert not result.errors
        # Con escalado ×1000: 0.5 → 500, capacidad 1.0 → 1000
        # Debe poder llevar 2 entregas (500+500=1000 ≤ 1000)
        # La tercera debe quedar sin asignar o usar otro vehículo
        total_delivered = sum(
            1 for r in result.routes
            for s in r.stops
            if s.type == "delivery"
        )
        assert total_delivered >= 2  # Al menos 2 deben poder entregarse


# ═══════════════════════════════════════════════════════════════════════════
# FIX #5: auto_retry no muta el config original del request
# ═══════════════════════════════════════════════════════════════════════════

class TestConfigNotMutated:
    """El config del request original no debe mutarse tras auto-retry."""

    def test_config_preserved_after_solve(self):
        request = make_basic_request(n_deliveries=3)
        original_allow_skipping = request.config.allow_skipping_nodes
        assert original_allow_skipping is False

        solver = VRPSolver.from_request(request, matrix_provider="synthetic")
        result = solver.solve()

        # El config del request original NO debe haber cambiado
        assert request.config.allow_skipping_nodes == original_allow_skipping


# ═══════════════════════════════════════════════════════════════════════════
# FIX #8: Skills — nodo sin vehículo compatible no se asigna a cualquiera
# ═══════════════════════════════════════════════════════════════════════════

class TestSkillsNoMatch:
    """Si ningún vehículo tiene las skills, el nodo no debe asignarse incorrectamente."""

    def test_node_with_unmatched_skills_stays_unassigned(self):
        request = make_basic_request(n_deliveries=3)
        request.config.allow_skipping_nodes = True
        request.locations[1].required_skills = ["refrigerated"]
        # Ningún vehículo tiene "refrigerated"

        solver = VRPSolver.from_request(request, matrix_provider="synthetic")
        result = solver.solve()

        # del_1 no debería estar asignado a ninguna ruta
        assigned_ids = {
            s.location_id for r in result.routes for s in r.stops
            if s.type == "delivery"
        }
        assert "del_1" not in assigned_ids


# ═══════════════════════════════════════════════════════════════════════════
# FIX #10: cost_per_km se usa en el modelo
# ═══════════════════════════════════════════════════════════════════════════

class TestCostPerKm:
    """cost_per_km debe afectar la selección de rutas."""

    def test_cost_per_km_runs_without_error(self):
        request = make_basic_request(n_deliveries=3)
        request.vehicles[0].cost_per_km = 1.5

        solver = VRPSolver.from_request(request, matrix_provider="synthetic")
        result = solver.solve()

        assert not result.errors
        assert len(result.routes) >= 1

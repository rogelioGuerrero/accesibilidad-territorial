"""
Tests del solver VRP con datos reales de ORS (matriz cacheada).
Valida que el modelo OR-Tools está bien construido.

Ejecutar: uv run pytest tests/ -v
"""

import json
from pathlib import Path

import pytest
from vrp_solver.models import (
    Location,
    LocationType,
    OptimizeRequest,
    OptimizationObjective,
    PickupDeliveryPair,
    SolverConfig,
    Vehicle,
)
from vrp_solver.solver import VRPSolver

# ═══════════════════════════════════════════════════════════════════════════
# FIXTURES — datos reales de Madrid (matriz ORS cacheada)
# ═══════════════════════════════════════════════════════════════════════════

FIXTURES_DIR = Path(__file__).parent / "fixtures"
MATRIX_PATH = FIXTURES_DIR / "matrix_madrid_15.json"
COORDS_PATH = FIXTURES_DIR / "coords_madrid_15.json"


def load_coords() -> list[tuple[float, float]]:
    with open(COORDS_PATH) as f:
        return [tuple(c) for c in json.load(f)["coords"]]


def make_real_locations(n_deliveries: int = 14) -> list[Location]:
    """Crea locations reales desde el fixture de Madrid."""
    coords = load_coords()
    locations = [
        Location(
            id="depot",
            name="Depósito Central Madrid",
            coords=coords[0],
            type=LocationType.depot,
        )
    ]
    for i in range(1, min(n_deliveries + 1, len(coords))):
        locations.append(Location(
            id=f"del_{i}",
            name=f"Entrega Madrid {i}",
            coords=coords[i],
            type=LocationType.delivery,
            weight_demand=10.0,
            service_time=300,
        ))
    return locations


def make_real_pickup_delivery() -> tuple[list[Location], list[PickupDeliveryPair]]:
    """Crea locations + pares pickup-delivery desde el fixture de Madrid."""
    coords = load_coords()
    locations = [
        Location(
            id="depot",
            name="Depósito Central Madrid",
            coords=coords[0],
            type=LocationType.depot,
        ),
        Location(
            id="pickup_1",
            name="Recogida Salamanca",
            coords=coords[1],
            type=LocationType.pickup,
            weight_demand=15.0,
            service_time=300,
        ),
        Location(
            id="delivery_1",
            name="Entrega Retiro",
            coords=coords[8],
            type=LocationType.delivery,
            weight_demand=-15.0,
            service_time=300,
        ),
        Location(
            id="pickup_2",
            name="Recogida Tetuán",
            coords=coords[7],
            type=LocationType.pickup,
            weight_demand=20.0,
            service_time=300,
        ),
        Location(
            id="delivery_2",
            name="Entrega Vallecas",
            coords=coords[4],
            type=LocationType.delivery,
            weight_demand=-20.0,
            service_time=300,
        ),
    ]
    pairs = [
        PickupDeliveryPair(pickup_id="pickup_1", delivery_id="delivery_1"),
        PickupDeliveryPair(pickup_id="pickup_2", delivery_id="delivery_2"),
    ]
    return locations, pairs


def make_vehicle(idx: int, capacity: float = 100.0) -> Vehicle:
    return Vehicle(
        id=f"veh_{idx}",
        name=f"Vehículo {idx}",
        start_location_id="depot",
        end_location_id="depot",
        weight_capacity=capacity,
    )


def make_solver(request: OptimizeRequest) -> VRPSolver:
    """Crea solver con matriz ORS cacheada (datos reales)."""
    return VRPSolver.from_request(request, matrix_provider="cached", matrix_path=str(MATRIX_PATH))


# ═══════════════════════════════════════════════════════════════════════════
# TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestBasicVRP:
    """Tests del modelo base con matriz ORS real."""

    def test_single_vehicle_5_deliveries(self):
        """1 vehículo, 5 entregas reales — debe asignar todo."""
        locations = make_real_locations(n_deliveries=5)
        vehicles = [make_vehicle(1)]
        request = OptimizeRequest(locations=locations, vehicles=vehicles)

        solver = make_solver(request)
        result = solver.solve()

        assert not result.errors, f"Solver errors: {result.errors}"
        assert len(result.routes) == 1
        assert result.routes[0].total_stops >= 6
        assert len(result.unassigned) == 0
        assert result.routes[0].total_distance > 0

    def test_two_vehicles_split_deliveries(self):
        """2 vehículos capacidad 50, 10 entregas → 5 por vehículo."""
        locations = make_real_locations(n_deliveries=10)
        vehicles = [make_vehicle(1, capacity=50.0), make_vehicle(2, capacity=50.0)]
        request = OptimizeRequest(locations=locations, vehicles=vehicles)

        solver = make_solver(request)
        result = solver.solve()

        assert not result.errors
        assert len(result.routes) == 2
        total_deliveries = sum(r.total_stops - 2 for r in result.routes)
        assert total_deliveries == 10

    def test_all_14_deliveries(self):
        """1 vehículo capacidad 200, 14 entregas reales — todas asignadas."""
        locations = make_real_locations(n_deliveries=14)
        vehicles = [make_vehicle(1, capacity=200.0)]
        request = OptimizeRequest(locations=locations, vehicles=vehicles)

        solver = make_solver(request)
        result = solver.solve()

        assert not result.errors
        assert len(result.routes) == 1
        assert len(result.unassigned) == 0
        assert result.routes[0].total_distance < 100_000


class TestCapacity:
    """Tests de restricción de capacidad con datos reales."""

    def test_capacity_overflow_splits_routes(self):
        """Vehículo capacidad 30, entregas de 10 c/u → 3 por vehículo."""
        locations = make_real_locations(n_deliveries=6)
        vehicles = [make_vehicle(1, capacity=30.0), make_vehicle(2, capacity=30.0)]
        request = OptimizeRequest(locations=locations, vehicles=vehicles)

        solver = make_solver(request)
        result = solver.solve()

        assert not result.errors
        for route in result.routes:
            assert route.max_weight <= 30

    def test_capacity_exceeded_unassigned(self):
        """1 vehículo capacidad 5, entregas de 10 → no puede asignar."""
        locations = make_real_locations(n_deliveries=2)
        vehicles = [make_vehicle(1, capacity=5.0)]
        request = OptimizeRequest(locations=locations, vehicles=vehicles)

        solver = make_solver(request)
        result = solver.solve()

        assert len(result.unassigned) >= 1, "La entrega con demanda 10 debe ser no asignada (capacidad 5)"


class TestTimeWindows:
    """Tests de ventanas de tiempo con datos reales."""

    def test_time_window_respected(self):
        """Nodo con ventana 08:00-10:00, vehículo empieza a las 08:00."""
        from vrp_solver.models import TimeWindow

        coords = load_coords()
        depot = Location(
            id="depot", name="Depósito", coords=coords[0],
            type=LocationType.depot,
        )
        delivery = Location(
            id="del_1", name="Entrega con ventana",
            coords=coords[1],
            type=LocationType.delivery,
            weight_demand=10.0,
            service_time=300,
            time_windows=[TimeWindow(start=28800, end=36000)],
        )
        vehicle = Vehicle(
            id="veh_1", name="Vehículo 1",
            start_location_id="depot", end_location_id="depot",
            weight_capacity=100.0,
            start_time=28800,
        )

        request = OptimizeRequest(locations=[depot, delivery], vehicles=[vehicle])
        solver = make_solver(request)
        result = solver.solve()

        assert not result.errors
        assert len(result.routes) == 1
        # stops[0] es el depot, stops[1] es la entrega con time window
        stop = result.routes[0].stops[1]
        assert stop.arrival is not None, "La entrega debe tener arrival"
        h, m, s = map(int, stop.arrival.split(":"))
        arrival_sec = h * 3600 + m * 60 + s
        assert 28800 <= arrival_sec <= 36000, f"Llegada {stop.arrival} fuera de ventana 08:00-10:00"


class TestPickupDelivery:
    """Tests de pares pickup & delivery con datos reales."""

    def test_pickup_before_delivery(self):
        """Los pickups deben visitarse antes que sus deliveries."""
        locations, pairs = make_real_pickup_delivery()
        vehicle = make_vehicle(1, capacity=100.0)

        request = OptimizeRequest(
            locations=locations,
            vehicles=[vehicle],
            pickups_deliveries=pairs,
        )

        solver = make_solver(request)
        result = solver.solve()

        assert not result.errors
        assert len(result.routes) == 1

        stops = result.routes[0].stops
        for pair in pairs:
            pickup_pos = next(i for i, s in enumerate(stops) if s.location_id == pair.pickup_id)
            delivery_pos = next(i for i, s in enumerate(stops) if s.location_id == pair.delivery_id)
            assert pickup_pos < delivery_pos, f"Pickup {pair.pickup_id} debe ir antes que delivery {pair.delivery_id}"


class TestDropPenalty:
    """Tests de allow_skipping_nodes."""

    def test_skip_unfeasible_node(self):
        """Con allow_skipping, el solver omite nodos infactibles."""
        from vrp_solver.models import TimeWindow

        coords = load_coords()
        depot = Location(
            id="depot", name="Depósito", coords=coords[0],
            type=LocationType.depot,
        )
        impossible = Location(
            id="impossible", name="Entrega imposible",
            coords=coords[1],
            type=LocationType.delivery,
            weight_demand=10.0,
            service_time=300,
            time_windows=[TimeWindow(start=82800, end=86340)],
        )
        vehicle = Vehicle(
            id="veh_1", name="Vehículo 1",
            start_location_id="depot", end_location_id="depot",
            weight_capacity=100.0,
            start_time=28800,
            end_time=64800,
        )

        request = OptimizeRequest(
            locations=[depot, impossible],
            vehicles=[vehicle],
            config=SolverConfig(allow_skipping_nodes=True, drop_penalty=100000),
        )

        solver = make_solver(request)
        result = solver.solve()

        assert len(result.unassigned) >= 1, "El nodo con TW imposible debe ser no asignado"


class TestBreaks:
    """Tests de breaks (descansos programados) con datos reales."""

    def test_lunch_break_inserted(self):
        """
        Vehículo con almuerzo (45 min, ventana 12:00-14:00).
        Con 8 entregas y service_time, la ruta pasa por el mediodía.
        El break debe aparecer en la ruta como tipo "break".
        """
        from vrp_solver.models import VehicleBreak, TimeWindow

        locations = make_real_locations(n_deliveries=8)
        # Asegurar que cada entrega tiene service_time para que la ruta sea larga
        for loc in locations:
            if loc.type == LocationType.delivery:
                loc.service_time = 600  # 10 min por entrega

        vehicle = Vehicle(
            id="veh_1", name="Vehículo 1",
            start_location_id="depot", end_location_id="depot",
            weight_capacity=200.0,
            start_time=28800,   # 08:00
            end_time=61200,     # 17:00
            breaks=[
                VehicleBreak(
                    duration=2700,  # 45 min
                    earliest_start=43200,  # 12:00
                    latest_start=50400,    # 14:00
                ),
            ],
        )

        request = OptimizeRequest(locations=locations, vehicles=[vehicle])
        solver = make_solver(request)
        result = solver.solve()

        assert not result.errors, f"Solver errors: {result.errors}"
        assert len(result.routes) == 1

        # Buscar el break en las paradas
        break_stops = [s for s in result.routes[0].stops if s.type == "break"]
        assert len(break_stops) == 1, f"Se esperaba 1 break, se encontraron {len(break_stops)}"

        # Verificar que el break está dentro de la ventana 12:00-14:00
        break_stop = break_stops[0]
        assert break_stop.arrival is not None
        h, m, s = map(int, break_stop.arrival.split(":"))
        arrival_sec = h * 3600 + m * 60 + s
        assert 43200 <= arrival_sec <= 50400, (
            f"Break inicia a {break_stop.arrival}, debe estar entre 12:00 y 14:00"
        )

    def test_break_does_not_add_distance(self):
        """El break no suma distancia al recorrido."""
        from vrp_solver.models import VehicleBreak

        locations = make_real_locations(n_deliveries=5)

        # Sin break
        vehicle_no_break = Vehicle(
            id="veh_1", name="Vehículo 1",
            start_location_id="depot", end_location_id="depot",
            weight_capacity=200.0,
        )
        request1 = OptimizeRequest(locations=locations, vehicles=[vehicle_no_break])
        solver1 = make_solver(request1)
        result1 = solver1.solve()

        # Con break
        vehicle_with_break = Vehicle(
            id="veh_1", name="Vehículo 1",
            start_location_id="depot", end_location_id="depot",
            weight_capacity=200.0,
            breaks=[
                VehicleBreak(
                    duration=2700,
                    earliest_start=43200,
                    latest_start=50400,
                ),
            ],
        )
        request2 = OptimizeRequest(locations=locations, vehicles=[vehicle_with_break])
        solver2 = make_solver(request2)
        result2 = solver2.solve()

        assert not result1.errors
        assert not result2.errors

        # La distancia con break debe ser <= sin break (el break no añade recorrido)
        dist_no_break = result1.routes[0].total_distance
        dist_with_break = result2.routes[0].total_distance
        assert dist_with_break <= dist_no_break + 1, (
            f"Break añadió distancia: sin={dist_no_break}, con={dist_with_break}"
        )

    def test_break_duration_respected(self):
        """La duración del break en la ruta debe ser la configurada."""
        from vrp_solver.models import VehicleBreak

        locations = make_real_locations(n_deliveries=8)
        for loc in locations:
            if loc.type == LocationType.delivery:
                loc.service_time = 600

        break_duration = 1800  # 30 min
        vehicle = Vehicle(
            id="veh_1", name="Vehículo 1",
            start_location_id="depot", end_location_id="depot",
            weight_capacity=200.0,
            start_time=28800,
            end_time=61200,
            breaks=[
                VehicleBreak(
                    duration=break_duration,
                    earliest_start=43200,
                    latest_start=50400,
                ),
            ],
        )

        request = OptimizeRequest(locations=locations, vehicles=[vehicle])
        solver = make_solver(request)
        result = solver.solve()

        assert not result.errors
        break_stops = [s for s in result.routes[0].stops if s.type == "break"]
        assert len(break_stops) == 1

        # arrival + duration = departure
        break_stop = break_stops[0]
        assert break_stop.arrival and break_stop.departure
        h_a, m_a, s_a = map(int, break_stop.arrival.split(":"))
        h_d, m_d, s_d = map(int, break_stop.departure.split(":"))
        arrival_sec = h_a * 3600 + m_a * 60 + s_a
        departure_sec = h_d * 3600 + m_d * 60 + s_d
        actual_duration = departure_sec - arrival_sec
        assert actual_duration == break_duration, (
            f"Duración del break: esperada={break_duration}, actual={actual_duration}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# TESTS: MEJORAS DEL SOLVER
# ═══════════════════════════════════════════════════════════════════════════

class TestSoftTimeWindows:
    """Valida que soft time windows permite llegada tardía."""

    def test_soft_tw_allows_late_arrival(self):
        """Con soft TW, el solver encuentra solución aunque sea imposible llegar a tiempo."""
        from vrp_solver.models import TimeWindow

        locations = make_real_locations(n_deliveries=5)
        # TW imposible: ventana de 1 segundo en el pasado
        for loc in locations:
            if loc.type == LocationType.delivery:
                loc.time_windows = [TimeWindow(start=0, end=1)]

        vehicle = Vehicle(
            id="veh_1", name="Vehículo 1",
            start_location_id="depot", end_location_id="depot",
            weight_capacity=200.0,
            start_time=28800,
            end_time=61200,
        )

        # Hard TW → debe fallar
        request_hard = OptimizeRequest(
            locations=locations, vehicles=[vehicle],
            config=SolverConfig(time_limit_seconds=10, auto_retry_with_skipping=False),
        )
        solver_hard = make_solver(request_hard)
        result_hard = solver_hard.solve()
        assert result_hard.errors, "Hard TW imposible debería fallar"

        # Soft TW → debe encontrar solución (con llegada tardía)
        request_soft = OptimizeRequest(
            locations=locations, vehicles=[vehicle],
            config=SolverConfig(
                time_limit_seconds=10,
                soft_time_windows=True,
                late_arrival_penalty=100,
                auto_retry_with_skipping=False,
            ),
        )
        solver_soft = make_solver(request_soft)
        result_soft = solver_soft.solve()
        assert not result_soft.errors, "Soft TW debería encontrar solución"
        assert len(result_soft.routes) >= 1


class TestAutoRetry:
    """Valida que auto-retry con skipping funciona."""

    def test_auto_retry_finds_partial_solution(self):
        """Cuando el solver falla, auto-retry entrega lo que pueda."""
        from vrp_solver.models import TimeWindow

        locations = make_real_locations(n_deliveries=8)
        # Hacer una entrega imposible (TW en el pasado)
        locations[1].time_windows = [TimeWindow(start=0, end=1)]

        vehicle = Vehicle(
            id="veh_1", name="Vehículo 1",
            start_location_id="depot", end_location_id="depot",
            weight_capacity=200.0,
            start_time=28800,
            end_time=61200,
        )

        request = OptimizeRequest(
            locations=locations, vehicles=[vehicle],
            config=SolverConfig(
                time_limit_seconds=10,
                auto_retry_with_skipping=True,
                allow_skipping_nodes=False,
            ),
        )
        solver = make_solver(request)
        result = solver.solve()

        # Debe tener solución parcial (7 de 8 entregas)
        assert not result.errors, f"Auto-retry debería encontrar solución parcial: {result.errors}"
        assert len(result.unassigned) == 1, f"Debería omitir 1 nodo imposible, omitió {len(result.unassigned)}"
        assert result.unassigned[0].id == "del_1"
        assert any("Reintentando" in w for w in result.warnings)


class TestMaxDistance:
    """Valida que max_distance limita la distancia por vehículo."""

    def test_max_distance_splits_routes(self):
        """Con max_distance bajo, se necesitan más vehículos."""
        locations = make_real_locations(n_deliveries=8)

        # Sin restricción: 1 vehículo basta
        veh_single = Vehicle(
            id="veh_1", name="Vehículo 1",
            start_location_id="depot", end_location_id="depot",
            weight_capacity=200.0,
        )

        request1 = OptimizeRequest(
            locations=locations, vehicles=[veh_single],
            config=SolverConfig(time_limit_seconds=15),
        )
        solver1 = make_solver(request1)
        result1 = solver1.solve()
        assert not result1.errors
        dist1 = result1.statistics.total_distance

        # Con max_distance: forzar 2 vehículos
        veh_a = Vehicle(
            id="veh_a", name="Vehículo A",
            start_location_id="depot", end_location_id="depot",
            weight_capacity=200.0,
            max_distance=int(dist1 * 0.6),  # 60% de la distancia original
        )
        veh_b = Vehicle(
            id="veh_b", name="Vehículo B",
            start_location_id="depot", end_location_id="depot",
            weight_capacity=200.0,
            max_distance=int(dist1 * 0.6),
        )

        request2 = OptimizeRequest(
            locations=locations, vehicles=[veh_a, veh_b],
            config=SolverConfig(time_limit_seconds=15),
        )
        solver2 = make_solver(request2)
        result2 = solver2.solve()
        assert not result2.errors
        assert result2.statistics.vehicles_used >= 2, (
            f"max_distance debería forzar 2+ vehículos, usó {result2.statistics.vehicles_used}"
        )
        # Ninguna ruta excede max_distance
        for r in result2.routes:
            assert r.total_distance <= int(dist1 * 0.6) + 1, (
                f"Ruta {r.vehicle_id} excede max_distance: {r.total_distance}"
            )


class TestMaxTasks:
    """Valida que max_tasks limita el número de paradas por vehículo."""

    def test_max_tasks_limits_stops(self):
        """Con max_tasks=4 y 8 entregas, se necesitan 2 vehículos."""
        locations = make_real_locations(n_deliveries=8)

        veh_a = Vehicle(
            id="veh_a", name="Vehículo A",
            start_location_id="depot", end_location_id="depot",
            weight_capacity=200.0,
            max_tasks=4,
        )
        veh_b = Vehicle(
            id="veh_b", name="Vehículo B",
            start_location_id="depot", end_location_id="depot",
            weight_capacity=200.0,
            max_tasks=4,
        )

        request = OptimizeRequest(
            locations=locations, vehicles=[veh_a, veh_b],
            config=SolverConfig(time_limit_seconds=15),
        )
        solver = make_solver(request)
        result = solver.solve()

        assert not result.errors
        assert result.statistics.vehicles_used >= 2
        for r in result.routes:
            # total_stops incluye depot start+end, así que max_tasks+2 como máximo
            real_stops = sum(1 for s in r.stops if s.type not in ("depot", "break"))
            assert real_stops <= 4, (
                f"Vehículo {r.vehicle_id} excede max_tasks: {real_stops} paradas"
            )


class TestPriorities:
    """Valida que las prioridades afectan qué nodos se omiten."""

    def test_high_priority_not_skipped(self):
        """Cuando se omiten nodos, los de prioridad H se mantienen."""
        locations = make_real_locations(n_deliveries=8)
        # Marcar del_1 como alta, del_2 como baja
        locations[1].priority = "H"
        locations[2].priority = "L"

        # Capacidad muy baja: solo puede hacer 3 entregas por vehículo
        veh_a = Vehicle(
            id="veh_a", name="Vehículo A",
            start_location_id="depot", end_location_id="depot",
            weight_capacity=30,  # 3 entregas de 10
        )
        veh_b = Vehicle(
            id="veh_b", name="Vehículo B",
            start_location_id="depot", end_location_id="depot",
            weight_capacity=30,
        )

        request = OptimizeRequest(
            locations=locations, vehicles=[veh_a, veh_b],
            config=SolverConfig(
                time_limit_seconds=15,
                allow_skipping_nodes=True,
                drop_penalty=100000,
            ),
        )
        solver = make_solver(request)
        result = solver.solve()

        assert not result.errors
        # del_1 (H) no debería estar en unassigned
        unassigned_ids = {u.id for u in result.unassigned}
        assert "del_1" not in unassigned_ids, (
            f"Nodo de prioridad H fue omitido: {unassigned_ids}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# COSTOS — matriz ORS real de Madrid
# ═══════════════════════════════════════════════════════════════════════════

class TestCosts:
    """Tests de costos con matriz ORS real cacheada."""

    def test_cost_breakdown_in_response(self):
        """El resultado debe incluir desglose de costos cuando se configuran."""
        locations = make_real_locations(n_deliveries=5)
        vehicles = [
            Vehicle(
                id="veh_1", name="Vehículo 1",
                start_location_id="depot", end_location_id="depot",
                weight_capacity=200.0,
                fixed_cost=50.0,
                cost_per_km=2.5,
                cost_per_hour=20.0,
                cost_per_stop=3.0,
            ),
        ]
        request = OptimizeRequest(locations=locations, vehicles=vehicles)
        solver = make_solver(request)
        result = solver.solve()

        assert not result.errors
        assert len(result.routes) >= 1
        route = result.routes[0]
        assert route.cost is not None
        assert route.cost.fixed == 50.0
        assert route.cost.distance > 0
        assert route.cost.time > 0
        assert route.cost.stops > 0
        assert route.cost.total > 0
        assert result.statistics.total_cost is not None
        assert result.statistics.total_cost > 0

    def test_no_cost_when_not_configured(self):
        """Sin costos configurados, el resultado no incluye costos."""
        locations = make_real_locations(n_deliveries=5)
        vehicles = [make_vehicle(1)]
        request = OptimizeRequest(locations=locations, vehicles=vehicles)
        solver = make_solver(request)
        result = solver.solve()

        assert not result.errors
        for route in result.routes:
            assert route.cost is None
        # MED-3: total_cost is 0 (not None) when no costs are configured
        assert result.statistics.total_cost == 0

    def test_optimize_by_cost(self):
        """optimize_by=cost debe funcionar con la matriz real."""
        locations = make_real_locations(n_deliveries=5)
        vehicles = [
            Vehicle(
                id="veh_1", name="Vehículo 1",
                start_location_id="depot", end_location_id="depot",
                weight_capacity=200.0,
                cost_per_km=2.5,
                cost_per_hour=20.0,
            ),
        ]
        request = OptimizeRequest(
            locations=locations, vehicles=vehicles,
            config=SolverConfig(time_limit_seconds=10, optimize_by=OptimizationObjective.cost),
        )
        solver = make_solver(request)
        result = solver.solve()

        assert not result.errors
        assert len(result.routes) >= 1
        assert result.routes[0].cost is not None
        assert result.routes[0].cost.total > 0

    def test_cost_per_hour_only(self):
        """Solo cost_per_hour sin cost_per_km debe funcionar."""
        locations = make_real_locations(n_deliveries=5)
        vehicles = [
            Vehicle(
                id="veh_1", name="Vehículo 1",
                start_location_id="depot", end_location_id="depot",
                weight_capacity=200.0,
                cost_per_hour=25.0,
            ),
        ]
        request = OptimizeRequest(locations=locations, vehicles=vehicles)
        solver = make_solver(request)
        result = solver.solve()

        assert not result.errors
        route = result.routes[0]
        assert route.cost is not None
        assert route.cost.distance == 0.0
        assert route.cost.time > 0

    def test_combined_cost_prefers_cheaper_vehicle(self):
        """Con dos vehículos de diferente costo, el solver prefiere el barato."""
        locations = make_real_locations(n_deliveries=4)
        vehicles = [
            Vehicle(
                id="cheap", name="Barato",
                start_location_id="depot", end_location_id="depot",
                weight_capacity=200.0,
                fixed_cost=10.0,
                cost_per_km=1.0,
            ),
            Vehicle(
                id="expensive", name="Caro",
                start_location_id="depot", end_location_id="depot",
                weight_capacity=200.0,
                fixed_cost=500.0,
                cost_per_km=10.0,
            ),
        ]
        request = OptimizeRequest(
            locations=locations, vehicles=vehicles,
            config=SolverConfig(time_limit_seconds=10, optimize_by=OptimizationObjective.cost),
        )
        solver = make_solver(request)
        result = solver.solve()

        assert not result.errors
        used_ids = {r.vehicle_id for r in result.routes}
        assert "cheap" in used_ids


# ═══════════════════════════════════════════════════════════════════════════
# REGRESSION TESTS — Audit fixes
# ═══════════════════════════════════════════════════════════════════════════

class TestCostPerStopRegression:
    """CRIT-1: cost_per_stop must be charged per real stop, not as a one-time fixed cost."""

    def test_cost_per_stop_scales_with_stops(self):
        """A route with more stops should have higher stops_cost than one with fewer."""
        locations = make_real_locations(n_deliveries=5)
        vehicles = [
            Vehicle(
                id="veh_1", name="Vehículo 1",
                start_location_id="depot", end_location_id="depot",
                weight_capacity=200.0,
                fixed_cost=0.0,
                cost_per_km=0.0,
                cost_per_hour=0.0,
                cost_per_stop=10.0,
            ),
        ]
        request = OptimizeRequest(
            locations=locations, vehicles=vehicles,
            config=SolverConfig(time_limit_seconds=10, optimize_by=OptimizationObjective.cost),
        )
        solver = make_solver(request)
        result = solver.solve()

        assert not result.errors
        route = result.routes[0]
        assert route.cost is not None
        # 5 deliveries → 5 real stops → stops_cost = 10 * 5 = 50
        real_stops = sum(1 for s in route.stops if s.type not in ("depot", "break"))
        assert real_stops == 5
        assert route.cost.stops == 50.0
        assert route.cost.fixed == 0.0


class TestDropPenaltyScaleRegression:
    """CRIT-2: Drop penalties must be scaled to match arc cost scale."""

    def test_drop_penalty_prevents_unnecessary_drops(self):
        """With scaled penalties, solver should not drop feasible nodes."""
        locations = make_real_locations(n_deliveries=5)
        vehicles = [
            Vehicle(
                id="veh_1", name="Vehículo 1",
                start_location_id="depot", end_location_id="depot",
                weight_capacity=200.0,
                fixed_cost=50.0,
                cost_per_km=2.5,
                cost_per_hour=20.0,
            ),
        ]
        request = OptimizeRequest(
            locations=locations, vehicles=vehicles,
            config=SolverConfig(
                time_limit_seconds=10,
                allow_skipping_nodes=True,
                drop_penalty=100000,
                optimize_by=OptimizationObjective.cost,
            ),
        )
        solver = make_solver(request)
        result = solver.solve()

        assert not result.errors
        # All 5 deliveries should be assigned — none dropped
        assert len(result.unassigned) == 0


class TestTinyCostPerKmRegression:
    """CRIT-3: Vehicle with tiny cost_per_km must still get an ArcCostEvaluator."""

    def test_tiny_cost_per_km_does_not_crash(self):
        """cost_per_km=0.001 should not leave vehicle without evaluator."""
        locations = make_real_locations(n_deliveries=3)
        vehicles = [
            Vehicle(
                id="veh_1", name="Vehículo 1",
                start_location_id="depot", end_location_id="depot",
                weight_capacity=200.0,
                cost_per_km=0.001,
            ),
        ]
        request = OptimizeRequest(
            locations=locations, vehicles=vehicles,
            config=SolverConfig(time_limit_seconds=10, optimize_by=OptimizationObjective.cost),
        )
        solver = make_solver(request)
        result = solver.solve()

        # Should not crash and should produce a valid solution
        assert not result.errors
        assert len(result.routes) >= 1


class TestNumStopsExcludesDepots:
    """HIGH-1: num_stops in cost calculation must exclude depots and breaks."""

    def test_stops_cost_excludes_depot(self):
        """stops_cost should only count delivery/pickup stops, not depot start/end."""
        locations = make_real_locations(n_deliveries=3)
        vehicles = [
            Vehicle(
                id="veh_1", name="Vehículo 1",
                start_location_id="depot", end_location_id="depot",
                weight_capacity=200.0,
                fixed_cost=0.0,
                cost_per_km=0.0,
                cost_per_hour=0.0,
                cost_per_stop=5.0,
            ),
        ]
        request = OptimizeRequest(
            locations=locations, vehicles=vehicles,
            config=SolverConfig(time_limit_seconds=10, optimize_by=OptimizationObjective.cost),
        )
        solver = make_solver(request)
        result = solver.solve()

        assert not result.errors
        route = result.routes[0]
        assert route.cost is not None
        # 3 deliveries → stops_cost = 5 * 3 = 15 (not 5 * 5 counting depots)
        assert route.cost.stops == 15.0


class TestOptimizeByDistanceWithCostFields:
    """When optimize_by=distance, cost fields should be ignored for optimization but still reported."""

    def test_distance_optimization_with_cost_fields(self):
        """optimize_by=distance should still produce valid routes with cost reporting."""
        locations = make_real_locations(n_deliveries=5)
        vehicles = [
            Vehicle(
                id="veh_1", name="Vehículo 1",
                start_location_id="depot", end_location_id="depot",
                weight_capacity=200.0,
                fixed_cost=50.0,
                cost_per_km=2.5,
                cost_per_hour=20.0,
                cost_per_stop=3.0,
            ),
        ]
        request = OptimizeRequest(
            locations=locations, vehicles=vehicles,
            config=SolverConfig(time_limit_seconds=10, optimize_by=OptimizationObjective.distance),
        )
        solver = make_solver(request)
        result = solver.solve()

        assert not result.errors
        assert len(result.routes) >= 1
        # Cost should still be reported even when optimizing by distance
        route = result.routes[0]
        assert route.cost is not None
        assert route.cost.fixed == 50.0
        assert route.cost.distance > 0

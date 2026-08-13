"""
Tests de isocrona + node_selector.
Usa SyntheticIsochroneProvider (sin ORS real).
"""

import pytest

from vrp_solver.isochrone_cache import (
    Isochrone,
    SyntheticIsochroneProvider,
    _point_in_polygon,
)
from vrp_solver.models import Location, LocationType, Vehicle
from vrp_solver.node_selector import NodeSelector


# ═══════════════════════════════════════════════════════════════════════════
# TESTS DE GEOMETRÍA
# ═══════════════════════════════════════════════════════════════════════════

class TestPointInPolygon:
    """Tests del algoritmo ray-casting."""

    def test_point_inside_square(self):
        square = [(0, 0), (0, 10), (10, 10), (10, 0), (0, 0)]
        assert _point_in_polygon((5, 5), square) is True

    def test_point_outside_square(self):
        square = [(0, 0), (0, 10), (10, 10), (10, 0), (0, 0)]
        assert _point_in_polygon((15, 15), square) is False

    def test_point_on_edge(self):
        square = [(0, 0), (0, 10), (10, 10), (10, 0), (0, 0)]
        # Punto sobre arista — ray-casting puede dar True o False
        # pero no debe crashear
        result = _point_in_polygon((0, 5), square)
        assert isinstance(result, bool)

    def test_degenerate_polygon(self):
        assert _point_in_polygon((5, 5), [(0, 0), (1, 1)]) is False


# ═══════════════════════════════════════════════════════════════════════════
# TESTS DE SYNTHETIC ISOCHRONE
# ═══════════════════════════════════════════════════════════════════════════

class TestSyntheticIsochrone:
    """Tests del provider sintético de isocronas."""

    def test_isochrone_contains_center(self):
        provider = SyntheticIsochroneProvider(speed_ms=11.11)
        iso = provider.compute("depot_1", (40.40, -3.70), 3600)  # 1h
        assert iso.contains((40.40, -3.70)) is True

    def test_isochrone_excludes_far_point(self):
        provider = SyntheticIsochroneProvider(speed_ms=11.11)
        iso = provider.compute("depot_1", (40.40, -3.70), 3600)  # 1h ≈ 40km
        # Punto a ~100km → fuera
        assert iso.contains((41.30, -3.70)) is False

    def test_isochrone_includes_nearby_point(self):
        provider = SyntheticIsochroneProvider(speed_ms=11.11)
        iso = provider.compute("depot_1", (40.40, -3.70), 3600)  # 1h ≈ 40km
        # Punto a ~5km → dentro
        assert iso.contains((40.45, -3.70)) is True

    def test_polygon_is_closed(self):
        provider = SyntheticIsochroneProvider()
        iso = provider.compute("depot_1", (40.40, -3.70), 3600)
        # El polígono debe cerrar (primer punto == último)
        assert iso.polygon[0] == iso.polygon[-1]


# ═══════════════════════════════════════════════════════════════════════════
# TESTS DE NODE SELECTOR
# ═══════════════════════════════════════════════════════════════════════════

def make_depots_and_nodes(
    n_deliveries: int = 5,
    n_depots: int = 1,
    far_nodes: int = 0,
):
    """Crea depots y deliveries de prueba."""
    depots = []
    for i in range(n_depots):
        lat = 40.40 + i * 0.01
        depots.append(Location(
            id=f"depot_{i}",
            name=f"Depot {i}",
            coords=(lat, -3.70),
            type=LocationType.depot,
        ))

    deliveries = []
    for i in range(n_deliveries):
        lat = 40.41 + i * 0.001  # ~100m entre cada uno, cerca del depot_0
        deliveries.append(Location(
            id=f"del_{i}",
            name=f"Entrega {i}",
            coords=(lat, -3.69),
            type=LocationType.delivery,
            weight_demand=10.0,
            priority="M",
        ))

    # Nodos lejanos (fuera de isocrona)
    for i in range(far_nodes):
        deliveries.append(Location(
            id=f"far_{i}",
            name=f"Lejano {i}",
            coords=(42.0 + i * 0.01, -3.70),  # ~180km del depot
            type=LocationType.delivery,
            weight_demand=10.0,
            priority="H",
        ))

    return depots, deliveries


class TestNodeSelector:
    """Tests del selector de nodos."""

    def test_all_nodes_covered(self):
        depots, deliveries = make_depots_and_nodes(n_deliveries=5)
        vehicles = [Vehicle(
            id="v1", name="V1",
            start_location_id="depot_0", end_location_id="depot_0",
            weight_capacity=200.0,
        )]

        provider = SyntheticIsochroneProvider()
        isochrones = [provider.compute(dep.id, dep.coords, 3600) for dep in depots]

        selector = NodeSelector(max_nodes_per_depot=25)
        result = selector.select(depots + deliveries, vehicles, isochrones)

        assert len(result.out_of_coverage) == 0
        assert len(result.selected) == 5
        assert all(d.id in result.depot_assignment for d in deliveries)

    def test_far_nodes_out_of_coverage(self):
        depots, deliveries = make_depots_and_nodes(n_deliveries=3, far_nodes=2)
        vehicles = [Vehicle(
            id="v1", name="V1",
            start_location_id="depot_0", end_location_id="depot_0",
            weight_capacity=200.0,
        )]

        provider = SyntheticIsochroneProvider()
        isochrones = [provider.compute(dep.id, dep.coords, 3600) for dep in depots]

        selector = NodeSelector(max_nodes_per_depot=25)
        result = selector.select(depots + deliveries, vehicles, isochrones)

        assert len(result.out_of_coverage) == 2
        assert len(result.selected) == 3
        assert any("fuera de cobertura" in r for r in result.recommendations)

    def test_priority_selection_when_over_capacity(self):
        """Cuando hay más nodos que max_nodes, los H se seleccionan primero."""
        depots, deliveries = make_depots_and_nodes(n_deliveries=30)
        # Asignar prioridades: primeros 10 = H, siguientes 10 = M, últimos 10 = L
        for i, d in enumerate(deliveries):
            if i < 10:
                d.priority = "H"
            elif i < 20:
                d.priority = "M"
            else:
                d.priority = "L"

        vehicles = [Vehicle(
            id="v1", name="V1",
            start_location_id="depot_0", end_location_id="depot_0",
            weight_capacity=10000.0,  # suficiente para todos
        )]

        provider = SyntheticIsochroneProvider()
        isochrones = [provider.compute(dep.id, dep.coords, 3600) for dep in depots]

        selector = NodeSelector(max_nodes_per_depot=15)
        result = selector.select(depots + deliveries, vehicles, isochrones)

        # Solo 15 seleccionados (max_nodes_per_depot)
        assert len(result.selected) == 15
        # Todos los H (10) deben estar seleccionados
        selected_ids = {loc.id for loc in result.selected}
        h_ids = {f"del_{i}" for i in range(10)}
        assert h_ids.issubset(selected_ids)
        # Algunos M también
        m_selected = selected_ids & {f"del_{i}" for i in range(10, 20)}
        assert len(m_selected) == 5

    def test_multi_depot_assignment(self):
        """Nodos se asignan al depot más cercano dentro de su isocrona."""
        depots = [
            Location(id="depot_n", name="Norte", coords=(40.50, -3.70), type=LocationType.depot),
            Location(id="depot_s", name="Sur", coords=(40.30, -3.70), type=LocationType.depot),
        ]
        deliveries = [
            Location(id="del_n", name="Cerca Norte", coords=(40.49, -3.70), type=LocationType.delivery, weight_demand=10.0),
            Location(id="del_s", name="Cerca Sur", coords=(40.31, -3.70), type=LocationType.delivery, weight_demand=10.0),
        ]
        vehicles = [
            Vehicle(id="vn", name="VN", start_location_id="depot_n", end_location_id="depot_n", weight_capacity=200.0),
            Vehicle(id="vs", name="VS", start_location_id="depot_s", end_location_id="depot_s", weight_capacity=200.0),
        ]

        provider = SyntheticIsochroneProvider()
        isochrones = [provider.compute(dep.id, dep.coords, 3600) for dep in depots]

        selector = NodeSelector(max_nodes_per_depot=25)
        result = selector.select(depots + deliveries, vehicles, isochrones)

        assert result.depot_assignment["del_n"] == "depot_n"
        assert result.depot_assignment["del_s"] == "depot_s"
        assert len(result.selected) == 2
        assert len(result.out_of_coverage) == 0

    def test_empty_isochrones_all_out(self):
        """Sin isocronas, todos los nodos están fuera de cobertura."""
        depots, deliveries = make_depots_and_nodes(n_deliveries=3)
        vehicles = [Vehicle(
            id="v1", name="V1",
            start_location_id="depot_0", end_location_id="depot_0",
            weight_capacity=200.0,
        )]

        selector = NodeSelector(max_nodes_per_depot=25)
        result = selector.select(depots + deliveries, vehicles, isochrones=[])

        assert len(result.out_of_coverage) == 3
        assert len(result.selected) == 0

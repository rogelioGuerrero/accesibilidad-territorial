"""
Selección de nodos para el solver.
Filtra por cobertura de isocrona, asigna nodos al depot más cercano,
y selecciona por prioridad + capacidad cuando hay más nodos que la flota puede atender.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .isochrone_cache import Isochrone
from .models import Location, LocationType, Vehicle
from .utils import haversine

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# RESULTADO
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class SelectionResult:
    """Resultado de la selección de nodos."""
    selected: list[Location] = field(default_factory=list)
    out_of_coverage: list[Location] = field(default_factory=list)
    depot_assignment: dict[str, str] = field(default_factory=dict)  # loc_id → depot_id
    recommendations: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════
# SELECTOR
# ═══════════════════════════════════════════════════════════════════════════

class NodeSelector:
    """
    Filtra nodos por isocrona y selecciona por prioridad + capacidad.
    """

    # Orden de prioridad: H > M > L > None
    PRIORITY_ORDER = {"H": 0, "M": 1, "L": 2}

    def __init__(self, max_nodes_per_depot: int = 25):
        self.max_nodes = max_nodes_per_depot

    def select(
        self,
        locations: list[Location],
        vehicles: list[Vehicle],
        isochrones: list[Isochrone],
    ) -> SelectionResult:
        """
        Filtra nodos por isocrona, asigna al depot más cercano, y selecciona
        por prioridad si excede la capacidad del día.
        """
        depots = [loc for loc in locations if loc.type == LocationType.depot]
        non_depots = [loc for loc in locations if loc.type != LocationType.depot]

        result = SelectionResult()

        # 1. Filtrar por isocrona y asignar al depot más cercano
        covered: list[tuple[Location, str, float]] = []  # (loc, depot_id, distance)

        for loc in non_depots:
            best_depot_id: str | None = None
            best_dist = float("inf")

            for iso in isochrones:
                if iso.contains(loc.coords):
                    dist = haversine(loc.coords, iso.depot_coords)
                    if dist < best_dist:
                        best_dist = dist
                        best_depot_id = iso.depot_id

            if best_depot_id is not None:
                covered.append((loc, best_depot_id, best_dist))
                result.depot_assignment[loc.id] = best_depot_id
            else:
                result.out_of_coverage.append(loc)

        if result.out_of_coverage:
            result.recommendations.append(
                f"{len(result.out_of_coverage)} nodo(s) fuera de cobertura "
                f"(ningún depot alcanza en el tiempo configurado). "
                f"Considerar depot temporal o servicio tercerizado."
            )
            for loc in result.out_of_coverage:
                result.recommendations.append(f"  - {loc.id}: {loc.name or 'sin nombre'}")

        # 2. Agrupar por depot
        by_depot: dict[str, list[Location]] = {}
        for loc, depot_id, _ in covered:
            by_depot.setdefault(depot_id, []).append(loc)

        # 3. Seleccionar por prioridad + capacidad por depot
        for depot_id, nodes in by_depot.items():
            depot_vehicles = [
                v for v in vehicles
                if v.start_location_id == depot_id
            ]

            if len(nodes) <= self.max_nodes:
                result.selected.extend(nodes)
                continue

            # Ordenar por prioridad (H primero) y luego por distancia al depot
            sorted_nodes = sorted(
                nodes,
                key=lambda n: (
                    self.PRIORITY_ORDER.get(n.priority or "L", 3),
                    haversine(n.coords, next((d.coords for d in depots if d.id == depot_id), (0, 0))),
                )
            )

            # Calcular capacidad aproximada del día
            # Nota: se usa abs() en la demanda como simplificación de pre-filtro.
            # En VRP con pickups y deliveries mezclados, la carga fluctúa durante la ruta,
            # pero para estimar capacidad máxima del día, abs() es una cota superior aceptable.
            total_weight_cap = sum(v.weight_capacity for v in depot_vehicles)
            total_volume_cap = sum(v.volume_capacity for v in depot_vehicles)

            selected_count = 0
            accum_weight = 0.0
            accum_volume = 0.0

            for node in sorted_nodes:
                if selected_count >= self.max_nodes:
                    break

                demand_w = abs(node.weight_demand)
                demand_v = abs(node.volume_demand)

                # Verificar si cabe en la capacidad restante
                if total_weight_cap > 0 and accum_weight + demand_w > total_weight_cap:
                    continue
                if total_volume_cap > 0 and accum_volume + demand_v > total_volume_cap:
                    continue

                result.selected.append(node)
                accum_weight += demand_w
                accum_volume += demand_v
                selected_count += 1

            skipped = len(nodes) - selected_count
            if skipped > 0:
                result.recommendations.append(
                    f"Depot {depot_id}: {skipped} nodo(s) pendiente(s) para otro día "
                    f"(capacidad insuficiente para {len(nodes)} nodos con {len(depot_vehicles)} vehículo(s))."
                )

        logger.info(
            "Selección: %d seleccionados, %d fuera de cobertura, %d pendientes",
            len(result.selected),
            len(result.out_of_coverage),
            len(covered) - len(result.selected),
        )

        return result


def filter_orphan_nodes(
    selection: SelectionResult,
    vehicles: list[Vehicle],
) -> tuple[list[Location], list[Vehicle], set[str]]:
    """
    Mueve nodos asignados a depots sin vehículos a out_of_coverage.
    Retorna (solver_locations_selected, solver_vehicles, selected_ids).
    """
    selected_ids = {loc.id for loc in selection.selected}
    depots_with_nodes = {selection.depot_assignment[lid] for lid in selected_ids}
    vehicle_depot_ids = {v.start_location_id for v in vehicles}
    depots_without_vehicles = depots_with_nodes - vehicle_depot_ids

    if depots_without_vehicles:
        orphan_nodes = [
            loc for loc in selection.selected
            if selection.depot_assignment.get(loc.id) in depots_without_vehicles
        ]
        for loc in orphan_nodes:
            selection.out_of_coverage.append(loc)
            selection.recommendations.append(
                f"Nodo {loc.id} asignado a depot sin vehículos: "
                f"{selection.depot_assignment[loc.id]}"
            )
        selection.selected = [
            loc for loc in selection.selected
            if selection.depot_assignment.get(loc.id) not in depots_without_vehicles
        ]
        selected_ids = {loc.id for loc in selection.selected}
        logger.warning(
            "%d nodos en depots sin vehículos movidos a out_of_coverage",
            len(orphan_nodes),
        )

    solver_vehicles = [
        v for v in vehicles
        if v.start_location_id in depots_with_nodes - depots_without_vehicles
    ]

    return selection.selected, solver_vehicles, selected_ids

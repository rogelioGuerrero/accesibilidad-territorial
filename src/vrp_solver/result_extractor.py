"""
Extracción de resultados desde la solución de OR-Tools.
Convierte el Assignment interno en RouteResponse, UnassignedNode y StatisticsResponse.
"""

from __future__ import annotations

from ortools.constraint_solver import pywrapcp

from .models import (
    CostBreakdown,
    Location,
    LocationType,
    RouteResponse,
    SolverConfig,
    StatisticsResponse,
    StopResponse,
    UnassignedNode,
)
from .utils import seconds_to_hms


class ResultExtractor:
    """Extrae rutas, nodos no asignados y estadísticas de la solución de OR-Tools."""

    def __init__(
        self,
        solution: pywrapcp.Assignment,
        builder,
        config: SolverConfig,
    ):
        self._solution = solution
        self._builder = builder
        self._manager = builder.manager
        self._routing = builder.routing
        self._locations = builder.locations
        self._vehicles = builder.vehicles
        self._matrix = builder.matrix
        self._break_nodes = builder.break_nodes
        self._dummy_indices = builder.dummy_indices
        self._n_real = builder.n_real
        self._has_time = builder.has_time
        self._has_weight = builder.has_weight
        self._has_volume = builder.has_volume
        self._config = config

    def extract_routes(self) -> list[RouteResponse]:
        """Extrae las rutas de la solución, identificando breaks."""
        routes: list[RouteResponse] = []

        time_dim = self._routing.GetDimensionOrDie("Time") if self._has_time else None
        weight_dim = self._routing.GetDimensionOrDie("Capacity_weight") if self._has_weight else None
        volume_dim = self._routing.GetDimensionOrDie("Capacity_volume") if self._has_volume else None

        break_by_node = {bn.node_idx: bn for bn in self._break_nodes}

        for veh_idx, veh in enumerate(self._vehicles):
            if not self._routing.IsVehicleUsed(self._solution, veh_idx):
                continue

            stops: list[StopResponse] = []
            route_distance = 0
            route_duration = 0
            max_weight = 0
            max_volume = 0

            start_time_val = 0
            if time_dim is not None:
                start_time_val = self._solution.Value(time_dim.CumulVar(self._routing.Start(veh_idx)))

            index = self._routing.Start(veh_idx)

            while not self._routing.IsEnd(index):
                node_idx = self._manager.IndexToNode(index)

                if node_idx in self._dummy_indices:
                    bn = break_by_node[node_idx]
                    arrival = None
                    departure = None
                    if time_dim is not None:
                        arrival_sec = self._solution.Value(time_dim.CumulVar(index))
                        departure_sec = arrival_sec + bn.duration
                        arrival = seconds_to_hms(arrival_sec)
                        departure = seconds_to_hms(departure_sec)

                    stops.append(StopResponse(
                        location_id=f"_break_{bn.vehicle_idx}",
                        name=f"Descanso ({bn.label})",
                        coords=(0.0, 0.0),
                        type="break",
                        arrival=arrival,
                        departure=departure,
                    ))
                else:
                    loc = self._locations[node_idx]

                    arrival = None
                    departure = None
                    if time_dim is not None:
                        arrival_sec = self._solution.Value(time_dim.CumulVar(index))
                        departure_sec = arrival_sec + loc.service_time
                        arrival = seconds_to_hms(arrival_sec)
                        departure = seconds_to_hms(departure_sec)

                    cum_weight = None
                    cum_volume = None
                    if weight_dim is not None:
                        cum_weight = self._solution.Value(weight_dim.CumulVar(index)) / 1000.0
                        max_weight = max(max_weight, cum_weight)
                    if volume_dim is not None:
                        cum_volume = self._solution.Value(volume_dim.CumulVar(index)) / 1000.0
                        max_volume = max(max_volume, cum_volume)

                    stops.append(StopResponse(
                        location_id=loc.id,
                        name=loc.name,
                        coords=loc.coords,
                        type=loc.type.value,
                        arrival=arrival,
                        departure=departure,
                        load_weight=loc.weight_demand,
                        load_volume=loc.volume_demand,
                        cumulative_weight=cum_weight,
                        cumulative_volume=cum_volume,
                    ))

                prev_index = index
                index = self._solution.Value(self._routing.NextVar(index))
                route_distance += self._matrix.distances[
                    self._manager.IndexToNode(prev_index)
                ][
                    self._manager.IndexToNode(index)
                ]

            if time_dim is not None:
                route_duration = self._solution.Value(time_dim.CumulVar(index)) - start_time_val

            end_node = self._manager.IndexToNode(index)
            if end_node < self._n_real:
                end_loc = self._locations[end_node]
                if time_dim is not None:
                    end_arrival = self._solution.Value(time_dim.CumulVar(index))
                    stops.append(StopResponse(
                        location_id=end_loc.id,
                        name=end_loc.name,
                        coords=end_loc.coords,
                        type=end_loc.type.value,
                        arrival=seconds_to_hms(end_arrival),
                        departure=None,
                    ))

            if stops:
                # HIGH-1: Exclude depots and breaks from stop count for cost calculation
                real_stops = sum(1 for s in stops if s.type not in ("depot", "break"))
                cost = self._compute_route_cost(veh, route_distance, route_duration, real_stops)
                routes.append(RouteResponse(
                    vehicle_id=veh.id,
                    vehicle_name=veh.name,
                    stops=stops,
                    total_distance=route_distance,
                    total_duration=route_duration,
                    total_stops=len(stops),
                    max_weight=max_weight if max_weight > 0 else None,
                    max_volume=max_volume if max_volume > 0 else None,
                    cost=cost,
                ))

        return routes

    def extract_unassigned(self, routes: list[RouteResponse] | None = None) -> list[UnassignedNode]:
        """Identifica nodos reales no asignados (excluye dummies y depósitos)."""
        if routes is not None:
            # Derivar visited de las rutas ya extraídas
            visited: set[int] = set()
            for r in routes:
                for s in r.stops:
                    if s.type not in ("break",):
                        # Buscar el índice de la location por id
                        for idx, loc in enumerate(self._locations):
                            if loc.id == s.location_id:
                                visited.add(idx)
                                break
        else:
            # Iterar la solución directamente (fallback)
            visited = set()
            for veh_idx in range(len(self._vehicles)):
                if not self._routing.IsVehicleUsed(self._solution, veh_idx):
                    continue
                index = self._routing.Start(veh_idx)
                while not self._routing.IsEnd(index):
                    node_idx = self._manager.IndexToNode(index)
                    if node_idx < self._n_real:
                        visited.add(node_idx)
                    index = self._solution.Value(self._routing.NextVar(index))

        unassigned: list[UnassignedNode] = []
        for node_idx, loc in enumerate(self._locations):
            if loc.type == LocationType.depot:
                continue
            if node_idx not in visited:
                if self._config.allow_skipping_nodes:
                    reason = "Omitido por el solver (penalización por prioridad)"
                else:
                    reason = "No asignado"
                unassigned.append(UnassignedNode(
                    id=loc.id,
                    name=loc.name,
                    reason=reason,
                ))

        return unassigned

    def compute_statistics(self, routes: list[RouteResponse] | None = None) -> StatisticsResponse:
        """Calcula estadísticas de la solución. Reutiliza rutas ya extraídas si se pasan."""
        if routes is None:
            routes = self.extract_routes()

        vehicles_used = sum(
            1 for v_idx in range(len(self._vehicles))
            if self._routing.IsVehicleUsed(self._solution, v_idx)
        )

        real_stops = 0
        for r in routes:
            for s in r.stops:
                if s.type not in ("break", "depot"):
                    real_stops += 1

        nodes_unassigned = len(self.extract_unassigned(routes))

        total_distance = sum(r.total_distance for r in routes)
        total_duration = sum(r.total_duration for r in routes)

        total_cost = sum(r.cost.total for r in routes if r.cost)

        return StatisticsResponse(
            vehicles_used=vehicles_used,
            vehicles_available=len(self._vehicles),
            nodes_assigned=real_stops,
            nodes_unassigned=nodes_unassigned,
            total_distance=total_distance,
            total_duration=total_duration,
            # MED-3: Return 0 instead of None when total cost is 0
            total_cost=total_cost if total_cost > 0 else 0,
        )

    def _compute_route_cost(self, veh, distance: float, duration: float, num_stops: int) -> CostBreakdown | None:
        """Calcula el desglose de costos para una ruta."""
        fixed = veh.fixed_cost
        dist_cost = (distance / 1000.0) * veh.cost_per_km
        time_cost = (duration / 3600.0) * veh.cost_per_hour
        stops_cost = veh.cost_per_stop * num_stops
        total = fixed + dist_cost + time_cost + stops_cost

        if total == 0:
            return None

        return CostBreakdown(
            fixed=round(fixed, 2),
            distance=round(dist_cost, 2),
            time=round(time_cost, 2),
            stops=round(stops_cost, 2),
            total=round(total, 2),
        )

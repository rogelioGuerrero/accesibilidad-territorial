"""
Construcción del modelo OR-Tools.
Crea el RoutingIndexManager, RoutingModel, y registra todas las dimensiones y restricciones.
"""

from __future__ import annotations

from ortools.constraint_solver import pywrapcp

from .breaks import BreakNode, build_break_nodes, extend_matrix
from .matrix import DistanceMatrix
from .models import (
    Location,
    LocationType,
    OptimizationObjective,
    SolverConfig,
    Vehicle,
)


class ModelBuilder:
    """Construye el modelo OR-Tools a partir de los datos del problema."""

    def __init__(
        self,
        locations: list[Location],
        vehicles: list[Vehicle],
        pairs: list,
        config: SolverConfig,
        matrix: DistanceMatrix,
    ):
        self.locations = locations
        self.vehicles = vehicles
        self.pairs = pairs
        self.config = config
        self.matrix = matrix

        # Derivables (públicos para que ResultExtractor pueda acceder sin romper encapsulamiento)
        self.location_index: dict[str, int] = {
            loc.id: i for i, loc in enumerate(locations)
        }
        self.depot_ids: list[str] = [
            loc.id for loc in locations if loc.type == LocationType.depot
        ]
        self.n_real = len(locations)
        self.break_nodes, self.dummy_indices, self.break_duration_map, self.n_total = (
            build_break_nodes(vehicles, self.n_real)
        )
        # Extender matriz para incluir nodos dummy de breaks
        self.matrix = extend_matrix(matrix, self.n_real, self.n_total)

        # Estado
        self.manager: pywrapcp.RoutingIndexManager | None = None
        self.routing: pywrapcp.RoutingModel | None = None
        self.has_time: bool = False
        self.has_weight: bool = False
        self.has_volume: bool = False
        self.has_breaks: bool = len(self.break_nodes) > 0
        self._distance_transit_idx: int | None = None

    def build(self) -> None:
        """Construye el modelo OR-Tools completo."""
        n_vehicles = len(self.vehicles)

        # Calcular has_time ANTES de las dimensiones para que _add_distance_dimension
        # pueda confiar en este valor
        self.has_time = self._has_time_constraints()
        self.has_weight = any(v.weight_capacity > 0 for v in self.vehicles)
        self.has_volume = any(v.volume_capacity > 0 for v in self.vehicles)

        # Multi-depot: cada vehículo usa su propio start/end location
        starts = [
            self.location_index[v.start_location_id]
            for v in self.vehicles
        ]
        ends = [
            self.location_index.get(v.end_location_id or v.start_location_id)
            for v in self.vehicles
        ]

        self.manager = pywrapcp.RoutingIndexManager(
            self.n_total, n_vehicles, starts, ends
        )
        self.routing = pywrapcp.RoutingModel(self.manager)

        # 1. Distancia
        self._add_distance_dimension()

        # 2. Tiempo
        if self.has_time:
            self._add_time_dimension()

        # 3. Capacidad peso
        if self.has_weight:
            self._add_capacity_dimension("weight", "weight_capacity", "weight_demand")

        # 4. Capacidad volumen
        if self.has_volume:
            self._add_capacity_dimension("volume", "volume_capacity", "volume_demand")

        # 5. Time windows
        if self.has_time:
            self._add_time_windows()

        # 6. Breaks
        if self.has_breaks:
            self._add_breaks()

        # 7. Pickup & Delivery
        if self.pairs:
            self._add_pickup_delivery()

        # 8. Skills
        if any(loc.required_skills for loc in self.locations):
            self._add_skills()

        # 9. Max duration
        if self.config.max_route_duration or any(v.max_route_duration for v in self.vehicles):
            self._add_max_duration()

        # 10. Max distance
        if self.config.max_distance or any(v.max_distance for v in self.vehicles):
            self._add_max_distance()

        # 11. Max tasks
        if any(v.max_tasks for v in self.vehicles):
            self._add_max_tasks()

        # 12. Drop penalties
        if self.config.allow_skipping_nodes:
            self._add_drop_penalties()

        # 13. Costos fijos (siempre) y variables por vehículo (solo con objetivo cost)
        self._add_fixed_costs()
        if self.config.optimize_by == OptimizationObjective.cost:
            self._add_costs()

        # 14. Objetivo (cost evaluator para vehículos sin cost_per_km)
        self._set_objective()

    def _has_time_constraints(self) -> bool:
        return any(
            loc.time_windows or loc.service_time > 0
            for loc in self.locations
        ) or any(
            v.start_time or v.end_time or v.breaks or v.max_route_duration
            or (v.cost_per_hour or 0) > 0
            for v in self.vehicles
        ) or self.config.max_route_duration is not None

    def _add_distance_dimension(self) -> None:
        def distance_callback(from_idx: int, to_idx: int) -> int:
            from_node = self.manager.IndexToNode(from_idx)
            to_node = self.manager.IndexToNode(to_idx)
            return self.matrix.distances[from_node][to_node]

        transit_idx = self.routing.RegisterTransitCallback(distance_callback)
        self._distance_transit_idx = transit_idx

        max_distance = self.config.max_distance or 3_000_000
        self.routing.AddDimension(
            transit_idx,
            0,
            max_distance,
            True,
            "Distance",
        )

    def _set_objective(self) -> None:
        """Configura el ArcCostEvaluator según el objetivo de optimización.

        Cuando optimize_by=cost, _add_costs ya registró callbacks para vehicles con cost fields.
        Aquí solo se asigna el callback de distancia a vehículos sin cost fields.
        Para otros modos (distance/duration), se asigna a TODOS los vehículos.
        """
        # CRIT-3: Detect vehicles whose cost fields rounded to zero in _add_costs.
        # These vehicles have cost_per_km/cost_per_hour > 0 but the scaled value rounded to 0,
        # so _add_costs skipped them. They need a fallback evaluator.
        def _scaled_cost_is_zero(v: Vehicle) -> bool:
            cp_m = int(round(v.cost_per_km * 100000 / 1000)) if v.cost_per_km else 0
            cp_s = int(round(v.cost_per_hour * 100000 / 3600)) if v.cost_per_hour else 0
            return cp_m == 0 and cp_s == 0

        vehicles_without_cost = [
            v_idx for v_idx, v in enumerate(self.vehicles)
            if (not v.cost_per_km and not v.cost_per_hour)
            or (self.config.optimize_by == OptimizationObjective.cost and _scaled_cost_is_zero(v))
        ]

        if self.config.optimize_by == OptimizationObjective.cost:
            # Sin costos definidos (o que redondearon a 0): optimizar por distancia como proxy
            for v_idx in vehicles_without_cost:
                self.routing.SetArcCostEvaluatorOfVehicle(self._distance_transit_idx, v_idx)
            return

        # Para optimización por distancia o duración, aplicar a TODOS los vehículos
        # (incluyendo los que tienen cost_per_km, ya que _add_costs no se llamó)
        if self.config.optimize_by == OptimizationObjective.duration:
            if self.has_time:
                # _add_time_dimension already called SetArcCostEvaluatorOfAllVehicles
                pass
            else:
                def time_cost_callback(from_idx: int, to_idx: int) -> int:
                    from_node = self.manager.IndexToNode(from_idx)
                    to_node = self.manager.IndexToNode(to_idx)
                    if from_node in self.dummy_indices:
                        return self.break_duration_map.get(from_node, 0)
                    travel = self.matrix.durations[from_node][to_node]
                    service = self.locations[from_node].service_time
                    return travel + service
                time_idx = self.routing.RegisterTransitCallback(time_cost_callback)
                for v_idx in range(len(self.vehicles)):
                    self.routing.SetArcCostEvaluatorOfVehicle(time_idx, v_idx)
        else:
            # Optimizar por distancia — todos los vehículos
            for v_idx in range(len(self.vehicles)):
                self.routing.SetArcCostEvaluatorOfVehicle(self._distance_transit_idx, v_idx)

    def _add_time_dimension(self) -> None:
        def time_callback(from_idx: int, to_idx: int) -> int:
            from_node = self.manager.IndexToNode(from_idx)
            to_node = self.manager.IndexToNode(to_idx)
            if from_node in self.dummy_indices:
                return self.break_duration_map.get(from_node, 0)
            travel = self.matrix.durations[from_node][to_node]
            service = self.locations[from_node].service_time
            return travel + service

        transit_idx = self.routing.RegisterTransitCallback(time_callback)

        if self.config.optimize_by == OptimizationObjective.duration:
            self.routing.SetArcCostEvaluatorOfAllVehicles(transit_idx)

        max_time = self.config.max_route_duration or 86400
        # HIGH-3: If time_dim exists only for cost_per_hour reporting (no real time constraints),
        # use a very large capacity to avoid imposing an unintended 24h route limit.
        if not any(loc.time_windows for loc in self.locations) and \
           not any(v.start_time or v.end_time or v.breaks or v.max_route_duration for v in self.vehicles) and \
           not self.config.max_route_duration:
            max_time = 2_000_000_000
        self.routing.AddDimension(
            transit_idx,
            max_time,
            max_time,
            False,
            "Time",
        )

    def _add_capacity_dimension(self, name: str, capacity_attr: str, demand_attr: str) -> None:
        SCALE = 1000  # escalar a enteros para preservar precisión decimal

        def demand_callback(from_idx: int) -> int:
            from_node = self.manager.IndexToNode(from_idx)
            if from_node in self.dummy_indices:
                return 0
            loc = self.locations[from_node]
            demand = getattr(loc, demand_attr, 0.0)
            return int(round(demand * SCALE))

        callback_idx = self.routing.RegisterUnaryTransitCallback(demand_callback)
        self.routing.AddDimensionWithVehicleCapacity(
            callback_idx,
            0,
            [int(round(getattr(v, capacity_attr) * SCALE)) for v in self.vehicles],
            True,
            f"Capacity_{name}",
        )

    def _add_time_windows(self) -> None:
        time_dim = self.routing.GetDimensionOrDie("Time")
        max_time = self.config.max_route_duration or 86400

        for node_idx, loc in enumerate(self.locations):
            index = self.manager.NodeToIndex(node_idx)
            if loc.time_windows:
                # Usar la unión de todas las ventanas de tiempo del nodo
                # OR-Tools soporta una sola CumulVar por nodo, así que usamos
                # el rango más amplio (start mínimo, end máximo) y dejamos que
                # el solver encuentre el mejor slot dentro de ese rango
                earliest_start = min(tw.start for tw in loc.time_windows)
                latest_end = max(tw.end for tw in loc.time_windows)
                if self.config.soft_time_windows:
                    time_dim.CumulVar(index).SetRange(earliest_start, max_time)
                    try:
                        time_dim.SetCumulVarSoftUpperBound(index, latest_end, self.config.late_arrival_penalty)
                    except Exception:
                        time_dim.CumulVar(index).SetRange(earliest_start, latest_end)
                else:
                    time_dim.CumulVar(index).SetRange(earliest_start, latest_end)
            elif loc.type == LocationType.depot:
                time_dim.CumulVar(index).SetRange(0, max_time)

        for veh_idx, veh in enumerate(self.vehicles):
            start_idx = self.routing.Start(veh_idx)
            end_idx = self.routing.End(veh_idx)
            if veh.start_time is not None:
                time_dim.CumulVar(start_idx).SetRange(veh.start_time, veh.start_time)
            if veh.end_time is not None:
                time_dim.CumulVar(end_idx).SetRange(0, veh.end_time)

    def _add_breaks(self) -> None:
        time_dim = self.routing.GetDimensionOrDie("Time")
        for bn in self.break_nodes:
            index = self.manager.NodeToIndex(bn.node_idx)
            self.routing.solver().Add(
                self.routing.VehicleVar(index) == bn.vehicle_idx
            )
            time_dim.CumulVar(index).SetRange(bn.earliest, bn.latest)

    def _add_pickup_delivery(self) -> None:
        time_dim = None
        if self.has_time:
            time_dim = self.routing.GetDimensionOrDie("Time")

        for pair in self.pairs:
            pickup_idx = self.location_index.get(pair.pickup_id)
            delivery_idx = self.location_index.get(pair.delivery_id)
            if pickup_idx is None or delivery_idx is None:
                continue

            pickup_node = self.manager.NodeToIndex(pickup_idx)
            delivery_node = self.manager.NodeToIndex(delivery_idx)

            self.routing.AddPickupAndDelivery(pickup_node, delivery_node)
            self.routing.solver().Add(
                self.routing.VehicleVar(pickup_node) == self.routing.VehicleVar(delivery_node)
            )
            if time_dim is not None:
                self.routing.solver().Add(
                    time_dim.CumulVar(pickup_node) <= time_dim.CumulVar(delivery_node)
                )

    def _add_skills(self) -> None:
        for node_idx, loc in enumerate(self.locations):
            if not loc.required_skills:
                continue
            index = self.manager.NodeToIndex(node_idx)
            required = set(loc.required_skills)
            allowed_vehicles = [
                v_idx for v_idx, veh in enumerate(self.vehicles)
                if required.issubset(set(veh.skills or []))
            ]
            if allowed_vehicles:
                # Workaround: SetAllowedVehiclesForIndex tiene un bug de SWIG en OR-Tools 9.15.6755
                # (TypeError: argument 2 of type 'absl::Span< int const >')
                # Usar restricciones de VehicleVar directamente.
                # TODO: Reintentar SetAllowedVehiclesForIndex al actualizar a OR-Tools >=9.16
                for v_idx in range(len(self.vehicles)):
                    if v_idx not in allowed_vehicles:
                        self.routing.solver().Add(
                            self.routing.VehicleVar(index) != v_idx
                        )
            else:
                # Ningún vehículo tiene las skills: permitir omisión y forzarla
                self.routing.AddDisjunction([index], 0)
                self.routing.solver().Add(
                    self.routing.VehicleVar(index) == -1
                )

    def _add_max_duration(self) -> None:
        time_dim = self.routing.GetDimensionOrDie("Time")
        for veh_idx, veh in enumerate(self.vehicles):
            max_dur = veh.max_route_duration or self.config.max_route_duration
            if max_dur is not None:
                time_dim.SetSpanUpperBoundForVehicle(max_dur, veh_idx)

    def _add_max_distance(self) -> None:
        dist_dim = self.routing.GetDimensionOrDie("Distance")
        for veh_idx, veh in enumerate(self.vehicles):
            max_dist = veh.max_distance or self.config.max_distance
            if max_dist is not None:
                dist_dim.SetSpanUpperBoundForVehicle(max_dist, veh_idx)

    def _add_max_tasks(self) -> None:
        def task_callback(from_idx: int) -> int:
            from_node = self.manager.IndexToNode(from_idx)
            if from_node in self.dummy_indices:
                return 0
            loc = self.locations[from_node]
            return 0 if loc.type == LocationType.depot else 1

        callback_idx = self.routing.RegisterUnaryTransitCallback(task_callback)
        self.routing.AddDimension(
            callback_idx,
            0,
            max(v.max_tasks for v in self.vehicles if v.max_tasks) or 1000,
            True,
            "Tasks",
        )
        tasks_dim = self.routing.GetDimensionOrDie("Tasks")
        for veh_idx, veh in enumerate(self.vehicles):
            if veh.max_tasks is not None:
                tasks_dim.SetSpanUpperBoundForVehicle(veh.max_tasks, veh_idx)

    def _add_drop_penalties(self) -> None:
        # CRIT-2: Scale drop penalties to match arc cost scale (×100000).
        # Without scaling, penalties are negligible vs arc costs and solver drops nodes unnecessarily.
        SCALE = 100000
        base_penalty = self.config.drop_penalty * SCALE
        priority_penalties = {
            "H": base_penalty * 10,
            "M": base_penalty,
            "L": max(1, base_penalty // 10),
        }
        for node_idx, loc in enumerate(self.locations):
            if loc.type == LocationType.depot:
                continue
            index = self.manager.NodeToIndex(node_idx)
            penalty = priority_penalties.get(loc.priority, base_penalty)
            self.routing.AddDisjunction([index], penalty)

    def _add_fixed_costs(self) -> None:
        """Registra el fixed_cost de cada vehículo (aplica con cualquier objetivo)."""
        SCALE = 100000
        for veh_idx, veh in enumerate(self.vehicles):
            fixed = int(veh.fixed_cost) * SCALE
            if fixed > 0:
                self.routing.SetFixedCostOfVehicle(fixed, veh_idx)

    def _add_costs(self) -> None:
        SCALE = 100000
        # MED-2: Capture required attrs as locals to avoid self references in closures
        manager = self.manager
        matrix = self.matrix
        locations = self.locations
        dummy_indices = self.dummy_indices
        break_duration_map = self.break_duration_map
        n_real = self.n_real

        for veh_idx, veh in enumerate(self.vehicles):
            # cost_per_stop is added to the arc cost for edges arriving at real stops.
            has_distance_cost = veh.cost_per_km > 0
            has_time_cost = veh.cost_per_hour > 0
            cost_per_stop_scaled = int(veh.cost_per_stop) * SCALE

            if has_distance_cost and has_time_cost:
                # Costo combinado: distancia + tiempo + parada
                cost_per_m = int(round(veh.cost_per_km * 100000 / 1000))
                cost_per_s = int(round(veh.cost_per_hour * 100000 / 3600))

                def make_combined_cost(cp_dist: int, cp_time: int, cp_stop: int,
                                       mgr, mtx, locs, dummies, bdm, n_r):
                    def cost_callback(from_idx: int, to_idx: int) -> int:
                        from_node = mgr.IndexToNode(from_idx)
                        to_node = mgr.IndexToNode(to_idx)
                        if from_node in dummies:
                            return bdm.get(from_node, 0) * cp_time
                        travel_dist = mtx.distances[from_node][to_node]
                        travel_time = mtx.durations[from_node][to_node]
                        service = locs[from_node].service_time
                        stop_cost = cp_stop if (to_node < n_r and locs[to_node].type != LocationType.depot) else 0
                        return travel_dist * cp_dist + (travel_time + service) * cp_time + stop_cost
                    return cost_callback

                cost_idx = self.routing.RegisterTransitCallback(
                    make_combined_cost(cost_per_m, cost_per_s, cost_per_stop_scaled,
                                       manager, matrix, locations, dummy_indices, break_duration_map, n_real)
                )
                self.routing.SetArcCostEvaluatorOfVehicle(cost_idx, veh_idx)
            elif has_distance_cost:
                cost_per_m = int(round(veh.cost_per_km * 100000 / 1000))
                if cost_per_m > 0:
                    def make_cost_callback(cp: int, cp_stop: int,
                                           mgr, mtx, locs, dummies, n_r):
                        def cost_callback(from_idx: int, to_idx: int) -> int:
                            from_node = mgr.IndexToNode(from_idx)
                            to_node = mgr.IndexToNode(to_idx)
                            stop_cost = cp_stop if (to_node < n_r and locs[to_node].type != LocationType.depot) else 0
                            return mtx.distances[from_node][to_node] * cp + stop_cost
                        return cost_callback
                    cost_idx = self.routing.RegisterTransitCallback(
                        make_cost_callback(cost_per_m, cost_per_stop_scaled,
                                           manager, matrix, locations, dummy_indices, n_real)
                    )
                    self.routing.SetArcCostEvaluatorOfVehicle(cost_idx, veh_idx)
            elif has_time_cost:
                # MED-1: Guard against cost_per_s rounding to 0
                cost_per_s = int(round(veh.cost_per_hour * 100000 / 3600))
                if cost_per_s > 0:
                    def make_time_cost_callback(cp: int, cp_stop: int,
                                                mgr, mtx, locs, dummies, bdm, n_r):
                        def cost_callback(from_idx: int, to_idx: int) -> int:
                            from_node = mgr.IndexToNode(from_idx)
                            to_node = mgr.IndexToNode(to_idx)
                            if from_node in dummies:
                                return bdm.get(from_node, 0) * cp
                            travel = mtx.durations[from_node][to_node]
                            service = locs[from_node].service_time
                            stop_cost = cp_stop if (to_node < n_r and locs[to_node].type != LocationType.depot) else 0
                            return (travel + service) * cp + stop_cost
                        return cost_callback

                    cost_idx = self.routing.RegisterTransitCallback(
                        make_time_cost_callback(cost_per_s, cost_per_stop_scaled,
                                                manager, matrix, locations, dummy_indices, break_duration_map, n_real)
                    )
                    self.routing.SetArcCostEvaluatorOfVehicle(cost_idx, veh_idx)

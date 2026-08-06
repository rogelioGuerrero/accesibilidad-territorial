"""
Motor VRP con OR-Tools.
Orquesta la construcción del modelo, resolución y extracción de resultados.
"""

from __future__ import annotations

import copy
import time
import logging
from dataclasses import dataclass, field
from typing import Optional

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from .breaks import build_break_nodes, extend_matrix
from .matrix import DistanceMatrix, get_matrix_provider
from .model_builder import ModelBuilder
from .models import (
    Location,
    LocationType,
    OptimizeRequest,
    RouteResponse,
    SolverConfig,
    StatisticsResponse,
    UnassignedNode,
    ValidationError,
    ValidationErrorCode,
    Vehicle,
)
from .result_extractor import ResultExtractor

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# RESULTADO INTERNO
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class SolverResult:
    routes: list[RouteResponse] = field(default_factory=list)
    unassigned: list[UnassignedNode] = field(default_factory=list)
    statistics: Optional[StatisticsResponse] = None
    solver_time: float = 0.0
    warnings: list[str] = field(default_factory=list)
    errors: list[ValidationError] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════
# SOLVER
# ═══════════════════════════════════════════════════════════════════════════

class VRPSolver:
    """Orquestador del solver VRP. Acepta datos planos, no modelos de API."""

    def __init__(
        self,
        locations: list[Location],
        vehicles: list[Vehicle],
        config: SolverConfig | None = None,
        pairs: list | None = None,
        matrix_provider: str = "synthetic",
        matrix_path: str | None = None,
    ):
        self.locations = locations
        self.vehicles = vehicles
        self.config = copy.deepcopy(config) if config else SolverConfig()
        self.pairs = pairs or []
        self._matrix_provider = matrix_provider
        self._matrix_path = matrix_path

        # Derivables
        self._location_index: dict[str, int] = {
            loc.id: i for i, loc in enumerate(locations)
        }
        self._depot_ids: list[str] = [
            loc.id for loc in locations if loc.type == LocationType.depot
        ]

        # Lazy: la matriz se computa en solve()
        self.matrix: Optional[DistanceMatrix] = None
        self._builder: Optional[ModelBuilder] = None
        self._solution: Optional[pywrapcp.Assignment] = None

    @property
    def builder(self) -> ModelBuilder | None:
        return self._builder

    @classmethod
    def from_request(
        cls,
        request: OptimizeRequest,
        matrix_provider: str = "synthetic",
        matrix_path: str | None = None,
    ) -> VRPSolver:
        """Factory method para construir desde un OptimizeRequest (compatibilidad API)."""
        return cls(
            locations=request.locations,
            vehicles=request.vehicles,
            config=request.config,
            pairs=request.pickups_deliveries or [],
            matrix_provider=matrix_provider,
            matrix_path=matrix_path,
        )

    def _compute_matrix(self) -> DistanceMatrix:
        """Computa la matriz de distancias (lazy)."""
        coords = [loc.coords for loc in self.locations]
        kwargs = {}
        if self._matrix_path:
            kwargs["matrix_path"] = self._matrix_path
        provider = get_matrix_provider(self._matrix_provider, **kwargs)
        base_matrix = provider.compute(coords)
        return base_matrix

    def _create_builder(self) -> ModelBuilder:
        return ModelBuilder(
            locations=self.locations,
            vehicles=self.vehicles,
            pairs=self.pairs,
            config=self.config,
            matrix=self.matrix,
        )

    # ─────────────────────────────────────────────────────────────────────
    # RESOLUCIÓN
    # ─────────────────────────────────────────────────────────────────────

    def _diagnose_infeasibility(self) -> list[str]:
        diagnoses: list[str] = []

        total_demand = sum(
            loc.weight_demand for loc in self.locations if loc.type != LocationType.depot
        )
        total_capacity = sum(v.weight_capacity for v in self.vehicles)
        if total_capacity > 0 and abs(total_demand) > total_capacity:
            diagnoses.append(
                f"Capacidad de peso insuficiente: demanda total={abs(total_demand)}, "
                f"capacidad total={total_capacity}"
            )

        total_volume_demand = sum(
            loc.volume_demand for loc in self.locations if loc.type != LocationType.depot
        )
        total_volume_capacity = sum(v.volume_capacity for v in self.vehicles)
        if total_volume_capacity > 0 and abs(total_volume_demand) > total_volume_capacity:
            diagnoses.append(
                f"Capacidad de volumen insuficiente: demanda total={abs(total_volume_demand)}, "
                f"capacidad total={total_volume_capacity}"
            )

        if self._builder and self._builder.has_time:
            for loc in self.locations:
                if not loc.time_windows or loc.type == LocationType.depot:
                    continue
                # Usar la unión de todas las ventanas: si no cabe en la más amplia, es infactible
                earliest_start = min(tw.start for tw in loc.time_windows)
                latest_end = max(tw.end for tw in loc.time_windows)
                loc_idx = self._location_index.get(loc.id)
                if loc_idx is None:
                    continue
                # Considerar el depósito más cercano al nodo
                min_travel = min(
                    self.matrix.durations[self._location_index[did]][loc_idx]
                    for did in self._depot_ids
                    if did in self._location_index
                )
                veh_start = min((v.start_time or 0) for v in self.vehicles)
                earliest_arrival = veh_start + min_travel
                if earliest_arrival > latest_end:
                    diagnoses.append(
                        f"TW imposible para {loc.id}: llegada más temprana={earliest_arrival}s "
                        f"> fin de ventana={latest_end}s"
                    )

        for veh in self.vehicles:
            if veh.start_time is not None and veh.end_time is not None:
                if veh.end_time <= veh.start_time:
                    diagnoses.append(
                        f"Vehículo {veh.id}: horario inválido ({veh.start_time}-{veh.end_time})"
                    )

        for loc in self.locations:
            if not loc.required_skills:
                continue
            compatible = any(
                set(loc.required_skills).issubset(set(v.skills or []))
                for v in self.vehicles
            )
            if not compatible:
                diagnoses.append(
                    f"Nodo {loc.id} requiere skills {loc.required_skills} "
                    f"que ningún vehículo tiene"
                )

        if not diagnoses:
            diagnoses.append(
                "No se pudo identificar causa específica — puede ser combinación de restricciones"
            )
        return diagnoses

    def solve(self) -> SolverResult:
        start_time = time.time()
        result = SolverResult()

        logger.info("Iniciando solver: %d locations, %d vehicles", len(self.locations), len(self.vehicles))

        # Computar matriz lazy
        try:
            self.matrix = self._compute_matrix()
        except RuntimeError as e:
            logger.error("Error computando matriz: %s", e)
            result.errors.append(ValidationError(
                code=ValidationErrorCode.SOLVER_ERROR,
                message=f"Error al obtener la matriz de distancias: {e}",
            ))
            return result

        try:
            self._builder = self._create_builder()
            self._builder.build()
        except Exception as e:
            logger.exception("Error construyendo modelo")
            result.errors.append(ValidationError(
                code=ValidationErrorCode.SOLVER_ERROR,
                message=f"Error al construir el modelo: {e}",
            ))
            return result

        search_params = pywrapcp.DefaultRoutingSearchParameters()
        search_params.first_solution_strategy = (
            getattr(routing_enums_pb2.FirstSolutionStrategy, self.config.first_solution_strategy)
        )
        search_params.local_search_metaheuristic = (
            getattr(routing_enums_pb2.LocalSearchMetaheuristic, self.config.local_search_metaheuristic)
        )
        search_params.time_limit.seconds = self.config.time_limit_seconds
        search_params.log_search = False

        self._solution = self._builder.routing.SolveWithParameters(search_params)

        if self._solution is None:
            diagnoses = self._diagnose_infeasibility()
            for d in diagnoses:
                result.warnings.append(f"Infactibilidad: {d}")
            logger.warning("Solver infactible: %s", "; ".join(diagnoses))

            if (self.config.auto_retry_with_skipping
                    and not self.config.allow_skipping_nodes):
                result.warnings.append("Reintentando con allow_skipping_nodes=True...")
                self.config.allow_skipping_nodes = True
                logger.info("Auto-retry con skipping activado")

                try:
                    self._builder = self._create_builder()
                    self._builder.build()
                except Exception as e:
                    result.errors.append(ValidationError(
                        code=ValidationErrorCode.SOLVER_ERROR,
                        message=f"Error al reconstruir el modelo: {e}",
                    ))
                    result.solver_time = time.time() - start_time
                    return result

                self._solution = self._builder.routing.SolveWithParameters(search_params)

                if self._solution is None:
                    result.errors.append(ValidationError(
                        code=ValidationErrorCode.SOLVER_INFEASIBLE,
                        message="El solver no encontró solución factible incluso con nodos omitibles",
                        details={"diagnoses": diagnoses},
                    ))
                    result.solver_time = time.time() - start_time
                    return result
            else:
                result.errors.append(ValidationError(
                    code=ValidationErrorCode.SOLVER_INFEASIBLE,
                    message="El solver no encontró solución factible",
                    details={"diagnoses": diagnoses},
                ))
                result.solver_time = time.time() - start_time
                return result

        extractor = ResultExtractor(
            solution=self._solution,
            builder=self._builder,
            config=self.config,
        )

        result.routes = extractor.extract_routes()
        result.unassigned = extractor.extract_unassigned(result.routes)
        result.statistics = extractor.compute_statistics(result.routes)
        result.solver_time = time.time() - start_time

        logger.info("Solver completado: %d rutas, %d no asignados, %.2fs",
                     len(result.routes), len(result.unassigned), result.solver_time)

        if result.unassigned:
            result.warnings.append(f"{len(result.unassigned)} nodo(s) no asignado(s)")

        return result

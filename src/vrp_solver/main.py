"""
FastAPI app — Endpoint /optimize para el solver VRP.
Documentación interactiva en /docs (Swagger) y /redoc.
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .isochrone_cache import get_isochrone_provider
from .models import (
    LocationType,
    OptimizeRequest,
    OptimizeResponse,
    SolverStatus,
    UnassignedNode,
    ValidationError,
    ValidationErrorCode,
)
from .demo import router as demo_router
from .node_selector import NodeSelector, filter_orphan_nodes
from .solver import VRPSolver
from .validator import validate_request

load_dotenv()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="VRP Solver",
    description="Motor de optimización de rutas con OR-Tools",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(demo_router)

# Configuración
ISOCHRONE_RANGE_S = int(os.getenv("ISOCHRONE_RANGE_SECONDS", "3600"))  # 1h default
MAX_NODES_PER_DEPOT = int(os.getenv("MAX_NODES_PER_DEPOT", "25"))


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "solver": "ortools"}


@app.post("/optimize", response_model=OptimizeResponse)
def optimize(request: OptimizeRequest) -> OptimizeResponse:
    """
    Recibe locations + vehicles + config y devuelve rutas optimizadas.
    Flujo: validar → filtrar por isocrona → seleccionar por prioridad → solver.
    """
    matrix_provider = os.getenv("MATRIX_PROVIDER", "synthetic")
    isochrone_provider_name = os.getenv("ISOCHRONE_PROVIDER", "synthetic")
    logger.info("Request recibido: %d locations, %d vehicles", len(request.locations), len(request.vehicles))

    # 1. Validación
    validation = validate_request(request)
    if not validation.is_valid:
        logger.warning("Validación falló: %d errores", len(validation.errors))
        return OptimizeResponse(
            status=SolverStatus.error,
            message="Dataset inválido — no se procesó",
            errors=validation.errors,
            warnings=validation.warnings,
        )

    # 2. Filtrar por isocrona y seleccionar nodos
    depots = [loc for loc in request.locations if loc.type == LocationType.depot]
    try:
        iso_provider = get_isochrone_provider(isochrone_provider_name)
        isochrones = [
            iso_provider.compute(dep.id, dep.coords, ISOCHRONE_RANGE_S)
            for dep in depots
        ]
    except RuntimeError as e:
        logger.error("Error computando isocronas: %s", e)
        return OptimizeResponse(
            status=SolverStatus.error,
            message="Error al obtener isocronas de cobertura",
            errors=[ValidationError(
                code=ValidationErrorCode.SOLVER_ERROR,
                message=str(e),
            )],
        )

    selector = NodeSelector(max_nodes_per_depot=MAX_NODES_PER_DEPOT)
    selection = selector.select(request.locations, request.vehicles, isochrones)

    # 3. Construir subset para el solver
    selected_locs, solver_vehicles, selected_ids = filter_orphan_nodes(
        selection, request.vehicles
    )
    solver_locations = depots + selected_locs

    # Filtrar pickup-delivery pairs: solo los que están en el subset
    solver_pairs = []
    if request.pickups_deliveries:
        for pair in request.pickups_deliveries:
            if pair.pickup_id in selected_ids and pair.delivery_id in selected_ids:
                solver_pairs.append(pair)

    if not solver_vehicles:
        return OptimizeResponse(
            status=SolverStatus.error,
            message="No hay vehículos asignados a los depots con nodos seleccionados",
            warnings=validation.warnings,
        )

    logger.info(
        "Solver: %d locations (%d fuera de cobertura), %d vehicles, %d pairs",
        len(solver_locations),
        len(selection.out_of_coverage),
        len(solver_vehicles),
        len(solver_pairs),
    )

    # 4. Solver con el subset
    try:
        solver = VRPSolver(
            locations=solver_locations,
            vehicles=solver_vehicles,
            config=request.config,
            pairs=solver_pairs,
            matrix_provider=matrix_provider,
        )
        result = solver.solve()
    except RuntimeError as e:
        logger.error("Error de proveedor de matriz: %s", e)
        return OptimizeResponse(
            status=SolverStatus.error,
            message="Error al obtener la matriz de distancias",
            errors=[ValidationError(
                code=ValidationErrorCode.SOLVER_ERROR,
                message=str(e),
            )],
        )

    # 5. Construir respuesta
    out_of_coverage_nodes = [
        UnassignedNode(id=loc.id, name=loc.name, reason="Fuera de cobertura (isocrona)")
        for loc in selection.out_of_coverage
    ]

    if result.errors:
        return OptimizeResponse(
            status=SolverStatus.error,
            message="El solver no pudo procesar la solicitud",
            errors=result.errors,
            out_of_coverage=out_of_coverage_nodes,
            recommendations=selection.recommendations,
            solver_time_seconds=result.solver_time,
        )

    return OptimizeResponse(
        status=SolverStatus.success,
        message="Optimización completada",
        routes=result.routes,
        statistics=result.statistics,
        unassigned_nodes=result.unassigned,
        out_of_coverage=out_of_coverage_nodes,
        recommendations=selection.recommendations,
        warnings=result.warnings + validation.warnings,
        solver_time_seconds=result.solver_time,
    )

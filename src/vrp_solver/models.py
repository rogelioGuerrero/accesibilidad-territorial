"""
Modelos Pydantic para la API VRP.
Define el contrato de entrada (request) y salida (response).
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ═══════════════════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════════════════

class LocationType(str, Enum):
    depot = "depot"
    pickup = "pickup"
    delivery = "delivery"
    service = "service"


class SolverStatus(str, Enum):
    success = "success"
    error = "error"


class ValidationErrorCode(str, Enum):
    """Códigos de error para que el frontend pueda reaccionar programáticamente."""
    NO_DEPOT = "NO_DEPOT"
    VEHICLE_REF_INVALID = "VEHICLE_REF_INVALID"
    CAPACITY_INSUFFICIENT = "CAPACITY_INSUFFICIENT"
    DEMAND_EXCEEDS_VEHICLE = "DEMAND_EXCEEDS_VEHICLE"
    SKILLS_NO_MATCH = "SKILLS_NO_MATCH"
    VEHICLE_SCHEDULE_INVALID = "VEHICLE_SCHEDULE_INVALID"
    TIME_WINDOW_INVALID = "TIME_WINDOW_INVALID"
    PICKUP_DELIVERY_REF_INVALID = "PICKUP_DELIVERY_REF_INVALID"
    SOLVER_INFEASIBLE = "SOLVER_INFEASIBLE"
    SOLVER_ERROR = "SOLVER_ERROR"


class ValidationError(BaseModel):
    """Error estructurado para el frontend."""
    code: ValidationErrorCode
    message: str = Field(description="Mensaje humano, listo para mostrar al usuario")
    details: Optional[dict] = Field(None, description="Datos adicionales contextuales")


# ═══════════════════════════════════════════════════════════════════════════
# REQUEST MODELS
# ═══════════════════════════════════════════════════════════════════════════

class TimeWindow(BaseModel):
    """Ventana de tiempo en segundos desde medianoche."""
    start: int = Field(ge=0, description="Segundos desde medianoche (ej: 28800 = 08:00)")
    end: int = Field(ge=0, description="Segundos desde medianoche (ej: 64800 = 18:00)")

    @field_validator("end")
    @classmethod
    def end_after_start(cls, v: int, info) -> int:
        start = info.data.get("start")
        if start is not None and v < start:
            raise ValueError(f"end ({v}) debe ser >= start ({start})")
        return v


class VehicleBreak(BaseModel):
    """Descanso programado para un vehículo."""
    duration: int = Field(gt=0, description="Duración del descanso en segundos")
    earliest_start: Optional[int] = Field(None, ge=0, description="Tiempo más temprano para iniciar (seg desde medianoche)")
    latest_start: Optional[int] = Field(None, ge=0, description="Tiempo más tardío para iniciar (seg desde medianoche)")
    time_windows: Optional[list[TimeWindow]] = Field(None, description="Ventanas de tiempo permitidas para el descanso")


class Location(BaseModel):
    """Ubicación en el problema VRP."""
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(description="Identificador único")
    name: Optional[str] = Field(None, description="Nombre descriptivo")
    coords: tuple[float, float] = Field(description="[lat, lng] — orden backend")
    type: LocationType = Field(default=LocationType.delivery)
    external_id: Optional[str] = Field(None, description="ID del sistema externo/cliente")
    service_time: int = Field(default=0, ge=0, description="Tiempo de servicio en segundos")
    time_windows: Optional[list[TimeWindow]] = Field(None, description="Ventanas de tiempo permitidas")
    weight_demand: float = Field(default=0.0, description="Demanda de peso (negativo para entregas, positivo para recogidas)")
    volume_demand: float = Field(default=0.0, description="Demanda de volumen", alias="volumeDemand")
    required_skills: Optional[list[str]] = Field(None, description="Skills requeridas para atender este nodo")
    priority: Optional[str] = Field(None, description="Prioridad: H (alta), M (media), L (baja)")

    @field_validator("coords")
    @classmethod
    def validate_coords(cls, v: tuple[float, float]) -> tuple[float, float]:
        lat, lng = v
        if not (-90 <= lat <= 90):
            raise ValueError(f"Latitud fuera de rango: {lat}")
        if not (-180 <= lng <= 180):
            raise ValueError(f"Longitud fuera de rango: {lng}")
        return v


class Vehicle(BaseModel):
    """Vehículo en la flota."""
    id: str = Field(description="Identificador único")
    name: Optional[str] = Field(None, description="Nombre descriptivo")
    start_location_id: str = Field(description="ID de ubicación de inicio")
    end_location_id: Optional[str] = Field(None, description="ID de ubicación de fin (default = start)")
    weight_capacity: float = Field(default=0.0, ge=0, description="Capacidad máxima de peso")
    volume_capacity: float = Field(default=0.0, ge=0, description="Capacidad máxima de volumen")
    skills: Optional[list[str]] = Field(None, description="Skills que posee el vehículo")
    start_time: Optional[int] = Field(None, ge=0, description="Inicio de jornada (seg desde medianoche)")
    end_time: Optional[int] = Field(None, ge=0, description="Fin de jornada (seg desde medianoche)")
    breaks: Optional[list[VehicleBreak]] = Field(None, description="Descansos programados")
    fixed_cost: float = Field(default=0.0, ge=0, description="Costo fijo por usar el vehículo")
    cost_per_km: float = Field(default=0.0, ge=0, description="Costo por kilómetro recorrido")
    cost_per_hour: float = Field(default=0.0, ge=0, description="Costo por hora de operación del vehículo")
    cost_per_stop: float = Field(default=0.0, ge=0, description="Costo fijo por cada parada realizada")
    max_route_duration: Optional[int] = Field(None, ge=0, description="Duración máxima de ruta en segundos")
    max_distance: Optional[int] = Field(None, ge=0, description="Distancia máxima de ruta en metros")
    max_tasks: Optional[int] = Field(None, ge=0, description="Número máximo de paradas en la ruta")


class PickupDeliveryPair(BaseModel):
    """Par de recogida y entrega vinculada."""
    pickup_id: str = Field(description="ID de la ubicación de recogida")
    delivery_id: str = Field(description="ID de la ubicación de entrega")


class OptimizationObjective(str, Enum):
    distance = "distance"
    duration = "duration"
    cost = "cost"


class SolverConfig(BaseModel):
    """Configuración del solver — activa/desactiva restricciones."""
    time_limit_seconds: int = Field(default=30, ge=1, description="Tiempo límite del solver")
    allow_skipping_nodes: bool = Field(default=False, description="Permitir omitir nodos (con penalización)")
    drop_penalty: int = Field(default=100000, ge=0, description="Penalización por nodo omitido")
    first_solution_strategy: str = Field(
        default="PATH_CHEAPEST_ARC",
        description="Estrategia de primera solución"
    )
    local_search_metaheuristic: str = Field(
        default="GUIDED_LOCAL_SEARCH",
        description="Metaheurística de búsqueda local"
    )
    max_route_duration: Optional[int] = Field(None, ge=0, description="Duración máxima global de ruta en segundos")
    max_distance: Optional[int] = Field(None, ge=0, description="Distancia máxima global de ruta en metros")
    optimize_by: OptimizationObjective = Field(
        default=OptimizationObjective.distance,
        description="Métrica a optimizar: distancia (metros) o duración (segundos)"
    )
    soft_time_windows: bool = Field(
        default=False,
        description="Permitir llegada tardía con penalización en lugar de prohibirla"
    )
    late_arrival_penalty: int = Field(
        default=1000, ge=1,
        description="Penalización por segundo de llegada tardía (solo si soft_time_windows=True)"
    )
    auto_retry_with_skipping: bool = Field(
        default=True,
        description="Si el solver falla y allow_skipping_nodes=False, reintentar automáticamente con skipping activado"
    )


class OptimizeRequest(BaseModel):
    """Request completo para el solver VRP."""
    locations: list[Location] = Field(min_length=2, description="Lista de ubicaciones (incluye depósitos)")
    vehicles: list[Vehicle] = Field(min_length=1, description="Lista de vehículos")
    pickups_deliveries: Optional[list[PickupDeliveryPair]] = Field(None, description="Pares de recogida y entrega")
    config: SolverConfig = Field(default_factory=SolverConfig, description="Configuración del solver")

    @field_validator("locations")
    @classmethod
    def validate_locations(cls, v: list[Location]) -> list[Location]:
        ids = [loc.id for loc in v]
        if len(ids) != len(set(ids)):
            raise ValueError("IDs de ubicación duplicados")
        if not any(loc.type == LocationType.depot for loc in v):
            raise ValueError("Debe haber al menos un depósito")
        return v

    @field_validator("vehicles")
    @classmethod
    def validate_vehicles(cls, v: list[Vehicle]) -> list[Vehicle]:
        ids = [veh.id for veh in v]
        if len(ids) != len(set(ids)):
            raise ValueError("IDs de vehículo duplicados")
        return v


# ═══════════════════════════════════════════════════════════════════════════
# RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════════════════

class StopResponse(BaseModel):
    """Parada individual en una ruta."""
    location_id: str
    name: Optional[str] = None
    coords: tuple[float, float]
    type: str
    arrival: Optional[str] = None  # formato HH:MM:SS
    departure: Optional[str] = None  # formato HH:MM:SS
    load_weight: Optional[float] = None
    load_volume: Optional[float] = None
    cumulative_weight: Optional[float] = None
    cumulative_volume: Optional[float] = None


class CostBreakdown(BaseModel):
    """Desglose de costos de una ruta."""
    fixed: float = 0.0
    distance: float = 0.0
    time: float = 0.0
    stops: float = 0.0
    total: float = 0.0


class RouteResponse(BaseModel):
    """Ruta de un vehículo."""
    vehicle_id: str
    vehicle_name: Optional[str] = None
    stops: list[StopResponse]
    total_distance: float  # metros
    total_duration: float  # segundos
    total_stops: int
    max_weight: Optional[float] = None
    max_volume: Optional[float] = None
    cost: Optional[CostBreakdown] = None


class StatisticsResponse(BaseModel):
    """Estadísticas de la solución."""
    vehicles_used: int
    vehicles_available: int
    nodes_assigned: int
    nodes_unassigned: int
    total_distance: float  # metros
    total_duration: float  # segundos
    total_cost: Optional[float] = None


class UnassignedNode(BaseModel):
    """Nodo que el solver no pudo asignar."""
    id: str
    name: Optional[str] = None
    reason: Optional[str] = None


class OptimizeResponse(BaseModel):
    """Respuesta del solver VRP."""
    status: SolverStatus
    message: str
    routes: list[RouteResponse] = []
    statistics: Optional[StatisticsResponse] = None
    unassigned_nodes: list[UnassignedNode] = []
    out_of_coverage: list[UnassignedNode] = []
    recommendations: list[str] = []
    warnings: list[str] = []
    errors: Optional[list[ValidationError]] = None
    solver_time_seconds: Optional[float] = None

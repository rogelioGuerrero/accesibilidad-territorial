"""
Pre-chequeo del dataset antes de enviar al solver.
Valida que el request sea viable en milisegundos, evitando gastar 30s de cómputo en algo que de antemano sabemos que va a fallar.
"""

from __future__ import annotations

from .models import Location, LocationType, OptimizeRequest, ValidationError, ValidationErrorCode, Vehicle


class ValidationResult:
    """Resultado de la validación del dataset."""

    def __init__(self):
        self.errors: list[ValidationError] = []
        self.warnings: list[str] = []

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def add_error(self, code: ValidationErrorCode, message: str, details: dict | None = None) -> None:
        self.errors.append(ValidationError(code=code, message=message, details=details))

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)


def validate_request(request: OptimizeRequest) -> ValidationResult:
    """
    Valida el request antes de construir el modelo OR-Tools.
    Retorna ValidationResult con errores estructurados y warnings.
    """
    result = ValidationResult()
    locations = request.locations
    vehicles = request.vehicles

    # ── 1. Depósito ──
    depots = [loc for loc in locations if loc.type == LocationType.depot]
    if not depots:
        result.add_error(
            ValidationErrorCode.NO_DEPOT,
            "El dataset debe incluir al menos un depósito",
        )

    # ── 2. Referencias de vehículos válidas ──
    loc_ids = {loc.id for loc in locations}
    depot_ids = {loc.id for loc in locations if loc.type == LocationType.depot}
    for veh in vehicles:
        if veh.start_location_id not in loc_ids:
            result.add_error(
                ValidationErrorCode.VEHICLE_REF_INVALID,
                f"El vehículo '{veh.id}' referencia una ubicación de inicio que no existe",
                {"vehicle_id": veh.id, "field": "start_location_id", "value": veh.start_location_id},
            )
        elif veh.start_location_id not in depot_ids:
            result.add_error(
                ValidationErrorCode.VEHICLE_REF_INVALID,
                f"El vehículo '{veh.id}' inicia en una ubicación que no es depósito",
                {"vehicle_id": veh.id, "field": "start_location_id", "value": veh.start_location_id},
            )
        if veh.end_location_id is not None and veh.end_location_id not in loc_ids:
            result.add_error(
                ValidationErrorCode.VEHICLE_REF_INVALID,
                f"El vehículo '{veh.id}' referencia una ubicación de fin que no existe",
                {"vehicle_id": veh.id, "field": "end_location_id", "value": veh.end_location_id},
            )

    # ── 3. Capacidad total vs demanda total (peso) ──
    total_demand = sum(
        loc.weight_demand for loc in locations
        if loc.type != LocationType.depot
    )
    total_capacity = sum(v.weight_capacity for v in vehicles)
    if total_capacity > 0 and abs(total_demand) > total_capacity:
        result.add_error(
            ValidationErrorCode.CAPACITY_INSUFFICIENT,
            "La demanda total de peso excede la capacidad combinada de todos los vehículos",
            {"total_demand": abs(total_demand), "total_capacity": total_capacity},
        )

    # ── 3b. Capacidad total vs demanda total (volumen) ──
    total_volume_demand = sum(
        loc.volume_demand for loc in locations
        if loc.type != LocationType.depot
    )
    total_volume_capacity = sum(v.volume_capacity for v in vehicles)
    if total_volume_capacity > 0 and abs(total_volume_demand) > total_volume_capacity:
        result.add_error(
            ValidationErrorCode.CAPACITY_INSUFFICIENT,
            "La demanda total de volumen excede la capacidad combinada de todos los vehículos",
            {"total_volume_demand": abs(total_volume_demand), "total_volume_capacity": total_volume_capacity},
        )

    # ── 4. Demanda individual ≤ capacidad del vehículo más grande (peso) ──
    max_capacity = max((v.weight_capacity for v in vehicles), default=0)
    for loc in locations:
        if loc.type == LocationType.depot:
            continue
        if max_capacity > 0 and abs(loc.weight_demand) > max_capacity:
            result.add_error(
                ValidationErrorCode.DEMAND_EXCEEDS_VEHICLE,
                f"La entrega '{loc.id}' demanda más peso del que puede llevar cualquier vehículo",
                {"location_id": loc.id, "demand": abs(loc.weight_demand), "max_capacity": max_capacity},
            )

    # ── 4b. Demanda individual ≤ capacidad del vehículo más grande (volumen) ──
    max_volume_capacity = max((v.volume_capacity for v in vehicles), default=0)
    for loc in locations:
        if loc.type == LocationType.depot:
            continue
        if max_volume_capacity > 0 and abs(loc.volume_demand) > max_volume_capacity:
            result.add_error(
                ValidationErrorCode.DEMAND_EXCEEDS_VEHICLE,
                f"La entrega '{loc.id}' demanda más volumen del que puede llevar cualquier vehículo",
                {"location_id": loc.id, "volume_demand": abs(loc.volume_demand), "max_volume_capacity": max_volume_capacity},
            )

    # ── 5. Skills compatibles ──
    for loc in locations:
        if not loc.required_skills:
            continue
        compatible = any(
            set(loc.required_skills).issubset(set(v.skills or []))
            for v in vehicles
        )
        if not compatible:
            result.add_error(
                ValidationErrorCode.SKILLS_NO_MATCH,
                f"La entrega '{loc.id}' requiere skills que ningún vehículo tiene",
                {"location_id": loc.id, "required_skills": loc.required_skills},
            )

    # ── 6. Horarios de vehículos coherentes ──
    for veh in vehicles:
        if veh.start_time is not None and veh.end_time is not None:
            if veh.end_time <= veh.start_time:
                result.add_error(
                    ValidationErrorCode.VEHICLE_SCHEDULE_INVALID,
                    f"El vehículo '{veh.id}' tiene un horario inválido (fin ≤ inicio)",
                    {"vehicle_id": veh.id, "start_time": veh.start_time, "end_time": veh.end_time},
                )

    # ── 7. Time windows coherentes ──
    for loc in locations:
        if not loc.time_windows:
            continue
        for tw in loc.time_windows:
            if tw.end < tw.start:
                result.add_error(
                    ValidationErrorCode.TIME_WINDOW_INVALID,
                    f"La entrega '{loc.id}' tiene una ventana de tiempo inválida (fin < inicio)",
                    {"location_id": loc.id, "start": tw.start, "end": tw.end},
                )

    # ── 8. Coordenadas duplicadas ──
    seen_coords: dict[tuple[float, float], str] = {}
    for loc in locations:
        key = (round(loc.coords[0], 6), round(loc.coords[1], 6))
        if key in seen_coords:
            result.add_warning(
                f"Coordenadas duplicadas: {loc.id} y {seen_coords[key]} "
                f"en ({loc.coords[0]:.4f}, {loc.coords[1]:.4f})"
            )
        else:
            seen_coords[key] = loc.id

    # ── 9. Pickup & delivery: IDs existen ──
    if request.pickups_deliveries:
        for pair in request.pickups_deliveries:
            if pair.pickup_id not in loc_ids:
                result.add_error(
                    ValidationErrorCode.PICKUP_DELIVERY_REF_INVALID,
                    f"El par pickup-delivery referencia un pickup que no existe",
                    {"field": "pickup_id", "value": pair.pickup_id},
                )
            if pair.delivery_id not in loc_ids:
                result.add_error(
                    ValidationErrorCode.PICKUP_DELIVERY_REF_INVALID,
                    f"El par pickup-delivery referencia un delivery que no existe",
                    {"field": "delivery_id", "value": pair.delivery_id},
                )

    # ── 10. Warnings de escala ──
    n_deliveries = sum(1 for loc in locations if loc.type != LocationType.depot)
    if n_deliveries > 30:
        result.add_warning(
            f"{n_deliveries} entregas — el rendimiento puede degradarse "
            f"(recomendado ≤ 30 nodos)"
        )

    return result

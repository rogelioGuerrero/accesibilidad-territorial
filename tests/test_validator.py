"""
Tests del validador de dataset (pre-chequeo antes del solver).
Valida que el pre-chequeo detecta problemas comunes en milisegundos.

Ejecutar: uv run pytest tests/test_validator.py -v
"""

import pytest
from vrp_solver.models import (
    Location,
    LocationType,
    OptimizeRequest,
    PickupDeliveryPair,
    SolverConfig,
    TimeWindow,
    Vehicle,
    ValidationErrorCode,
)
from vrp_solver.validator import validate_request


def make_basic_request(
    n_deliveries: int = 5,
    vehicles: list[Vehicle] | None = None,
) -> OptimizeRequest:
    """Crea un request básico válido."""
    coords = [
        (40.4168, -3.7038),  # depot Madrid
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


class TestValidRequest:
    """Request válido pasa el pre-chequeo."""

    def test_valid_request_passes(self):
        request = make_basic_request()
        result = validate_request(request)
        assert result.is_valid
        assert len(result.errors) == 0


class TestNoDepot:
    """Sin depósito → error."""

    def test_no_depot_error(self):
        request = make_basic_request()
        request.locations[0].type = LocationType.delivery
        result = validate_request(request)
        assert not result.is_valid
        assert any(e.code == ValidationErrorCode.NO_DEPOT for e in result.errors)


class TestCapacityInsufficient:
    """Capacidad total < demanda total → error."""

    def test_capacity_insufficient(self):
        request = make_basic_request(n_deliveries=5)
        request.vehicles[0].weight_capacity = 20  # 5 entregas × 10 = 50 > 20
        result = validate_request(request)
        assert not result.is_valid
        assert any(e.code == ValidationErrorCode.CAPACITY_INSUFFICIENT for e in result.errors)


class TestDemandExceedsVehicle:
    """Demanda individual > capacidad del vehículo más grande → error."""

    def test_single_demand_too_big(self):
        request = make_basic_request(n_deliveries=1)
        request.locations[1].weight_demand = 500
        request.vehicles[0].weight_capacity = 200
        result = validate_request(request)
        assert not result.is_valid
        assert any(e.code == ValidationErrorCode.DEMAND_EXCEEDS_VEHICLE for e in result.errors)


class TestSkillsIncompatible:
    """Nodo requiere skill que ningún vehículo tiene → error."""

    def test_no_vehicle_with_skill(self):
        request = make_basic_request(n_deliveries=3)
        request.locations[1].required_skills = ["refrigerated"]
        result = validate_request(request)
        assert not result.is_valid
        assert any(e.code == ValidationErrorCode.SKILLS_NO_MATCH for e in result.errors)

    def test_vehicle_with_skill_passes(self):
        request = make_basic_request(n_deliveries=3)
        request.locations[1].required_skills = ["refrigerated"]
        request.vehicles[0].skills = ["refrigerated"]
        result = validate_request(request)
        assert result.is_valid


class TestVehicleSchedule:
    """Horario de vehículo inválido → error."""

    def test_end_before_start(self):
        request = make_basic_request()
        request.vehicles[0].start_time = 50000
        request.vehicles[0].end_time = 30000
        result = validate_request(request)
        assert not result.is_valid
        assert any(e.code == ValidationErrorCode.VEHICLE_SCHEDULE_INVALID for e in result.errors)


class TestTimeWindowInvalid:
    """Time window con end < start → error."""

    def test_tw_end_before_start(self):
        request = make_basic_request(n_deliveries=3)
        # Usar model_construct para bypass de validación de Pydantic
        tw = TimeWindow.model_construct(start=50000, end=30000)
        request.locations[1].time_windows = [tw]
        result = validate_request(request)
        assert not result.is_valid
        assert any(e.code == ValidationErrorCode.TIME_WINDOW_INVALID for e in result.errors)


class TestVehicleReferences:
    """Referencias de vehículo a locations inexistentes → error."""

    def test_start_location_not_found(self):
        request = make_basic_request()
        request.vehicles[0].start_location_id = "nonexistent"
        result = validate_request(request)
        assert not result.is_valid
        assert any(e.code == ValidationErrorCode.VEHICLE_REF_INVALID for e in result.errors)


class TestPickupDelivery:
    """Pickup-delivery con IDs inexistentes → error."""

    def test_pickup_id_not_found(self):
        request = make_basic_request(n_deliveries=3)
        request.pickups_deliveries = [
            PickupDeliveryPair(pickup_id="nonexistent", delivery_id="del_1")
        ]
        result = validate_request(request)
        assert not result.is_valid
        assert any(e.code == ValidationErrorCode.PICKUP_DELIVERY_REF_INVALID for e in result.errors)


class TestScaleWarning:
    """Más de 30 entregas → warning (no error)."""

    def test_scale_warning(self):
        coords = [(40.4168 + i * 0.001, -3.7038 + i * 0.001) for i in range(35)]
        locations = [
            Location(id="depot", name="Depósito", coords=coords[0], type=LocationType.depot)
        ]
        for i in range(1, 33):
            locations.append(Location(
                id=f"del_{i}",
                name=f"Entrega {i}",
                coords=coords[i],
                type=LocationType.delivery,
                weight_demand=1.0,
            ))
        vehicles = [Vehicle(
            id="veh_1", name="V1",
            start_location_id="depot", end_location_id="depot",
            weight_capacity=1000,
        )]
        request = OptimizeRequest(locations=locations, vehicles=vehicles)
        result = validate_request(request)
        assert result.is_valid
        assert any("rendimiento" in w for w in result.warnings)

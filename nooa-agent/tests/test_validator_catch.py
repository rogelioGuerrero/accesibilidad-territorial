"""
Tests de validación directa: payloads inválidos atrapados por el validator.

Estos tests no requieren LLM — usan _process_payload directamente con datos inválidos.

Ejecutar: pytest nooa-agent/test_validator_catch.py -v
"""

import copy

from chat_agent import ChatVRPAgent


# Payload base válido en estructura, pero con capacidad insuficiente
_BASE_PAYLOAD = {
    "locations": [
        {"id": "depot", "name": "Deposito", "coords": [4.65, -74.1], "type": "depot"},
        {"id": "del_1", "name": "E1", "coords": [4.68, -74.05], "type": "delivery", "weight_demand": 10.0, "service_time": 300},
        {"id": "del_2", "name": "E2", "coords": [4.62, -74.15], "type": "delivery", "weight_demand": 10.0, "service_time": 300},
        {"id": "del_3", "name": "E3", "coords": [4.7, -74.12], "type": "delivery", "weight_demand": 10.0, "service_time": 300},
        {"id": "del_4", "name": "E4", "coords": [4.6, -74.08], "type": "delivery", "weight_demand": 10.0, "service_time": 300},
        {"id": "del_5", "name": "E5", "coords": [4.66, -74.14], "type": "delivery", "weight_demand": 10.0, "service_time": 300},
    ],
    "vehicles": [
        {"id": "veh_1", "name": "V1", "start_location_id": "depot", "end_location_id": "depot", "weight_capacity": 30.0}
    ],
    "pickups_deliveries": []
}


def test_payload_insufficient_capacity():
    """Payload con capacidad insuficiente (30kg vs 50kg) es rechazado."""
    agent = ChatVRPAgent("bogota")
    result = agent._process_payload(copy.deepcopy(_BASE_PAYLOAD))
    assert "validacion" in result.lower() or "capacidad" in result.lower() or "corregir" in result.lower()


def test_payload_no_depot():
    """Payload sin depósito es rechazado."""
    agent = ChatVRPAgent("bogota")
    data = copy.deepcopy(_BASE_PAYLOAD)
    data["locations"][0]["type"] = "delivery"
    result = agent._process_payload(data)
    assert "validacion" in result.lower() or "deposito" in result.lower() or "depot" in result.lower() or "corregir" in result.lower()


def test_payload_invalid_depot_reference():
    """Payload con vehículo referenciando depósito inexistente es rechazado."""
    agent = ChatVRPAgent("bogota")
    data = copy.deepcopy(_BASE_PAYLOAD)
    data["vehicles"][0]["start_location_id"] = "no_existe"
    result = agent._process_payload(data)
    assert "validacion" in result.lower() or "corregir" in result.lower() or "error" in result.lower()

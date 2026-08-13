"""
Tests para el agente multi-motor.

Tests sin LLM (corren siempre):
    - VRP, Bin Packing, Min Cost Flow con datos directos
    - Menu del agente

Tests con LLM real (skip si no hay GROQ_API_KEY):
    - Extracción de parámetros desde texto natural

Ejecutar: pytest nooa-agent/test_multi_agent.py -v
"""

import json
from pathlib import Path

import pytest

from conftest import requires_llm
from engines.bin_packing import (
    BinPackingItem, BinPackingBin, BinPackingRequest, BinPackingSolver,
)
from engines.min_cost_flow import (
    MinCostFlowSolver,
    build_school_assignment,
)
from vrp_solver.models import Location, LocationType, OptimizeRequest, Vehicle
from vrp_solver.solver import VRPSolver
from vrp_solver.validator import validate_request

FIXTURES = Path(__file__).parent.parent.parent / "src" / "vrp_solver" / "tests" / "fixtures"


# ─── Tests sin LLM (siempre corren) ─────────────────────────────────


def test_vrp_engine():
    """VRP con datos directos (sin LLM)."""
    with open(FIXTURES / "coords_bogota_6.json") as f:
        coords = [tuple(c) for c in json.load(f)["coords"]]

    locations = [
        Location(id="depot", name="Deposito", coords=list(coords[0]), type=LocationType.depot),
    ]
    for i in range(1, 6):
        locations.append(Location(
            id=f"del_{i}", name=f"Entrega {i}", coords=list(coords[i]),
            type=LocationType.delivery, weight_demand=10.0, service_time=300,
        ))

    vehicles = [
        Vehicle(id="veh_1", name="Vehiculo 1", start_location_id="depot",
                end_location_id="depot", weight_capacity=100.0),
    ]

    request = OptimizeRequest(locations=locations, vehicles=vehicles)
    validation = validate_request(request)
    assert validation.is_valid

    solver = VRPSolver.from_request(
        request,
        matrix_provider="cached",
        matrix_path=str(FIXTURES / "matrix_bogota_6.json"),
    )
    result = solver.solve()

    assert not result.errors
    assert len(result.routes) > 0
    assert result.statistics.nodes_assigned == 5


def test_bin_packing_basic():
    """Bin packing: 4 items que caben en una sola caja."""
    items = [
        BinPackingItem(id="i1", name="Producto A", weight=10.0),
        BinPackingItem(id="i2", name="Producto B", weight=15.0),
        BinPackingItem(id="i3", name="Producto C", weight=5.0),
        BinPackingItem(id="i4", name="Producto D", weight=20.0),
    ]
    bins = [BinPackingBin(id="b1", name="Caja Grande", capacity_weight=50.0)]

    request = BinPackingRequest(items=items, bins=bins)
    solver = BinPackingSolver(request)
    result = solver.solve()

    assert not result.errors
    assert result.total_items_packed == 4
    assert result.total_bins_used == 1
    assert abs(result.total_weight - 50.0) < 0.01


def test_bin_packing_multiple_bins():
    """Bin packing: 5 items de 20kg en cajas de 50kg requieren 3 cajas."""
    items = [
        BinPackingItem(id=f"i{i+1}", name=f"Producto {i+1}", weight=20.0)
        for i in range(5)
    ]
    bins = [
        BinPackingBin(id=f"b{i+1}", name=f"Caja {i+1}", capacity_weight=50.0)
        for i in range(3)
    ]

    request = BinPackingRequest(items=items, bins=bins)
    solver = BinPackingSolver(request)
    result = solver.solve()

    assert not result.errors
    assert result.total_items_packed == 5
    assert result.total_bins_used == 3
    assert result.total_weight == 100.0


def test_bin_packing_oversized_item():
    """Item que excede capacidad máxima queda como no empacado."""
    items = [
        BinPackingItem(id="i1", name="Producto Pequeno", weight=5.0),
        BinPackingItem(id="i2", name="Producto Gigante", weight=100.0),
    ]
    bins = [BinPackingBin(id="b1", name="Caja", capacity_weight=50.0)]

    request = BinPackingRequest(items=items, bins=bins)
    solver = BinPackingSolver(request)
    result = solver.solve()

    assert len(result.unassigned_items) == 1
    assert result.unassigned_items[0].id == "i2"
    assert result.total_items_packed == 1


def test_min_cost_flow_school():
    """Asignación escolar con Min Cost Flow: 80 niños a 2 escuelas."""
    schools = [
        {"id": "esc_1", "name": "Escuela A", "coords": [4.60, -74.05], "capacity": 60},
        {"id": "esc_2", "name": "Escuela B", "coords": [4.70, -74.12], "capacity": 40},
    ]
    neighborhoods = [
        {"id": "bar_1", "name": "Barrio Norte", "coords": [4.65, -74.08], "children": 50},
        {"id": "bar_2", "name": "Barrio Sur", "coords": [4.55, -74.15], "children": 30},
    ]

    request = build_school_assignment(schools, neighborhoods)
    solver = MinCostFlowSolver(request)
    result = solver.solve()

    assert not result.errors
    assert result.total_units_assigned == 80


def test_min_cost_flow_insufficient_capacity():
    """Asignación escolar con capacidad insuficiente asigna lo posible."""
    schools = [
        {"id": "esc_1", "name": "Escuela A", "coords": [4.60, -74.05], "capacity": 30},
    ]
    neighborhoods = [
        {"id": "bar_1", "name": "Barrio Norte", "coords": [4.65, -74.08], "children": 50},
    ]

    request = build_school_assignment(schools, neighborhoods)
    solver = MinCostFlowSolver(request)
    result = solver.solve()

    assert not result.errors
    assert result.total_units_assigned > 0
    assert result.total_units_assigned <= 30


def test_agent_menu():
    """Menu del agente muestra 3 opciones y procesa selección válida/inválida."""
    from multi_agent import MultiEngineAgent

    agent = MultiEngineAgent("bogota")
    menu = agent.show_menu()
    assert "1." in menu and "2." in menu and "3." in menu

    resp = agent.select_motor("1")
    assert "VRP" in resp or "rutas" in resp.lower()
    assert agent.motor_elegido == 1

    agent.motor_elegido = None
    resp = agent.select_motor("9")
    assert "inválida" in resp.lower() or "invalida" in resp.lower()
    assert agent.motor_elegido is None


# ─── Tests con LLM real (skip si no hay GROQ_API_KEY) ───────────────


@requires_llm
def test_agent_llm_vrp():
    """Agente multi-motor: extracción LLM real para VRP."""
    from multi_agent import MultiEngineAgent

    agent = MultiEngineAgent("bogota")
    agent.motor_elegido = 1
    user_text = "Tengo 2 camiones con capacidad de 50kg cada uno y 5 entregas de 10kg cada una"
    result = agent.process_user_response(user_text)
    assert "error" not in result.lower()


@requires_llm
def test_agent_llm_bin_packing():
    """Agente multi-motor: extracción LLM real para Bin Packing."""
    from multi_agent import MultiEngineAgent

    agent = MultiEngineAgent("bogota")
    agent.motor_elegido = 2
    user_text = "Tengo 10 productos de 5kg cada uno y 3 cajas con capacidad de 20kg cada una"
    result = agent.process_user_response(user_text)
    assert "error" not in result.lower()


@requires_llm
def test_agent_llm_school():
    """Agente multi-motor: extracción LLM real para asignación escolar."""
    from multi_agent import MultiEngineAgent

    agent = MultiEngineAgent("bogota")
    agent.motor_elegido = 3
    user_text = "3 barrios con 40, 30 y 50 niños. 2 escuelas con capacidad de 60 y 70"
    result = agent.process_user_response(user_text)
    assert "error" not in result.lower()

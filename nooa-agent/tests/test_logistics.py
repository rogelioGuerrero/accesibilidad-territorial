"""
Tests para LogisticsAgent — orquestador chat con tool calling nativo.

Tests sin LLM (corren siempre):
    - Init con ciudad válida/inválida
    - Tool execution directo con datos reales (VRP, bin packing, min cost flow)

Tests con LLM real (skip si no hay GROQ_API_KEY):
    - Chat conversación completa: texto → tool call → explicación

Ejecutar: pytest nooa-agent/test_logistics.py -v
"""

import json
from pathlib import Path

import pytest

from conftest import requires_llm
from logistics_agent import LogisticsAgent

FIXTURES = Path(__file__).parent.parent.parent / "src" / "vrp_solver" / "tests" / "fixtures"


# ─── Tests sin LLM (siempre corren) ─────────────────────────────────


def test_init_valid_city():
    """LogisticsAgent se inicializa con ciudad válida."""
    agent = LogisticsAgent("bogota")
    assert agent.city == "bogota"
    assert len(agent._coords) > 0
    assert len(agent._messages) == 1  # system prompt


def test_init_invalid_city():
    """Ciudad no disponible lanza ValueError."""
    with pytest.raises(ValueError, match="no disponible"):
        LogisticsAgent("paris")


def test_reset():
    """Reset limpia el historial manteniendo la ciudad."""
    agent = LogisticsAgent("bogota")
    agent._messages.append({"role": "user", "content": "hola"})
    agent._last_result = "something"
    agent.reset()
    assert len(agent._messages) == 1
    assert agent._last_result is None


def test_execute_tool_vrp():
    """Tool optimize_vrp ejecuta OR-Tools VRP con datos reales."""
    agent = LogisticsAgent("bogota")

    with open(FIXTURES / "coords_bogota_6.json") as f:
        coords = json.load(f)["coords"]

    locations = [
        {"id": "depot", "name": "Deposito", "coords": coords[0], "type": "depot"},
    ]
    for i in range(1, 6):
        locations.append({
            "id": f"del_{i}", "name": f"Entrega {i}", "coords": coords[i],
            "type": "delivery", "weight_demand": 10.0, "service_time": 300,
        })

    vehicles = [
        {"id": "veh_1", "name": "Vehiculo 1", "start_location_id": "depot",
         "end_location_id": "depot", "weight_capacity": 100.0},
    ]

    result = agent._execute_tool("optimize_vrp", {"locations": locations, "vehicles": vehicles})

    assert "error" not in result
    assert len(result["routes"]) > 0
    assert result["nodes_assigned"] == 5
    assert result["total_distance_km"] > 0


def test_execute_tool_bin_packing():
    """Tool optimize_bin_packing ejecuta OR-Tools Knapsack con datos reales."""
    agent = LogisticsAgent("bogota")

    result = agent._execute_tool("optimize_bin_packing", {
        "items": [
            {"id": "i1", "name": "Producto A", "weight": 10.0},
            {"id": "i2", "name": "Producto B", "weight": 15.0},
            {"id": "i3", "name": "Producto C", "weight": 5.0},
            {"id": "i4", "name": "Producto D", "weight": 20.0},
        ],
        "bins": [
            {"id": "b1", "name": "Caja Grande", "capacity_weight": 50.0},
        ],
    })

    assert "error" not in result
    assert result["items_packed"] == 4
    assert result["bins_used"] == 1


def test_execute_tool_min_cost_flow():
    """Tool optimize_min_cost_flow ejecuta OR-Tools MCF con datos reales."""
    agent = LogisticsAgent("bogota")

    result = agent._execute_tool("optimize_min_cost_flow", {
        "schools": [
            {"id": "esc_1", "name": "Escuela A", "coords": [4.60, -74.05], "capacity": 60},
            {"id": "esc_2", "name": "Escuela B", "coords": [4.70, -74.12], "capacity": 40},
        ],
        "neighborhoods": [
            {"id": "bar_1", "name": "Barrio Norte", "coords": [4.65, -74.08], "children": 50},
            {"id": "bar_2", "name": "Barrio Sur", "coords": [4.55, -74.15], "children": 30},
        ],
    })

    assert "error" not in result
    assert result["total_children_assigned"] == 80


def test_execute_tool_unknown():
    """Tool desconocido devuelve error."""
    agent = LogisticsAgent("bogota")
    result = agent._execute_tool("no_existe", {})
    assert "error" in result


def test_validate_output_vrp_valid():
    """_validate_output aprueba VRP con rutas."""
    agent = LogisticsAgent("bogota")
    result = {"routes": [{"vehicle": "v1", "stops": ["A", "B"]}], "nodes_assigned": 5}
    assert agent._validate_output("optimize_vrp", result) is True


def test_validate_output_vrp_no_routes():
    """_validate_output rechaza VRP sin rutas."""
    agent = LogisticsAgent("bogota")
    result = {"routes": [], "nodes_assigned": 0}
    assert agent._validate_output("optimize_vrp", result) is False


def test_validate_output_bin_packing_valid():
    """_validate_output aprueba bin packing con items empacados."""
    agent = LogisticsAgent("bogota")
    result = {"items_packed": 4, "items_total": 4, "bins_used": 1}
    assert agent._validate_output("optimize_bin_packing", result) is True


def test_validate_output_bin_packing_zero():
    """_validate_output rechaza bin packing que empacó 0 items."""
    agent = LogisticsAgent("bogota")
    result = {"items_packed": 0, "items_total": 5, "bins_used": 0}
    assert agent._validate_output("optimize_bin_packing", result) is False


def test_validate_output_mcf_valid():
    """_validate_output aprueba MCF con niños asignados."""
    agent = LogisticsAgent("bogota")
    result = {"total_children_assigned": 80, "assignments": []}
    assert agent._validate_output("optimize_min_cost_flow", result) is True


def test_validate_output_mcf_zero():
    """_validate_output rechaza MCF que asignó 0 niños."""
    agent = LogisticsAgent("bogota")
    result = {"total_children_assigned": 0, "assignments": []}
    assert agent._validate_output("optimize_min_cost_flow", result) is False


def test_validate_output_error():
    """_validate_output rechaza cualquier resultado con key 'error'."""
    agent = LogisticsAgent("bogota")
    result = {"error": "Validación falló", "errors": ["capacidad insuficiente"]}
    assert agent._validate_output("optimize_vrp", result) is False


def test_validate_output_non_dict():
    """_validate_output rechaza resultados que no son dict."""
    agent = LogisticsAgent("bogota")
    assert agent._validate_output("optimize_vrp", None) is False
    assert agent._validate_output("optimize_vrp", "string") is False


# ─── Test end-to-end con valor de referencia conocido ────────────────


def test_e2e_vrp_reference_values():
    """
    End-to-end: VRP con datos reales de Bogotá (6 puntos, matriz cacheada).

    OR-Tools es determinista con la misma matriz y parámetros.
    Si la distancia total cambia, algo se rompió:
      - nodes_assigned != 5  → parámetros (capacidad, coordenadas)
      - len(routes) != 1     → vehicles mal configurados
      - distance != 59.73    → matriz cambió o solver dio otra solución
    """
    agent = LogisticsAgent("bogota")
    coords = agent._coords

    locations = [{"id": "depot", "name": "Deposito", "coords": list(coords[0]), "type": "depot"}]
    for i in range(1, 6):
        locations.append({
            "id": f"del_{i}", "name": f"E{i}", "coords": list(coords[i]),
            "type": "delivery", "weight_demand": 10.0, "service_time": 300,
        })

    vehicles = [
        {"id": "veh_1", "name": "V1", "start_location_id": "depot",
         "end_location_id": "depot", "weight_capacity": 100.0},
    ]

    result = agent.optimize_vrp(locations, vehicles)

    assert "error" not in result, f"Solver error: {result.get('error')}"
    assert result["nodes_assigned"] == 5, f"Esperaba 5 nodos, got {result['nodes_assigned']}"
    assert result["nodes_unassigned"] == 0, f"Nodos sin asignar: {result['nodes_unassigned']}"
    assert len(result["routes"]) == 1, f"Esperaba 1 ruta, got {len(result['routes'])}"
    assert result["routes"][0]["stops_count"] == 7, "Ruta debe visitar 5 entregas + depósito ida/vuelta"
    assert abs(result["total_distance_km"] - 59.73) < 0.5, (
        f"Distancia esperada ~59.73 km, got {result['total_distance_km']} km — "
        "la matriz o el solver cambiaron"
    )


# ─── Tests con LLM real (skip si no hay GROQ_API_KEY) ───────────────


@requires_llm
def test_chat_vrp():
    """Chat completo: usuario describe VRP → LLM llama tool → explica resultado."""
    agent = LogisticsAgent("bogota")
    resp = agent.chat("Tengo 1 camión de 100kg y necesito hacer 5 entregas de 10kg cada una")
    assert isinstance(resp, str)
    assert len(resp) > 20


@requires_llm
def test_chat_bin_packing():
    """Chat completo: usuario describe bin packing → LLM llama tool → explica."""
    agent = LogisticsAgent("bogota")
    resp = agent.chat("Tengo 10 productos de 5kg cada uno y 3 cajas con capacidad de 20kg cada una")
    assert isinstance(resp, str)
    assert len(resp) > 20


@requires_llm
def test_chat_min_cost_flow():
    """Chat completo: usuario describe asignación escolar → LLM llama tool → explica."""
    agent = LogisticsAgent("bogota")
    resp = agent.chat("3 barrios con 40, 30 y 50 niños. 2 escuelas con capacidad de 60 y 70")
    assert isinstance(resp, str)
    assert len(resp) > 20


@requires_llm
def test_chat_multi_turn():
    """Conversación multi-turno: saludo → pregunta → datos → resultado."""
    agent = LogisticsAgent("bogota")

    r1 = agent.chat("Hola")
    assert len(r1) > 0

    r2 = agent.chat("Tengo 2 camiones con capacidad de 50kg cada uno")
    assert len(r2) > 0

    r3 = agent.chat("5 entregas de 10kg cada una en Bogota")
    assert len(r3) > 20

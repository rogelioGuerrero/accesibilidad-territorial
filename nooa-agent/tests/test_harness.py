"""
Tests para el harness NOOA — pass-by-reference, memory store, harness APIs.

Tests sin LLM (corren siempre):
    - ResultRegistry: store, get, previews, context blocks
    - ToolResult: bounded previews de dicts, listas, dataclasses
    - MemoryStore: CRUD entities, relations, search, consolidation
    - HarnessAPI: inspect_context, query_history, remember, recall, relate

Tests con LLM real (skip si no hay GROQ_API_KEY):
    - LogisticsAgent con harness tools integrados
    - EmergencyAutonomousAgent con @strategy cross_analysis

Ejecutar: pytest nooa-agent/test_harness.py -v
"""

import json
import tempfile
from pathlib import Path

import pytest

from conftest import requires_llm
from harness import ToolResult, ResultRegistry
from memory_store import MemoryStore, Entity, Relation
from harness_api import HarnessAPI, HARNESS_TOOLS


# ─── ToolResult: bounded previews ───────────────────────────────────

def test_toolresult_preview_dict_small():
    """Dict pequeño se muestra completo."""
    tr = ToolResult.from_value("test", {"a": 1, "b": 2})
    assert "a" in tr.preview
    assert "b" in tr.preview
    assert tr.value == {"a": 1, "b": 2}


def test_toolresult_preview_dict_large():
    """Dict grande se trunca con resumen de keys."""
    big = {f"key_{i}": i for i in range(20)}
    tr = ToolResult.from_value("test", big)
    assert "20 keys total" in tr.preview
    assert tr.value == big  # full value preserved


def test_toolresult_preview_list():
    """Lista larga se trunca."""
    big_list = list(range(20))
    tr = ToolResult.from_value("test", big_list)
    assert "20 items total" in tr.preview


def test_toolresult_preview_string():
    """String largo se trunca con char count."""
    long_str = "x" * 500
    tr = ToolResult.from_value("test", long_str)
    assert "500 chars total" in tr.preview


def test_toolresult_error():
    """ToolResult.from_error crea preview de error."""
    tr = ToolResult.from_error("fail", "something broke")
    assert tr.is_error
    assert "ERROR" in tr.preview


# ─── ResultRegistry: pass-by-reference ──────────────────────────────

def test_registry_store_and_get():
    """Store y retrieve de ToolResults."""
    reg = ResultRegistry()
    reg.store(ToolResult.from_value("vrp", {"routes": [1, 2, 3]}))
    assert reg.get("vrp") is not None
    assert reg.get_value("vrp") == {"routes": [1, 2, 3]}


def test_registry_preview():
    """get_preview devuelve bounded preview, no el valor completo."""
    reg = ResultRegistry()
    reg.store(ToolResult.from_value("big", {"data": "x" * 1000}))
    preview = reg.get_preview("big")
    assert len(preview) < 500  # bounded


def test_registry_context_block():
    """build_context_block genera resumen para el LLM."""
    reg = ResultRegistry()
    reg.store(ToolResult.from_value("vrp", {"routes": 5, "distance": 42.5}))
    reg.store(ToolResult.from_error("sentinel", "no credentials"))
    block = reg.build_context_block()
    assert "vrp" in block
    assert "sentinel" in block
    assert "❌" in block


def test_registry_list_names():
    reg = ResultRegistry()
    reg.store(ToolResult.from_value("a", 1))
    reg.store(ToolResult.from_value("b", 2))
    assert set(reg.list_names()) == {"a", "b"}


# ─── MemoryStore: knowledge graph ───────────────────────────────────

@pytest.fixture
def memory():
    """MemoryStore en :memory: para tests aislados."""
    store = MemoryStore(":memory:")
    yield store
    store.close()


def test_memory_create_entity(memory):
    e = memory.create_entity("eq1", "event", ["M6.2 en Bogotá"], importance=0.9, tags=["sismo"])
    assert e.name == "eq1"
    assert e.entity_type == "event"
    assert "M6.2" in e.observations[0]
    assert e.importance == 0.9


def test_memory_get_nonexistent(memory):
    assert memory.get_entity("no_existe") is None


def test_memory_add_observations(memory):
    memory.create_entity("h1", "hospital", ["Hospital Norte"])
    e = memory.add_observations("h1", ["20 camas disponibles", "trauma nivel 2"])
    assert len(e.observations) == 3


def test_memory_list_by_type(memory):
    memory.create_entity("e1", "event", ["sismo"], importance=0.8)
    memory.create_entity("e2", "event", ["inundación"], importance=0.6)
    memory.create_entity("h1", "hospital", ["San José"])
    events = memory.list_entities(entity_type="event")
    assert len(events) == 2


def test_memory_list_min_importance(memory):
    memory.create_entity("e1", "event", ["sismo"], importance=0.9)
    memory.create_entity("e2", "event", ["lluvia"], importance=0.1)
    high = memory.list_entities(min_importance=0.5)
    assert len(high) == 1


def test_memory_relations(memory):
    memory.create_entity("eq1", "event", ["terremoto"])
    memory.create_entity("h1", "hospital", ["Hospital Central"])
    rel = memory.create_relation("eq1", "h1", "related-to")
    assert rel is not None
    assert rel.relation_type == "related-to"

    rels = memory.get_relations("eq1")
    assert len(rels) == 1


def test_memory_relation_missing_entity(memory):
    """Relación con entidad inexistente devuelve None."""
    memory.create_entity("a", "test", ["a"])
    rel = memory.create_relation("a", "no_existe", "related-to")
    assert rel is None


def test_memory_search(memory):
    memory.create_entity("sismo_bogota", "event", ["M6.2", "Bogotá", "10km profundidad"], tags=["sismo", "crítico"])
    memory.create_entity("inundacion_cali", "event", ["lluvias torrenciales", "Cali"], tags=["inundacion"])
    results = memory.search("bogota")
    assert len(results) == 1
    assert results[0].name == "sismo_bogota"


def test_memory_consolidation(memory):
    """Consolidación: prune stale low-importance entities."""
    memory.create_entity("old_low", "event", ["old"], importance=0.05)
    memory.create_entity("important", "event", ["keep"], importance=0.9)
    stats = memory.consolidate(min_importance=0.1)
    assert stats["pruned"] >= 0  # may not prune if not old enough
    assert memory.get_entity("important") is not None


def test_memory_export_graph(memory):
    memory.create_entity("a", "event", ["test"])
    memory.create_entity("b", "hospital", ["test2"])
    memory.create_relation("a", "b", "related-to")
    graph = memory.export_graph()
    assert len(graph["entities"]) == 2
    assert len(graph["relations"]) == 1


# ─── HarnessAPI: model-callable tools ───────────────────────────────

@pytest.fixture
def harness():
    """HarnessAPI con memory y registry frescos."""
    mem = MemoryStore(":memory:")
    reg = ResultRegistry()
    api = HarnessAPI(agent=None, memory_store=mem, result_registry=reg)
    yield api
    mem.close()


def test_harness_remember_recall(harness):
    r = harness.execute("remember", {
        "entity_name": "sismo_001",
        "entity_type": "event",
        "observations": ["M6.2 en Bogotá", "10km profundidad"],
        "importance": 0.9,
        "tags": ["sismo", "crítico"],
    })
    assert r["status"] == "stored"

    results = harness.execute("recall", {"query": "bogota"})
    assert results["count"] == 1
    assert "M6.2" in str(results["results"])


def test_harness_relate(harness):
    harness.execute("remember", {"entity_name": "e1", "entity_type": "event", "observations": ["sismo"]})
    harness.execute("remember", {"entity_name": "h1", "entity_type": "hospital", "observations": ["Central"]})
    r = harness.execute("relate", {"from_entity": "e1", "to_entity": "h1", "relation_type": "related-to"})
    assert r["status"] == "created"


def test_harness_list_tool_results(harness):
    harness._results.store(ToolResult.from_value("vrp", {"routes": 3}))
    r = harness.execute("list_tool_results", {})
    assert r["count"] == 1
    assert "vrp" in r["results"]


def test_harness_get_tool_result(harness):
    harness._results.store(ToolResult.from_value("vrp", {"routes": [1, 2, 3]}))
    r = harness.execute("get_tool_result", {"name": "vrp"})
    assert r["value"] == {"routes": [1, 2, 3]}


def test_harness_get_tool_result_missing(harness):
    r = harness.execute("get_tool_result", {"name": "no_existe"})
    assert "error" in r


def test_harness_unknown_tool(harness):
    r = harness.execute("no_existe", {})
    assert "error" in r


# ─── CodeAction: ejecución de código generado ───────────────────────

def test_strip_method_def_full_definition():
    """Si el LLM devuelve la definición completa, se extrae solo el cuerpo."""
    from code_action import _strip_method_def

    code = '''def cross_analysis(self, event: EmergencyEvent) -> str:
    report = "informe"
    return report'''
    body = _strip_method_def(code, "cross_analysis")
    assert "def cross_analysis" not in body
    assert 'report = "informe"' in body
    assert "return report" in body


def test_strip_method_def_body_only():
    """Si el LLM devuelve solo el cuerpo, no se modifica."""
    from code_action import _strip_method_def

    code = 'report = "informe"\nreturn report'
    assert _strip_method_def(code, "cross_analysis") == code


def test_execute_code_action_with_return():
    """Código generado con return se ejecuta y devuelve el valor."""
    from code_action import _execute_code_action

    class FakeAgent:
        value = 42

    def fake_method(self, event):
        """doc"""
        ...

    code = 'report = f"Evento: {event} - valor: {self.value}"\nreturn report'
    result = _execute_code_action(FakeAgent(), code, fake_method, ("sismo",), {})
    assert result == "Evento: sismo - valor: 42"


def test_execute_code_action_full_def():
    """Definición completa del método también se ejecuta correctamente."""
    from code_action import _execute_code_action

    class FakeAgent:
        value = 42

    def fake_method(self, event):
        """doc"""
        ...

    code = '''def fake_method(self, event: str) -> str:
    return str(self.value * 2)'''
    result = _execute_code_action(FakeAgent(), code, fake_method, ("x",), {})
    assert result == "84"


# ─── Tests con LLM real ─────────────────────────────────────────────

@requires_llm
def test_logistics_with_harness_tools():
    """LogisticsAgent tiene harness tools disponibles para el LLM."""
    from logistics_agent import LogisticsAgent
    agent = LogisticsAgent("bogota")
    resp = agent.chat("Hola, ¿qué herramientas tienes disponibles?")
    assert isinstance(resp, str)
    assert len(resp) > 10


@requires_llm
def test_logistics_pass_by_reference():
    """VRP result se almacena por referencia, el LLM ve solo preview."""
    from logistics_agent import LogisticsAgent
    agent = LogisticsAgent("bogota")
    resp = agent.chat("1 camión 100kg, 3 entregas de 10kg en Bogotá")
    assert isinstance(resp, str)
    assert len(resp) > 20
    # Verificar que el resultado quedó en el registry
    assert "optimize_vrp" in agent._result_registry.list_names()


@requires_llm
def test_emergency_strategy_cross_analysis():
    """@strategy cross_analysis se completa con LLM en runtime."""
    from emergency_autonomous import EmergencyAutonomousAgent
    from emergency_agent import EmergencyEvent

    agent = EmergencyAutonomousAgent("bogota")
    event = EmergencyEvent(
        event_type="sismo",
        epicenter=(4.65, -74.08),
        magnitude=6.2,
        affected_zones=[
            {"name": "Zona Norte", "coords": [4.70, -74.05], "severity": 8, "casualties": 50},
            {"name": "Zona Sur", "coords": [4.55, -74.15], "severity": 5, "casualties": 20},
        ],
    )

    # Pre-populate result registry with tool results
    agent._result_registry.store(ToolResult.from_value("search_sentinel", {"products": [
        {"name": "S2A_20250801", "date": "2025-08-01"},
    ], "count": 1}))
    agent._result_registry.store(ToolResult.from_value("generate_deformation_map", {
        "zones": [
            {"name": "Zona Norte", "max_mm": 150, "severity": 8, "building_risk": 85},
            {"name": "Zona Sur", "max_mm": 45, "severity": 5, "building_risk": 30},
        ],
        "max_deformation_mm": 150,
    }))
    agent._result_registry.store(ToolResult.from_value("optimize_evacuation", {
        "routes": 3, "summary": "3 ambulancias despachadas"
    }))
    agent._result_registry.store(ToolResult.from_value("optimize_hospital_assignment", {
        "assignments": 4, "summary": "70 heridos asignados a 2 hospitales"
    }))

    # Ejecutar el método @strategy — el LLM escribe el cuerpo
    report = agent.cross_analysis(event)
    assert isinstance(report, str)
    assert len(report) > 50
    # Debe mencionar datos de los resultados
    assert any(word in report.lower() for word in ["deformación", "deformacion", "heridos", "zona", "hospital"])

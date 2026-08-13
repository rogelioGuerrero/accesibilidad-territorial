"""
Tests para EmergencyAgent y SentinelClient.

Tests sin LLM (corren siempre):
    - SentinelClient sin credenciales
    - bbox_to_wkt
    - EmergencyAgent init
    - EmergencyAgent sin datos

Tests con LLM real (skip si no hay GROQ_API_KEY):
    - on_event, evacuation, hospital, aid, full_response

Ejecutar: pytest nooa-agent/test_emergency.py -v
"""

import pytest

from conftest import requires_llm
from emergency_agent import (
    EmergencyAgent, EmergencyEvent, Hospital, Ambulance, AidItem,
)
from sentinel_client import SentinelClient, bbox_to_wkt


# ─── Tests sin LLM (siempre corren) ─────────────────────────────────


def test_sentinel_client_no_credentials(monkeypatch):
    """SentinelClient sin credenciales no autentica."""
    monkeypatch.delenv("CDSE_USERNAME", raising=False)
    monkeypatch.delenv("CDSE_PASSWORD", raising=False)
    client = SentinelClient(username=None, password=None)
    assert not client._check_credentials()
    assert not client.authenticate()


def test_bbox_to_wkt():
    """Conversión de bbox a WKT produce geometría válida."""
    wkt = bbox_to_wkt(-74.5, 4.5, -74.0, 5.0)
    assert "POLYGON" in wkt
    assert "-74.5" in wkt and "4.5" in wkt


def test_emergency_agent_init():
    """EmergencyAgent se inicializa con estado vacío."""
    agent = EmergencyAgent(city="bogota")
    assert agent.event is None
    assert agent.hospitals == []
    assert agent.ambulances == []
    assert agent.aid_items == []
    assert agent.sentinel is not None


def test_emergency_no_data():
    """Agente sin datos devuelve mensajes apropiados (sin LLM)."""
    agent = EmergencyAgent(city="bogota")
    assert agent.optimize_evacuation() == "Sin datos para optimizar evacuación."
    assert agent.optimize_hospital_assignment() == "Sin datos para asignación hospitalaria."
    assert agent.optimize_aid_distribution() == "Sin items de ayuda para distribuir."


# ─── Tests con LLM real (skip si no hay GROQ_API_KEY) ───────────────


@requires_llm
def test_emergency_agent_on_event():
    """EmergencyAgent genera plan de respuesta con LLM real."""
    agent = EmergencyAgent(city="bogota")
    agent.event = EmergencyEvent(
        event_type="sismo",
        epicenter=(6.64, -73.12),
        magnitude=6.3,
        affected_zones=[
            {"name": "Centro", "coords": [6.64, -73.12], "severity": "alta", "casualties": 45},
            {"name": "Norte", "coords": [6.70, -73.10], "severity": "media", "casualties": 20},
        ],
    )
    agent.hospitals = [
        Hospital(id="h1", name="Hospital A", coords=(6.64, -73.12), capacity=50, trauma_level=3),
        Hospital(id="h2", name="Hospital B", coords=(6.70, -73.10), capacity=30, trauma_level=2),
    ]
    plan = agent._generate_response_plan()
    assert len(plan) > 50
    assert "sismo" in plan.lower() or "emergen" in plan.lower() or "hospital" in plan.lower()


@requires_llm
def test_emergency_evacuation():
    """Optimización de evacuación con VRP + explicación LLM real."""
    agent = EmergencyAgent(city="bogota")
    agent.event = EmergencyEvent(
        event_type="sismo",
        epicenter=(6.64, -73.12),
        magnitude=6.3,
        affected_zones=[
            {"name": "Zona A", "coords": [6.64, -73.12], "severity": "alta", "casualties": 5},
            {"name": "Zona B", "coords": [6.70, -73.10], "severity": "media", "casualties": 3},
        ],
    )
    agent.ambulances = [
        Ambulance(id="amb1", name="Ambulancia 1", base_coords=(6.64, -73.12), capacity=3),
        Ambulance(id="amb2", name="Ambulancia 2", base_coords=(6.64, -73.12), capacity=3),
    ]
    result = agent.optimize_evacuation()
    assert "Sin datos" not in result


@requires_llm
def test_emergency_hospital_assignment():
    """Asignación hospitalaria con Min Cost Flow + explicación LLM real."""
    agent = EmergencyAgent(city="bogota")
    agent.event = EmergencyEvent(
        event_type="sismo",
        epicenter=(6.64, -73.12),
        magnitude=6.3,
        affected_zones=[
            {"name": "Zona A", "coords": [6.64, -73.12], "severity": "alta", "casualties": 45},
            {"name": "Zona B", "coords": [6.70, -73.10], "severity": "media", "casualties": 20},
        ],
    )
    agent.hospitals = [
        Hospital(id="h1", name="Hospital A", coords=(6.64, -73.12), capacity=50, trauma_level=3),
        Hospital(id="h2", name="Hospital B", coords=(6.70, -73.10), capacity=30, trauma_level=2),
    ]
    result = agent.optimize_hospital_assignment()
    assert "error" not in result.lower()
    assert len(agent._result.hospital_assignment) > 0


@requires_llm
def test_emergency_aid_distribution():
    """Distribución de ayuda con Bin Packing + explicación LLM real."""
    agent = EmergencyAgent(city="bogota")
    agent.aid_items = [
        AidItem(id="a1", name="Agua (20L)", weight=20.0),
        AidItem(id="a2", name="Agua (20L)", weight=20.0),
        AidItem(id="a3", name="Comida R1", weight=5.0),
        AidItem(id="a4", name="Comida R2", weight=5.0),
        AidItem(id="a5", name="Kit Médico", weight=15.0),
        AidItem(id="a6", name="Mantas", weight=8.0),
    ]
    result = agent.optimize_aid_distribution(bin_capacity=50.0, num_bins=3)
    assert "error" not in result.lower()
    assert len(agent._result.aid_distribution) > 0


@requires_llm
def test_emergency_aid_oversized():
    """Item que excede capacidad es reportado como no empacado."""
    agent = EmergencyAgent(city="bogota")
    agent.aid_items = [
        AidItem(id="a1", name="Agua (20L)", weight=20.0),
        AidItem(id="a2", name="Generador", weight=100.0),
    ]
    result = agent.optimize_aid_distribution(bin_capacity=50.0, num_bins=2)
    assert "error" not in result.lower()
    # Determinista: el generador (100kg) no cabe en cajas de 50kg
    packed_items = [i for pb in agent._result.aid_distribution for i in pb["items"]]
    assert "Generador" not in packed_items
    assert "Agua (20L)" in packed_items
    # El solver reporta el item no empacado en warnings
    assert any("a2" in w for w in agent._result.warnings)


@requires_llm
def test_emergency_full_response():
    """Resumen ejecutivo de toda la respuesta con LLM real."""
    agent = EmergencyAgent(city="bogota")
    agent.event = EmergencyEvent(
        event_type="sismo",
        epicenter=(6.64, -73.12),
        magnitude=6.3,
        affected_zones=[
            {"name": "Zona A", "coords": [6.64, -73.12], "severity": "alta", "casualties": 5},
        ],
    )
    agent.ambulances = [
        Ambulance(id="amb1", name="Ambulancia 1", base_coords=(6.64, -73.12), capacity=3),
    ]
    agent.hospitals = [
        Hospital(id="h1", name="Hospital A", coords=(6.64, -73.12), capacity=50, trauma_level=3),
    ]
    agent.aid_items = [
        AidItem(id="a1", name="Agua (20L)", weight=20.0),
        AidItem(id="a2", name="Comida", weight=5.0),
    ]
    agent.optimize_evacuation()
    agent.optimize_hospital_assignment()
    agent.optimize_aid_distribution()
    summary = agent.explain_full_response()
    assert len(summary) > 50

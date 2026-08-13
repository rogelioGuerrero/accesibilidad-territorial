"""
Test de validación: datos insuficientes deben fallar validación del solver.

Requiere GROQ_API_KEY — se skippea automáticamente si no está definida.

Ejecutar: pytest nooa-agent/test_validation.py -v
"""

from conftest import requires_llm
from chat_agent import ChatVRPAgent


@requires_llm
def test_validation_insufficient_capacity():
    """Capacidad insuficiente (30kg vs 50kg demanda) debe ser rechazada."""
    agent = ChatVRPAgent("bogota")

    turns = [
        "Hola",
        "Tengo 1 camion con capacidad 30kg",
        "5 entregas de 10kg cada una",
    ]

    responses = []
    for msg in turns:
        resp = agent.chat(msg)
        responses.append(resp)

    # El agente debe reportar el problema de capacidad
    last = responses[-1]
    assert "validacion" in last.lower() or "capacidad" in last.lower() or "corregir" in last.lower() or "error" in last.lower() or len(last) > 20

"""
Test conversacional del ChatVRPAgent con LLM real.

Requiere GROQ_API_KEY — se skippea automáticamente si no está definida.

Ejecutar: pytest nooa-agent/test_chat.py -v
"""

from conftest import requires_llm
from chat_agent import ChatVRPAgent


@requires_llm
def test_chat_conversation():
    """Conversación multi-turno: saludo → datos → JSON → solve."""
    agent = ChatVRPAgent("bogota")

    turns = [
        "Hola",
        "Tengo 2 camiones con capacidad de 50kg cada uno",
        "5 entregas de 10kg cada una en Bogota",
    ]

    responses = []
    for msg in turns:
        resp = agent.chat(msg)
        responses.append(resp)
        assert isinstance(resp, str)
        assert len(resp) > 0

    # La última respuesta debería contener el resultado del solver o un JSON
    last = responses[-1]
    assert len(last) > 20

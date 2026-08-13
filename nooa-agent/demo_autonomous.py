"""
Demo: Agentes autónomos con Groq + tool calling + human-in-the-loop.

Muestra dos agentes heredando de la misma clase base:
1. EmergencyAutonomousAgent — sismo M7.4 Chocó
2. InsuranceAutonomousAgent — reclamo de seguro por el mismo sismo

Ambos heredan de base_agent.AutonomousAgent:
- Mismo pipeline (detectar → proponer → aprobar → ejecutar → validar)
- Diferentes tools y prompts
- Cero código duplicado

Ejecutar: uv run python nooa-agent/demo_autonomous.py
"""

from emergency_autonomous import EmergencyAutonomousAgent
from insurance_autonomous import InsuranceAutonomousAgent

# ─── Datos del sismo real de hoy ────────────────────────────────────
EVENT_DATA = {
    "magnitude": 7.4,
    "epicenter": [5.0, -76.5],
    "location": "San José del Palmar, Chocó, Colombia",
    "date": "2026-08-10T07:34:00",
    "depth_km": 82,
    "zones": [
        {"name": "Pereira Centro", "lat": 4.8133, "lng": -75.6961, "casualties": 35},
        {"name": "Manizales", "lat": 5.0687, "lng": -75.5174, "casualties": 28},
        {"name": "Quibdó", "lat": 5.6916, "lng": -76.6583, "casualties": 29},
    ],
    "hospitals": [
        {"id": "h1", "name": "Hospital Universitario San Jorge", "coords": (4.8133, -75.6961), "capacity": 50, "trauma_level": 3},
        {"id": "h2", "name": "Clínica Confamiliar", "coords": (4.8073, -75.7012), "capacity": 20, "trauma_level": 2},
        {"id": "h3", "name": "Hospital Santa Mónica", "coords": (5.0687, -75.5174), "capacity": 30, "trauma_level": 2},
        {"id": "h4", "name": "Clínica Los Rosales", "coords": (5.0700, -75.5200), "capacity": 15, "trauma_level": 1},
    ],
    "ambulances": [
        {"id": f"amb-{i}", "name": f"Ambulancia {i}", "base_coords": (4.8133, -75.6961), "capacity": 8}
        for i in range(1, 16)
    ],
    "aid_items": [
        {"id": "a1", "name": "Agua 20L", "weight": 20},
        {"id": "a2", "name": "Comida 15kg", "weight": 15},
        {"id": "a3", "name": "Carpa 10kg", "weight": 10},
        {"id": "a4", "name": "Mantos 5kg", "weight": 5},
        {"id": "a5", "name": "Linternas 3kg", "weight": 3},
        {"id": "a6", "name": "Botiquín 8kg", "weight": 8},
        {"id": "a7", "name": "Medicamentos 12kg", "weight": 12},
        {"id": "a8", "name": "Cuerdas 6kg", "weight": 6},
    ],
}


# ─── Datos del reclamo de seguro ────────────────────────────────────
CLAIM_DATA = {
    "claim_id": "CLM-2026-0810-0042",
    "address": "Calle 42 #15-30, Pereira",
    "lat": 4.8133,
    "lng": -75.6961,
    "magnitude": 7.4,
    "damage_type": "daño estructural",
    "claim_amount": 85000000,
    "policy_holder": "Juan Pérez",
}


def demo_emergency(auto_approve: bool = True):
    """Demo del agente de emergencias."""
    print("""
╔════════════════════════════════════════════════════════════════════╗
║                                                                    ║
║  EmergencyAutonomousAgent(AutonomousAgent)                        ║
║  Sismo M7.4 — San José del Palmar, Chocó — 10 ago 2026           ║
║                                                                    ║
║  Hereda: detect_event, propose_actions, approve_and_execute,      ║
║         validate_plan, run_full_pipeline                          ║
║  Override: tools_schema, system_prompt, _execute_tool             ║
║                                                                    ║
╚════════════════════════════════════════════════════════════════════╝
    """)

    agent = EmergencyAutonomousAgent(city="bogota")
    results = agent.run_full_pipeline(EVENT_DATA, auto_approve=auto_approve)

    print("\n" + "═" * 60)
    print("  RESUMEN — EmergencyAgent")
    print("═" * 60)
    print(f"  Estado: {results.get('status', 'unknown')}")
    if "results" in results:
        for tool_name, tool_result in results["results"].items():
            if isinstance(tool_result, dict) and "error" not in tool_result:
                for k, v in tool_result.items():
                    if isinstance(v, list):
                        print(f"  {tool_name}: {k} = {len(v)} items")
                    elif k not in ("summary", "plan"):
                        print(f"  {tool_name}: {k} = {v}")
    print(f"  Tools ejecutados: {len(results.get('results', {}))}")
    print()


def demo_insurance(auto_approve: bool = True):
    """Demo del agente de seguros."""
    print("""
╔════════════════════════════════════════════════════════════════════╗
║                                                                    ║
║  InsuranceAutonomousAgent(AutonomousAgent)                        ║
║  Reclamo CLM-2026-0810-0042 — Pereira                             ║
║                                                                    ║
║  Hereda: detect_event, propose_actions, approve_and_execute,      ║
║         validate_plan, run_full_pipeline                          ║
║  Override: tools_schema, system_prompt, _execute_tool             ║
║                                                                    ║
║  Mismo motor. Diferente caso de uso. Cero código duplicado.       ║
║                                                                    ║
╚════════════════════════════════════════════════════════════════════╝
    """)

    agent = InsuranceAutonomousAgent()
    results = agent.run_full_pipeline(CLAIM_DATA, auto_approve=auto_approve)

    print("\n" + "═" * 60)
    print("  RESUMEN — InsuranceAgent")
    print("═" * 60)
    print(f"  Estado: {results.get('status', 'unknown')}")
    if "results" in results:
        for tool_name, tool_result in results["results"].items():
            if isinstance(tool_result, dict) and "error" not in tool_result:
                for k, v in tool_result.items():
                    if isinstance(v, list):
                        print(f"  {tool_name}: {k} = {len(v)} items")
                    else:
                        print(f"  {tool_name}: {k} = {v}")
    print(f"  Tools ejecutados: {len(results.get('results', {}))}")
    print()


def main():
    AUTO_APPROVE = True

    # Demo 1: Agente de emergencias
    demo_emergency(auto_approve=AUTO_APPROVE)

    # Demo 2: Agente de seguros (mismo motor, diferente caso de uso)
    demo_insurance(auto_approve=AUTO_APPROVE)

    print("═" * 60)
    print("  Dos agentes. Una clase base. Cero código duplicado.")
    print("  AutonomousAgent → EmergencyAutonomousAgent")
    print("  AutonomousAgent → InsuranceAutonomousAgent")
    print("  AutonomousAgent → MiningAutonomousAgent  (siguiente...)")
    print("═" * 60)


if __name__ == "__main__":
    main()

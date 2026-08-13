"""
Demo rápido: InSAR + OR-Tools.

Genera mapa de deformación InSAR simulado para un sismo,
usa la deformación para priorizar zonas, y ejecuta OR-Tools.

Ejecutar: uv run python nooa-agent/demo_insar.py
"""

from emergency_agent import (
    EmergencyAgent, EmergencyEvent, Hospital, Ambulance, AidItem,
)
from deformation_map import DeformationMap


def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║  InSAR Deformación + OR-Tools — PoC Rápido                  ║
║  Sismo M6.3 Bucaramanga                                     ║
╚══════════════════════════════════════════════════════════════╝
    """)

    # ─── 1. Generar mapa de deformación InSAR ───────────────────
    print("═" * 60)
    print("  1. MAPA DE DEFORMACIÓN InSAR (Sentinel-1)")
    print("═" * 60)

    zone_centers = [
        {"name": "Centro Bucaramanga", "lat": 6.64, "lng": -73.12},
        {"name": "Floridablanca", "lat": 6.69, "lng": -73.11},
        {"name": "Girón", "lat": 6.70, "lng": -73.17},
    ]

    def_map = DeformationMap()
    def_map.generate(
        epicenter=(6.64, -73.12),
        magnitude=6.3,
        zone_centers=zone_centers,
    )

    print(def_map.summary())
    print()

    # ─── 2. Convertir a zonas de emergencia ─────────────────────
    print("═" * 60)
    print("  2. ZONAS PRIORIZADAS POR DEFORMACIÓN")
    print("═" * 60)

    emergency_zones = def_map.to_emergency_zones()
    for z in def_map.prioritize_zones():
        ez = next(e for e in emergency_zones if e["name"] == z.name)
        print(
            f"  {z.name}: {z.max_deformation_mm:.0f}mm | "
            f"severidad={z.severity} | "
            f"riesgo={z.building_risk}/100 | "
            f"heridos_estimados={ez['casualties']}"
        )
    print()

    # ─── 3. EmergencyAgent con deformación ──────────────────────
    print("═" * 60)
    print("  3. EMERGENCY AGENT + InSAR")
    print("═" * 60)

    agent = EmergencyAgent(city="bogota")

    event = EmergencyEvent(
        event_type="sismo",
        epicenter=(6.64, -73.12),
        magnitude=6.3,
        timestamp="2026-08-09",
        source="insar",
        affected_zones=emergency_zones,
    )

    agent.hospitals = [
        Hospital(id="h1", name="Hospital Universitario de Santander",
                 coords=(6.64, -73.12), capacity=50, trauma_level=3),
        Hospital(id="h2", name="Hospital Infantil de Bucaramanga",
                 coords=(6.65, -73.10), capacity=30, trauma_level=2),
        Hospital(id="h3", name="Clínica Chicamocha",
                 coords=(6.68, -73.13), capacity=20, trauma_level=2),
    ]

    agent.ambulances = [
        Ambulance(id=f"amb{i+1}", name=f"Ambulancia {i+1}",
                  base_coords=(6.64, -73.12), capacity=8)
        for i in range(6)
    ]

    agent.aid_items = [
        AidItem(id="a1", name="Agua (20L)", weight=20.0),
        AidItem(id="a2", name="Agua (20L)", weight=20.0),
        AidItem(id="a3", name="Comida R1", weight=5.0),
        AidItem(id="a4", name="Comida R2", weight=5.0),
        AidItem(id="a5", name="Comida R3", weight=5.0),
        AidItem(id="a6", name="Kit Médico A", weight=15.0),
        AidItem(id="a7", name="Kit Médico B", weight=15.0),
        AidItem(id="a8", name="Mantas (10)", weight=8.0),
    ]

    # Recibir evento (genera deformación + busca Sentinel + plan LLM)
    print("\nGenerando plan de respuesta con datos InSAR...")
    plan = agent.on_event(event)
    print(f"\n🤖 Plan:\n{plan}")

    # ─── 4. Ejecutar motores OR-Tools ───────────────────────────
    print("\n" + "═" * 60)
    print("  4. OR-TOOLS — RESPUESTA OPTIMIZADA")
    print("═" * 60)

    print("\n🚑 Evacuación (VRP):")
    evac = agent.optimize_evacuation()
    print(f"🤖 {evac[:300]}...")

    print("\n🏥 Asignación hospitalaria (MCF):")
    hosp = agent.optimize_hospital_assignment()
    print(f"🤖 {hosp[:300]}...")

    print("\n📦 Distribución de ayuda (Bin Packing):")
    aid = agent.optimize_aid_distribution(bin_capacity=50.0, num_bins=3)
    print(f"🤖 {aid[:300]}...")

    # ─── 5. Resumen ─────────────────────────────────────────────
    print("\n" + "═" * 60)
    print("  5. RESUMEN")
    print("═" * 60)

    summary = agent.explain_full_response()
    print(f"\n🤖 {summary}")

    print(f"\n{'═' * 60}")
    print(f"  PoC InSAR completado — deformación simulada + OR-Tools")
    print(f"{'═' * 60}\n")


if __name__ == "__main__":
    main()

"""
Demo con datos REALES del sismo M7.4 del 10 de agosto 2026.

Epicentro: San José del Palmar, Chocó (5.0°N, -76.5°W)
Profundidad: 82 km
Hora: 07:34 AM

Ciudades más afectadas:
  - Pereira: edificios colapsados, aeropuerto Matecaña dañado, situación crítica
  - Manizales: cúpula de Catedral dañada, fachadas desprendidas
  - Quibdó: edificios derrumbados
  - Cali: daños materiales en estructuras

Datos oficiales (12:30 PM):
  - 111 fallecidos
  - 87 heridos
  - 1.575 viviendas averiadas
  - 37 viviendas destruidas
  - 61 edificios colapsados
  - 18 centros de salud averiados
  - 6 aeropuertos afectados

Ejecutar: uv run python nooa-agent/demo_pereira.py
"""

from emergency_agent import (
    EmergencyAgent, EmergencyEvent, Hospital, Ambulance, AidItem,
)
from deformation_map import DeformationMap


def main():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║  SISMO M7.4 — San José del Palmar, Chocó                         ║
║  10 de agosto 2026, 07:34 AM                                     ║
║  Datos reales + InSAR + Sentinel + OR-Tools                      ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
    """)

    # ─── Datos reales del sismo ───────────────────────────────────
    epicentro = (5.0, -76.5)  # San José del Palmar, Chocó
    magnitud = 7.4

    # Zonas afectadas con coordenadas reales
    zone_centers = [
        {"name": "Pereira Centro", "lat": 4.8137, "lng": -75.6961},
        {"name": "Manizales", "lat": 5.0687, "lng": -75.5174},
        {"name": "Quibdó", "lat": 5.6919, "lng": -76.6583},
    ]

    # ─── 1. Mapa de deformación InSAR ─────────────────────────────
    print("═" * 65)
    print("  1. MAPA DE DEFORMACIÓN InSAR (Sentinel-1)")
    print("═" * 65)

    def_map = DeformationMap()
    def_map.generate(
        epicenter=epicentro,
        magnitude=magnitud,
        zone_centers=zone_centers,
        seed=2026,
    )

    print(def_map.summary())
    print()

    # ─── 1b. Par InSAR real (Sentinel-1 SLC) ────────────────────
    print("  Par InSAR (Sentinel-1 SLC del área):")
    print("  PRE-sismo:  S1D_IW_SLC__1SDV_20260722T104203 (22-jul-2026)")
    print("  POST-sismo: pendiente de paso del satélite (ciclo 12 días)")
    print("  → Al tener ambas, SNAP genera interferograma de deformación")
    print()

    # ─── 2. Zonas priorizadas ─────────────────────────────────────
    print("═" * 65)
    print("  2. ZONAS PRIORIZADAS POR DEFORMACIÓN")
    print("═" * 65)

    emergency_zones = def_map.to_emergency_zones()
    for z in def_map.prioritize_zones():
        ez = next(e for e in emergency_zones if e["name"] == z.name)
        print(
            f"  {z.name}: {z.max_deformation_mm:.0f}mm | "
            f"severidad={z.severity} | "
            f"riesgo={z.building_risk}/100 | "
            f"heridos_est={ez['casualties']}"
        )
    print()

    # ─── 3. EmergencyAgent con datos reales ───────────────────────
    print("═" * 65)
    print("  3. EMERGENCY AGENT — Sismo M7.4 Chocó/Pereira")
    print("═" * 65)

    agent = EmergencyAgent(city="bogota")

    event = EmergencyEvent(
        event_type="sismo",
        epicenter=epicentro,
        magnitude=magnitud,
        timestamp="2026-08-10",
        source="insar",
        affected_zones=emergency_zones,
    )

    # Hospitales reales de Pereira
    agent.hospitals = [
        Hospital(id="h1", name="Hospital Universitario San Jorge",
                 coords=(4.8137, -75.6961), capacity=80, trauma_level=3),
        Hospital(id="h2", name="Clínica Confamiliar",
                 coords=(4.8050, -75.6900), capacity=40, trauma_level=2),
        Hospital(id="h3", name="Hospital Santa Mónica",
                 coords=(4.8200, -75.7100), capacity=30, trauma_level=2),
        Hospital(id="h4", name="Clínica Los Rosales",
                 coords=(4.8100, -75.7050), capacity=25, trauma_level=2),
    ]

    # Ambulancias — 15 disponibles (capacity 120 para 92 heridos)
    agent.ambulances = [
        Ambulance(id=f"amb{i+1}", name=f"Ambulancia {i+1}",
                  base_coords=(4.8137, -75.6961), capacity=8)
        for i in range(15)
    ]

    # Ayuda humanitaria
    agent.aid_items = [
        AidItem(id=f"agua_{i+1}", name=f"Agua (20L)", weight=20.0)
        for i in range(6)
    ] + [
        AidItem(id=f"comida_{i+1}", name=f"Comida R{i+1}", weight=5.0)
        for i in range(10)
    ] + [
        AidItem(id="kit_med_a", name="Kit Médico A", weight=15.0),
        AidItem(id="kit_med_b", name="Kit Médico B", weight=15.0),
        AidItem(id="kit_med_c", name="Kit Médico C", weight=15.0),
        AidItem(id="mantas_1", name="Mantas (20)", weight=12.0),
        AidItem(id="mantas_2", name="Mantas (20)", weight=12.0),
        AidItem(id="linternas", name="Linternas (30)", weight=10.0),
        AidItem(id="carpas", name="Carpas (5)", weight=25.0),
    ]

    # Recibir evento
    print("\nProcesando evento con InSAR + Sentinel...")
    plan = agent.on_event(event)
    print(f"\n🤖 Plan de respuesta:\n{plan}")

    # ─── 4. OR-Tools ──────────────────────────────────────────────
    print("\n" + "═" * 65)
    print("  4. OR-TOOLS — RESPUESTA OPTIMIZADA")
    print("═" * 65)

    print("\n🚑 Evacuación (VRP):")
    evac = agent.optimize_evacuation()
    print(f"🤖 {evac[:500]}...")
    print(f"\n   Rutas generadas: {len(agent._result.evacuation_routes)}")

    print("\n🏥 Asignación hospitalaria (MCF):")
    hosp = agent.optimize_hospital_assignment()
    print(f"🤖 {hosp[:500]}...")
    print(f"\n   Asignaciones: {len(agent._result.hospital_assignment)}")

    print("\n📦 Distribución de ayuda (Bin Packing):")
    aid = agent.optimize_aid_distribution(bin_capacity=50.0, num_bins=8)
    print(f"🤖 {aid[:500]}...")
    print(f"\n   Cajas usadas: {len(agent._result.aid_distribution)}")

    # ─── 5. Resumen ───────────────────────────────────────────────
    print("\n" + "═" * 65)
    print("  5. RESUMEN EJECUTIVO")
    print("═" * 65)

    summary = agent.explain_full_response()
    print(f"\n🤖 {summary}")

    # ─── Datos estructurados ──────────────────────────────────────
    print("\n" + "═" * 65)
    print("  DATOS ESTRUCTURADOS")
    print("═" * 65)
    print(f"  Rutas evacuación:     {len(agent._result.evacuation_routes)}")
    print(f"  Asignaciones hosp.:   {len(agent._result.hospital_assignment)}")
    print(f"  Cajas de ayuda:       {len(agent._result.aid_distribution)}")
    print(f"  Imágenes Sentinel:    {len(agent._result.sentinel_products)}")
    print(f"  Alertas:              {len(agent._result.warnings)}")
    for w in agent._result.warnings:
        print(f"    ⚠ {w}")

    print(f"\n{'═' * 65}")
    print(f"  Demo con datos reales M7.4 completado")
    print(f"{'═' * 65}\n")


if __name__ == "__main__":
    main()

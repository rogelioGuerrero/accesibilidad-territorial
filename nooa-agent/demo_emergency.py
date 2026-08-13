"""
Demo de EmergencyAgent — escenario de sismo en Colombia.

Simula el sismo de ayer: magnitud 6.3 cerca de Bucaramanga.
El agente recibe el evento, busca imagenes Sentinel (si hay credenciales),
y ejecuta los 3 motores: evacuacion, asignacion hospitalaria, distribucion de ayuda.

Ejecutar: uv run python nooa-agent/demo_emergency.py
"""

import time

from emergency_agent import (
    EmergencyAgent, EmergencyEvent, Hospital, Ambulance, AidItem,
)


def separator(title: str):
    print(f"\n{'═' * 70}")
    print(f"  {title}")
    print(f"{'═' * 70}\n")


def main():
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║                                                                      ║
║   EmergencyAgent — Respuesta a Sismo con OR-Tools + Sentinel         ║
║                                                                      ║
║   Escenario: Magnitud 6.3 cerca de Bucaramanga, Colombia             ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
    """)

    # ─── Crear agente ───────────────────────────────────────────────
    agent = EmergencyAgent(city="bogota")

    # ─── Definir evento ─────────────────────────────────────────────
    event = EmergencyEvent(
        event_type="sismo",
        epicenter=(6.64, -73.12),  # Bucaramanga area
        magnitude=6.3,
        timestamp="2026-08-09",
        source="manual",
        affected_zones=[
            {
                "name": "Centro Bucaramanga",
                "coords": [6.64, -73.12],
                "severity": "alta",
                "casualties": 24,
                "blocked_roads": 3,
            },
            {
                "name": "Floridablanca",
                "coords": [6.69, -73.11],
                "severity": "media",
                "casualties": 16,
                "blocked_roads": 1,
            },
            {
                "name": "Girón",
                "coords": [6.70, -73.17],
                "severity": "media",
                "casualties": 8,
                "blocked_roads": 2,
            },
        ],
    )
    agent.event = event

    # ─── Definir recursos ───────────────────────────────────────────
    agent.hospitals = [
        Hospital(id="h1", name="Hospital Universitario de Santander",
                 coords=(6.64, -73.12), capacity=50, trauma_level=3),
        Hospital(id="h2", name="Hospital Infantil de Bucaramanga",
                 coords=(6.65, -73.10), capacity=30, trauma_level=2),
        Hospital(id="h3", name="Clínica Chicamocha",
                 coords=(6.68, -73.13), capacity=20, trauma_level=2),
    ]

    agent.ambulances = [
        Ambulance(id="amb1", name="Ambulancia 1", base_coords=(6.64, -73.12), capacity=8),
        Ambulance(id="amb2", name="Ambulancia 2", base_coords=(6.64, -73.12), capacity=8),
        Ambulance(id="amb3", name="Ambulancia 3", base_coords=(6.64, -73.12), capacity=8),
        Ambulance(id="amb4", name="Ambulancia 4", base_coords=(6.64, -73.12), capacity=8),
        Ambulance(id="amb5", name="Ambulancia 5", base_coords=(6.64, -73.12), capacity=8),
        Ambulance(id="amb6", name="Ambulancia 6", base_coords=(6.64, -73.12), capacity=8),
    ]

    agent.aid_items = [
        AidItem(id="a1", name="Agua (20L)", weight=20.0),
        AidItem(id="a2", name="Agua (20L)", weight=20.0),
        AidItem(id="a3", name="Comida R1", weight=5.0),
        AidItem(id="a4", name="Comida R2", weight=5.0),
        AidItem(id="a5", name="Comida R3", weight=5.0),
        AidItem(id="a6", name="Comida R4", weight=5.0),
        AidItem(id="a7", name="Comida R5", weight=5.0),
        AidItem(id="a8", name="Kit Médico A", weight=15.0),
        AidItem(id="a9", name="Kit Médico B", weight=15.0),
        AidItem(id="a10", name="Mantas (10)", weight=8.0),
        AidItem(id="a11", name="Mantas (10)", weight=8.0),
        AidItem(id="a12", name="Linternas (20)", weight=10.0),
    ]

    # ─── Paso 1: Recibir evento y generar plan ──────────────────────
    separator("PASO 1: Recepción del evento")
    print(f"Evento: Sismo M{event.magnitude} en {event.epicenter}")
    print(f"Zonas afectadas: {len(event.affected_zones)}")
    print(f"Total heridos estimados: {sum(z['casualties'] for z in event.affected_zones)}")
    print(f"Hospitales disponibles: {len(agent.hospitals)} ({sum(h.capacity for h in agent.hospitals)} camas)")
    print(f"Ambulancias: {len(agent.ambulances)}")
    print(f"Items de ayuda: {len(agent.aid_items)} ({sum(a.weight for a in agent.aid_items)}kg)")
    print()

    # Buscar Sentinel si hay credenciales
    if agent.sentinel._check_credentials():
        print("Buscando imágenes Sentinel...")
        agent._fetch_sentinel_imagery()
        if agent._result.sentinel_products:
            print(f"  Encontradas: {len(agent._result.sentinel_products)} imágenes")
            for sp in agent._result.sentinel_products:
                print(f"    - {sp['name']} ({sp['collection']})")
        else:
            print("  No se encontraron imágenes recientes")
    else:
        print("Sin credenciales CDSE — saltando búsqueda Sentinel")
        print("  (Agrega CDSE_USERNAME y CDSE_PASSWORD al .env para activar)")
    print()

    print("Generando plan de respuesta...")
    plan = agent._generate_response_plan()
    print(f"\n🤖 Plan:\n{plan}")

    # ─── Paso 2: Evacuacion (VRP) ───────────────────────────────────
    separator("PASO 2: Evacuación de heridos (VRP)")
    print("Optimizando rutas de ambulancias...")
    evac_result = agent.optimize_evacuation()
    print(f"\n🤖 {evac_result}")

    # ─── Paso 3: Asignacion hospitalaria (MCF) ──────────────────────
    separator("PASO 3: Asignación hospitalaria (Min Cost Flow)")
    print("Asignando heridos a hospitales...")
    hosp_result = agent.optimize_hospital_assignment()
    print(f"\n🤖 {hosp_result}")

    # ─── Paso 4: Distribucion de ayuda (Bin Packing) ────────────────
    separator("PASO 4: Distribución de ayuda (Bin Packing)")
    print("Empacando ayuda humanitaria...")
    aid_result = agent.optimize_aid_distribution(bin_capacity=50.0, num_bins=5)
    print(f"\n🤖 {aid_result}")

    # ─── Paso 5: Resumen ejecutivo ──────────────────────────────────
    separator("PASO 5: Resumen ejecutivo")
    print("Generando resumen...")
    summary = agent.explain_full_response()
    print(f"\n🤖 {summary}")

    # ─── Resultado estructurado ─────────────────────────────────────
    separator("DATOS ESTRUCTURADOS (para integración)")
    print(f"Rutas de evacuación: {len(agent._result.evacuation_routes)}")
    print(f"Asignaciones hospitalarias: {len(agent._result.hospital_assignment)}")
    print(f"Cajas de ayuda: {len(agent._result.aid_distribution)}")
    print(f"Imágenes Sentinel: {len(agent._result.sentinel_products)}")
    print(f"Alertas: {len(agent._result.warnings)}")
    for w in agent._result.warnings:
        print(f"  ⚠ {w}")

    print(f"\n{'═' * 70}")
    print("  Demo completada — EmergencyAgent con POO + OR-Tools + Sentinel")
    print(f"{'═' * 70}\n")


if __name__ == "__main__":
    main()

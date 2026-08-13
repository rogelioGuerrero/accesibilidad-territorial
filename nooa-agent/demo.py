"""
Demo automático para clientes — muestra los 3 motores sin interacción.
Ejecutar: uv run python nooa-agent/demo.py

Ideal para una presentación: corre los 3 casos de uso en secuencia
y muestra cómo el agente conversa, resuelve y explica.
"""

import time

from multi_agent import MultiEngineAgent


def separator(title: str):
    print(f"\n{'═' * 70}")
    print(f"  {title}")
    print(f"{'═' * 70}\n")


def demo_vrp():
    """Demo: Rutas de entrega."""
    separator("DEMO 1: Rutas de Entrega (VRP)")
    print("Caso: E-commerce con 2 camiones en Bogotá, 5 entregas de 10kg cada una.")
    print()

    agent = MultiEngineAgent("bogota")
    agent.motor_elegido = 1

    user_text = "Tengo 2 camiones con capacidad de 50kg cada uno y 5 entregas de 10kg cada una en Bogotá"
    print(f"👤 Usuario: {user_text}\n")
    print("🤖 Procesando...\n")

    result = agent.process_user_response(user_text)
    print(result)


def demo_bin_packing():
    """Demo: Empaquetado."""
    separator("DEMO 2: Empaquetado de Productos (Bin Packing)")
    print("Caso: Warehouse con 10 productos de 5kg y 3 cajas de 20kg.")
    print()

    agent = MultiEngineAgent("bogota")
    agent.motor_elegido = 2

    user_text = "Tengo 10 productos de 5kg cada uno y 3 cajas con capacidad de 20kg cada una"
    print(f"👤 Usuario: {user_text}\n")
    print("🤖 Procesando...\n")

    result = agent.process_user_response(user_text)
    print(result)


def demo_school():
    """Demo: Asignación escolar."""
    separator("DEMO 3: Asignación Escolar (Min Cost Flow)")
    print("Caso: Municipio con 3 barrios (40, 30, 50 niños) y 2 escuelas (60 y 70 cupos).")
    print()

    agent = MultiEngineAgent("bogota")
    agent.motor_elegido = 3

    user_text = "3 barrios con 40, 30 y 50 niños respectivamente. 2 escuelas con capacidad de 60 y 70 cupos"
    print(f"👤 Usuario: {user_text}\n")
    print("🤖 Procesando...\n")

    result = agent.process_user_response(user_text)
    print(result)


def main():
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║                                                                      ║
║   Agente Multi-Motor OR-Tools                                        ║
║   VRP · Bin Packing · Asignación Escolar                             ║
║                                                                      ║
║   Demo automático — 3 casos de uso en menos de 2 minutos             ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
    """)

    demos = [
        ("VRP", demo_vrp),
        ("Bin Packing", demo_bin_packing),
        ("Asignación Escolar", demo_school),
    ]

    for name, fn in demos:
        try:
            fn()
        except Exception as e:
            print(f"  ❌ Error en demo {name}: {e}")
        time.sleep(1)

    separator("FIN DEL DEMO")
    print("""
  Resumen de capacidades:
  
  1. VRP — Rutas de entrega optimizadas con OR-Tools
     • Múltiples vehículos con capacidad
     • Matrices reales de distancia (OpenRouteService)
     • Ventanas de tiempo, pickup-delivery, skills
  
  2. Bin Packing — Empaquetado óptimo
     • Minimiza contenedores usados
     • Best Fit Decreasing con OR-Tools
     • Detecta items que no caben
  
  3. Asignación Escolar — Min Cost Flow
     • Asigna niños a escuelas minimizando distancia
     • Respeta capacidad de cada escuela
     • Detecta déficit de cupos
  
  Todos los motores:
    ✓ Reciben entrada en lenguaje natural (español)
    ✓ Validan antes de resolver
    ✓ Explican el resultado en español natural
    ✓ Usan OR-Tools (Google) como motor de optimización
    ✓ LLM: Groq free tier (Llama 3.3 70B)
    """)


if __name__ == "__main__":
    main()

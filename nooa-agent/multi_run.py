"""
Demo interactivo del agente multi-motor.
Ejecutar: uv run python nooa-agent/multi_run.py
"""

from multi_agent import MultiEngineAgent


def main():
    print("=" * 70)
    print("  Agente Multi-Motor OR-Tools (filosofía NOOA)")
    print("  VRP · Bin Packing · Asignación Escolar")
    print("=" * 70)

    city = input("\nCiudad base (bogota/madrid) [bogota]: ").strip().lower() or "bogota"
    agent = MultiEngineAgent(city=city)
    print(f"\nCiudad: {city} | {len(agent._coords)} puntos disponibles\n")

    while True:
        # Mostrar menu
        print(agent.show_menu())
        choice = input("> ").strip()

        if choice.lower() in ("salir", "exit", "quit"):
            print("\n¡Hasta luego!")
            break

        # Seleccionar motor
        response = agent.select_motor(choice)
        print(f"\n{response}\n")

        if agent.motor_elegido is None:
            continue

        # Recolectar info del usuario
        print("Describe tu problema (puedes escribir todo en una frase):")
        user_text = input("> ").strip()

        if not user_text:
            print("No se ingresó nada. Volviendo al menú.\n")
            agent.motor_elegido = None
            continue

        # Procesar
        print("\nProcesando...\n")
        result = agent.process_user_response(user_text)

        print("─" * 70)
        print("RESULTADO:")
        print("─" * 70)
        print(result)
        print("─" * 70)
        print()

        # Reset para siguiente iteracion
        agent.motor_elegido = None


if __name__ == "__main__":
    main()

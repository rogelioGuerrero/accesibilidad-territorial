"""
Script interactivo para probar el agente VRP.
Ejecutar: uv run python nooa-agent/run.py
"""

from agent import VRPAgent


EXAMPLES = [
    "Tengo 1 camion con capacidad 100kg. 5 entregas de 10kg cada una en Bogota.",
    "Tengo 2 camiones con capacidad 50kg cada uno. 5 entregas de 10kg cada una.",
    "Tengo 1 camion con capacidad 200kg y 14 entregas de 10kg en Madrid.",
]


def main():
    print("=" * 70)
    print("  Agente VRP con LiteLLM + OR-Tools")
    print("  Escribe tu problema en espanol o usa un ejemplo.")
    print("=" * 70)

    city = input("\nCiudad (bogota/madrid) [bogota]: ").strip().lower() or "bogota"
    agent = VRPAgent(city=city)
    print(f"\nAgente listo. {len(agent._coords)} puntos disponibles en {city}.\n")

    print("Ejemplos:")
    for i, ex in enumerate(EXAMPLES, 1):
        print(f"  {i}. {ex}")
    print("  0. Escribir mi propio problema")
    print()

    choice = input("Elige opcion [1]: ").strip() or "1"

    if choice in ("1", "2", "3"):
        user_input = EXAMPLES[int(choice) - 1]
    else:
        user_input = input("\nDescribe tu problema: ").strip()

    if not user_input:
        print("No se ingreso nada. Saliendo.")
        return

    print(f"\n{'─' * 70}")
    print(f"PROBLEMA: {user_input}")
    print(f"{'─' * 70}")

    print("\nResolviendo...\n")
    answer = agent.solve_from_text(user_input)

    print(f"{'─' * 70}")
    print("RESPUESTA:")
    print(f"{'─' * 70}")
    print(answer)
    print(f"{'─' * 70}")


if __name__ == "__main__":
    main()

"""
Chat interactivo para el agente VRP conversacional.
Ejecutar: uv run python nooa-agent/chat_run.py
"""

from chat_agent import ChatVRPAgent


def main():
    print("=" * 70)
    print("  Chat VRP - Agente conversacional")
    print("  Escribe tu problema de rutas en espanol.")
    print("  Comandos: 'salir' para terminar, 'reset' para nueva conversacion.")
    print("=" * 70)

    city = input("\nCiudad (bogota/madrid) [bogota]: ").strip().lower() or "bogota"
    agent = ChatVRPAgent(city=city)
    print(f"\nAgente listo. {len(agent._coords)} puntos disponibles en {city}.\n")

    # Primer mensaje del agente
    greeting = agent.chat("Hola")
    print(f"Agente: {greeting}\n")

    while True:
        user_input = input("Tu: ").strip()
        if not user_input:
            continue
        if user_input.lower() in ("salir", "exit", "quit"):
            print("\nHasta luego!")
            break
        if user_input.lower() == "reset":
            agent.reset()
            greeting = agent.chat("Hola")
            print(f"\nAgente: {greeting}\n")
            continue

        print()
        response = agent.chat(user_input)
        print(f"Agente: {response}\n")


if __name__ == "__main__":
    main()

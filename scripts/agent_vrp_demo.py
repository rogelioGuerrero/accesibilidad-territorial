"""
Agente VRP con tool calling usando Groq LLM.

El agente recibe pedidos en lenguaje natural, los geocodifica,
arma el payload, llama al solver, y devuelve rutas optimizadas con costos.

Solo la matriz es cacheada (Madrid 15x15). Todo lo demás es real:
- LLM: Groq gpt-oss-120b
- Geocoding: Nominatim (OpenStreetMap)
- Solver: OR-Tools con matriz ORS real cacheada

Ejecutar: python scripts/agent_vrp_demo.py
"""

import json
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from vrp_solver.models import (
    Location,
    LocationType,
    OptimizeRequest,
    SolverConfig,
    Vehicle,
)
from vrp_solver.solver import VRPSolver

# ═══════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
if not GROQ_API_KEY:
    print("ERROR: GROQ_API_KEY no encontrada en .env")
    sys.exit(1)

MODEL = "openai/gpt-oss-120b"
FALLBACK_MODEL = "openai/gpt-oss-20b"

FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures"
MATRIX_PATH = FIXTURES_DIR / "matrix_madrid_15.json"
COORDS_PATH = FIXTURES_DIR / "coords_madrid_15.json"

# Coords reales de Madrid (del fixture)
with open(COORDS_PATH) as f:
    MADRID_COORDS = [tuple(c) for c in json.load(f)["coords"]]

# Depot es el primer nodo
DEPOT_COORDS = MADRID_COORDS[0]

# ═══════════════════════════════════════════════════════════════════════════
# ESTADO DEL AGENTE
# ═══════════════════════════════════════════════════════════════════════════

orders: list[dict] = []


# ═══════════════════════════════════════════════════════════════════════════
# TOOLS — funciones reales que el LLM puede llamar
# ═══════════════════════════════════════════════════════════════════════════

def geocode(address: str) -> dict:
    """Geocodifica una dirección usando Nominatim (OpenStreetMap). Gratis, sin API key."""
    try:
        response = httpx.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": address,
                "format": "json",
                "limit": 1,
                "countrycodes": "es",
            },
            headers={"User-Agent": "VRP-Agent-Demo/1.0"},
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        if not data:
            return {"ok": False, "error": f"No se encontró: {address}"}
        result = data[0]
        return {
            "ok": True,
            "lat": float(result["lat"]),
            "lng": float(result["lon"]),
            "display_name": result["display_name"],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def add_order(order_id: str, lat: float, lng: float, weight: float, priority: str) -> dict:
    """Agrega un pedido a la lista de órdenes pendientes."""
    orders.append({
        "id": order_id,
        "lat": lat,
        "lng": lng,
        "weight": weight,
        "priority": priority,
    })
    return {"ok": True, "order_id": order_id, "total_orders": len(orders)}


def optimize(num_vehicles: int = 2, weight_capacity: float = 100.0) -> dict:
    """
    Optimiza las rutas con los pedidos acumulados.
    Usa la matriz ORS real cacheada de Madrid.
    """
    if not orders:
        return {"ok": False, "error": "No hay pedidos para optimizar"}

    # Mapear cada order a la coord más cercana del fixture de Madrid
    # (porque la matriz cacheada es de 15 puntos fijos)
    used_indices = set()
    locations = [
        Location(id="depot", name="Depósito Madrid", coords=DEPOT_COORDS, type=LocationType.depot)
    ]

    for order in orders:
        # Buscar la coord más cercana del fixture
        min_dist = float("inf")
        best_idx = 0
        for i, coord in enumerate(MADRID_COORDS[1:], 1):
            if i in used_indices:
                continue
            dist = (coord[0] - order["lat"]) ** 2 + (coord[1] - order["lng"]) ** 2
            if dist < min_dist:
                min_dist = dist
                best_idx = i

        used_indices.add(best_idx)
        coord = MADRID_COORDS[best_idx]
        locations.append(Location(
            id=order["id"],
            name=f"Entrega {order['id']}",
            coords=coord,
            type=LocationType.delivery,
            weight_demand=order["weight"],
            priority=order["priority"],
        ))

    vehicles = [
        Vehicle(
            id=f"veh_{i+1}",
            name=f"Camión {i+1}",
            start_location_id="depot",
            end_location_id="depot",
            weight_capacity=weight_capacity,
            fixed_cost=50.0,
            cost_per_km=2.5,
            cost_per_hour=20.0,
            cost_per_stop=3.0,
        )
        for i in range(num_vehicles)
    ]

    request = OptimizeRequest(
        locations=locations,
        vehicles=vehicles,
        config=SolverConfig(
            time_limit_seconds=10,
            optimize_by="cost",
        ),
    )

    solver = VRPSolver.from_request(
        request,
        matrix_provider="cached",
        matrix_path=str(MATRIX_PATH),
    )

    result = solver.solve()

    if result.errors:
        return {"ok": False, "error": str(result.errors)}

    routes_data = []
    for route in result.routes:
        route_info = {
            "vehicle": route.vehicle_name or route.vehicle_id,
            "stops": route.total_stops,
            "distance_km": round(route.total_distance / 1000, 2),
            "duration_min": round(route.total_duration / 60, 1),
            "cost": route.cost.model_dump() if route.cost else None,
            "sequence": [stop.location_id for stop in route.stops],
        }
        routes_data.append(route_info)

    return {
        "ok": True,
        "routes": routes_data,
        "statistics": {
            "vehicles_used": result.statistics.vehicles_used,
            "nodes_assigned": result.statistics.nodes_assigned,
            "total_distance_km": round(result.statistics.total_distance / 1000, 2),
            "total_duration_min": round(result.statistics.total_duration / 60, 1),
            "total_cost": result.statistics.total_cost,
        },
    }


def send_to_drivers(routes: list[dict]) -> dict:
    """Simula el envío de rutas a los choferes via PWA."""
    for route in routes:
        print(f"   📱 PWA → {route['vehicle']}: {route['stops']} paradas, {route['distance_km']}km, ETA {route['duration_min']}min")
    return {"ok": True, "drivers_notified": len(routes)}


# ═══════════════════════════════════════════════════════════════════════════
# TOOL DEFINITIONS PARA GROQ (formato OpenAI)
# ═══════════════════════════════════════════════════════════════════════════

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "geocode",
            "description": "Geocodifica una dirección postal a coordenadas lat/lng. Usa OpenStreetMap Nominatim.",
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {
                        "type": "string",
                        "description": "Dirección postal completa. Ej: 'Gran Vía 45, Madrid'",
                    },
                },
                "required": ["address"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_order",
            "description": "Agrega un pedido geocodificado a la lista de órdenes pendientes para optimización.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "ID único del pedido. Ej: 'ORD-001'"},
                    "lat": {"type": "number", "description": "Latitud geocodificada"},
                    "lng": {"type": "number", "description": "Longitud geocodificada"},
                    "weight": {"type": "number", "description": "Peso del paquete en kg. Default 15."},
                    "priority": {"type": "string", "enum": ["H", "M", "L"], "description": "Prioridad: High, Medium, Low. Default M."},
                },
                "required": ["order_id", "lat", "lng"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "optimize",
            "description": "Optimiza las rutas con los pedidos acumulados. Llama al solver VRP con matriz real de Madrid. Devuelve rutas, distancias, tiempos y costos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "num_vehicles": {"type": "integer", "description": "Número de vehículos disponibles. Default 2."},
                    "weight_capacity": {"type": "number", "description": "Capacidad de peso por vehículo en kg. Default 100."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_to_drivers",
            "description": "Envía las rutas optimizadas a los choferes via PWA.",
            "parameters": {
                "type": "object",
                "properties": {
                    "routes": {"type": "array", "description": "Lista de rutas devuelta por optimize()"},
                },
                "required": ["routes"],
            },
        },
    },
]

# Mapa de funciones
TOOL_FUNCTIONS = {
    "geocode": geocode,
    "add_order": add_order,
    "optimize": optimize,
    "send_to_drivers": send_to_drivers,
}


# ═══════════════════════════════════════════════════════════════════════════
# AGENTE — loop de tool calling
# ═══════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """Eres un agente de logística autónomo especializado en optimización de rutas de última milla (last-mile delivery).

Tu trabajo:
1. Recibir pedidos del usuario (direcciones, pesos, prioridades)
2. Geocodificar cada dirección con la tool `geocode`
3. Agregar cada pedido con `add_order`
4. Cuando tengas todos los pedidos, optimizar con `optimize`
5. Enviar las rutas a los choferes con `send_to_drivers`

Reglas:
- Geocodifica UNA dirección a la vez
- Después de geocodificar, agrega el pedido inmediatamente con add_order
- Cuando el usuario diga "optimiza" o tengas todos los pedidos, llama optimize
- Siempre envía a choferes después de optimizar
- Reporta costos y distancias al usuario
- Sé conciso pero claro. Usa emojis apropiados.
- Si una dirección no se encuentra, informa al usuario y pide aclaración
"""


def run_agent(user_message: str):
    """Ejecuta el loop de tool calling con Groq."""
    client = Groq(api_key=GROQ_API_KEY)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    print(f"\n{'='*70}")
    print(f"👤 Usuario: {user_message}")
    print(f"{'='*70}")

    for step in range(15):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                max_tokens=4096,
                temperature=0.1,
            )
        except Exception as e:
            print(f"⚠️ Error con {MODEL}, intentando {FALLBACK_MODEL}...")
            try:
                response = client.chat.completions.create(
                    model=FALLBACK_MODEL,
                    messages=messages,
                    tools=TOOLS,
                    tool_choice="auto",
                    max_tokens=4096,
                    temperature=0.1,
                )
            except Exception as e2:
                print(f"❌ Error fatal: {e2}")
                return

        msg = response.choices[0].message

        # Si el LLM quiere llamar tools
        if msg.tool_calls:
            assistant_msg = {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            }
            messages.append(assistant_msg)

            for tc in msg.tool_calls:
                fn_name = tc.function.name
                fn_args = json.loads(tc.function.arguments)

                print(f"\n🤖 Agente llama: {fn_name}({json.dumps(fn_args, ensure_ascii=False)[:100]})")

                # Ejecutar la función real
                result = TOOL_FUNCTIONS[fn_name](**fn_args)

                print(f"   → {json.dumps(result, ensure_ascii=False)[:150]}")

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })

        # Si el LLM responde con texto (sin tools)
        if msg.content and not msg.tool_calls:
            print(f"\n🤖 Agente: {msg.content}")
            messages.append({"role": "assistant", "content": msg.content})
            break

        # Si no hay ni content ni tool_calls, salimos
        if not msg.content and not msg.tool_calls:
            break

    print(f"\n{'='*70}")
    print(f"Pedidos procesados: {len(orders)}")
    print(f"{'='*70}\n")


# ═══════════════════════════════════════════════════════════════════════════
# SIMULACIÓN
# ═══════════════════════════════════════════════════════════════════════════

SCENARIOS = [
    {
        "name": "Demo: 3 entregas en Madrid",
        "message": """Tengo 3 entregas urgentes en Madrid:
1. Gran Vía 45, Madrid — 20kg, prioridad alta
2. Plaza Mayor, Madrid — 15kg, prioridad media
3. Calle Alcalá 100, Madrid — 10kg, prioridad media

Optimiza con 2 vehículos y envíalo a los choferes.""",
    },
    {
        "name": "Demo: 5 entregas con prioridades mixtas",
        "message": """Necesito despachar 5 pedidos en Madrid:
1. Puerta del Sol, Madrid — 25kg, alta
2. Paseo de la Castellana 200, Madrid — 30kg, alta
3. Atocha, Madrid — 15kg, media
4. Plaza de España, Madrid — 10kg, baja
5. Barajas, Madrid — 18kg, media

Tengo 2 camiones de 100kg cada uno. Optimiza y manda a los choferes.""",
    },
]


def main():
    print("=" * 70)
    print("AGENTE VRP — Tool Calling con Groq LLM")
    print(f"Modelo: {MODEL}")
    print(f"Matriz: Madrid 15x15 (ORS cacheada)")
    print(f"Geocoding: Nominatim (real)")
    print(f"Solver: OR-Tools (real)")
    print("=" * 70)

    for scenario in SCENARIOS:
        print(f"\n{'#'*70}")
        print(f"# ESCENARIO: {scenario['name']}")
        print(f"{'#'*70}")

        # Reset orders
        orders.clear()

        run_agent(scenario["message"])

        # Pausa entre escenarios
        time.sleep(3)

    print("\n" + "=" * 70)
    print("SIMULACIÓN COMPLETADA")
    print("=" * 70)


if __name__ == "__main__":
    main()

# Uso técnico

Documentación para desarrolladores que implementan o integran la herramienta.

---

## Instalación

### Requisitos

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (gestor de paquetes)
- Clave de OpenRouteService (opcional — la herramienta funciona sin ella en modo sintético)

### Pasos

```bash
# 1. Clonar el repositorio
git clone https://github.com/rogelioGuerrero/accesibilidad-territorial.git
cd accesibilidad-territorial

# 2. Instalar dependencias
uv sync

# 3. (Opcional) Configurar OpenRouteService para datos reales de red vial
#    Registrarse en https://openrouteservice.org/ (gratis)
#    Crear archivo .env con:
#    ORS_API_KEY=tu_clave_aqui
#    MATRIX_PROVIDER=ors
#    ISOCHRONE_PROVIDER=ors

# 4. Verificar instalación
uv run pytest tests/ -v
```

---

## Demo interactivo

La herramienta incluye un mapa interactivo con 8 casos predefinidos que se ejecutan sin instalación ni clave de acceso:

```bash
uv run python -m uvicorn vrp_solver.main:app --host 127.0.0.1 --port 8000
```

Abrir http://localhost:8000/demo en el navegador. Casos disponibles:

| Caso | Descripción |
|------|-------------|
| Básico | 1 brigada, 5 comunidades |
| Multi-brigada | 3 brigadas, 15 comunidades con capacidad limitada |
| Multi-punto de salida | 2 puntos de salida, 4 brigadas, 20 comunidades |
| Ventanas de tiempo | 2 brigadas, 10 comunidades con horarios de atención |
| Backlog + isocronas | 50 comunidades, selección por prioridad y cobertura |
| Recogida y entrega | 3 pares de recogida y entrega vinculados |
| Habilidades | Brigada con cadena de frío vs normal |
| Descansos | 1 brigada con descanso del equipo |

---

## Uso como API

```bash
# Iniciar el servidor
uv run python -m uvicorn vrp_solver.main:app --host 0.0.0.0 --port 8000
```

```python
import httpx

request = {
    "locations": [
        {"id": "depot", "name": "Punto de salida", "coords": [4.65, -74.10], "type": "depot"},
        {"id": "d1", "name": "Comunidad 1", "coords": [4.66, -74.09], "type": "delivery", "weight_demand": 20.0},
        {"id": "d2", "name": "Comunidad 2", "coords": [4.64, -74.11], "type": "delivery", "weight_demand": 15.0},
        {"id": "d3", "name": "Comunidad 3", "coords": [4.67, -74.08], "type": "delivery", "weight_demand": 10.0},
    ],
    "vehicles": [
        {
            "id": "v1", "name": "Brigada 1",
            "start_location_id": "depot", "end_location_id": "depot",
            "weight_capacity": 200.0,
            "fixed_cost": 50.0, "cost_per_km": 2.5, "cost_per_hour": 20.0, "cost_per_stop": 3.0
        }
    ],
    "config": {"time_limit_seconds": 5, "optimize_by": "cost"}
}

response = httpx.post("http://localhost:8000/optimize", json=request)
result = response.json()

for route in result["routes"]:
    print(f"{route['vehicle_name']}: {len(route['stops'])} comunidades, "
          f"{route['total_distance']/1000:.1f} km, ${route['cost']['total']:.2f}")
```

---

## Uso como librería

```python
from vrp_solver.models import Location, LocationType, Vehicle, SolverConfig, OptimizeRequest
from vrp_solver.solver import VRPSolver

request = OptimizeRequest(
    locations=[
        Location(id="depot", name="Punto de salida", coords=(4.65, -74.10), type=LocationType.depot),
        Location(id="d1", name="Comunidad 1", coords=(4.66, -74.09), type=LocationType.delivery, weight_demand=20.0),
        Location(id="d2", name="Comunidad 2", coords=(4.64, -74.11), type=LocationType.delivery, weight_demand=15.0),
    ],
    vehicles=[
        Vehicle(id="v1", name="Brigada 1", start_location_id="depot", end_location_id="depot",
                weight_capacity=200.0, fixed_cost=50.0, cost_per_km=2.5, cost_per_hour=20.0, cost_per_stop=3.0)
    ],
    config=SolverConfig(time_limit_seconds=5, optimize_by="cost"),
)

solver = VRPSolver(
    locations=request.locations,
    vehicles=request.vehicles,
    config=request.config,
    matrix_provider="synthetic",  # o "ors" para datos reales
)
result = solver.solve()
print(f"Brigadas usadas: {result.statistics.vehicles_used}")
print(f"Distancia total: {result.statistics.total_distance / 1000:.1f} km")
print(f"Costo total: ${result.statistics.total_cost:.2f}")
```

---

## Pruebas

```bash
# Ejecutar todas las pruebas
uv run pytest tests/ -v

# Pruebas del motor de optimización (con matriz ORS real cacheada)
uv run pytest tests/test_solver.py -v

# Pruebas de regresión
uv run pytest tests/test_fixes.py -v
```

Las pruebas verifican: capacidad de brigadas, ventanas de tiempo, recogidas y entregas vinculadas, múltiples puntos de salida, costos, prioridades, habilidades especiales, descansos del equipo, y manejo de comunidades fuera de cobertura.

---

## Estructura del proyecto

```
accesibilidad-territorial/
├── src/vrp_solver/
│   ├── main.py              # Servidor API (FastAPI)
│   ├── solver.py            # Motor de optimización
│   ├── model_builder.py     # Construcción del modelo de optimización
│   ├── result_extractor.py  # Extracción y formato de resultados
│   ├── matrix.py            # Matriz de tiempos/distancias (real y sintética)
│   ├── isochrone_cache.py   # Mapas de cobertura con guardado automático
│   ├── node_selector.py     # Filtrado por cobertura y prioridades
│   ├── models.py            # Modelos de datos de entrada y salida
│   ├── validator.py         # Validación de solicitudes
│   ├── breaks.py            # Manejo de descansos del equipo
│   ├── demo.py              # Mapa interactivo de demostración
│   └── utils.py             # Utilidades (distancia haversine, etc.)
├── tests/                   # Pruebas automatizadas
│   ├── fixtures/            # Datos de prueba (matrices reales cacheadas)
│   ├── test_solver.py       # Pruebas del solver
│   ├── test_fixes.py        # Pruebas de regresión
│   ├── test_isochrone.py    # Pruebas de mapas de cobertura
│   └── test_validator.py    # Pruebas de validación
├── scripts/                 # Scripts auxiliares
├── img/                     # Imágenes del README
├── docs/                    # Documentación adicional
├── pyproject.toml
├── LICENSE
└── README.md
```

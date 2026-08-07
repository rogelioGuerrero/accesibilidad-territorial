# Accesibilidad y Optimización Territorial

**Diagnóstico de brechas de cobertura y planificación del despliegue de servicios públicos para gobiernos**

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Status: Activo](https://img.shields.io/badge/Status-Activo-green.svg)]()

![Demostración del mapa interactivo](img/demo_map.png)

---

## Tabla de contenidos

- [Descripción](#descripción)
- [El problema](#el-problema)
- [Cómo funciona](#cómo-funciona)
- [Instalación](#instalación)
- [Demo interactivo](#demo-interactivo)
- [Uso rápido](#uso-rápido)
- [Casos de uso](#casos-de-uso)
- [Roadmap](#roadmap)
- [Pruebas](#pruebas)
- [Contribuir](#contribuir)
- [Licencia](#licencia)
- [Contacto](#contacto)

---

## Descripción

Accesibilidad y Optimización Territorial es una herramienta de código abierto que responde dos preguntas críticas para la planificación de servicios públicos: **¿quién está lejos?** y **cómo se llega?**

La herramienta combina tres capacidades:

1. **Tiempo de viaje real por red vial** — calcula cuánto tarda una persona en llegar desde su comunidad hasta cada servicio disponible (escuela, hospital, centro de vacunación), considerando la red de caminos reales y el modo de transporte (auto, a pie, bicicleta, motocicleta).

2. **Mapas de cobertura por tiempo** — dibuja el área que se puede alcanzar desde cada servicio en un tiempo determinado (15, 30, 60 minutos). Permite identificar qué comunidades quedan fuera del alcance.

3. **Planificación del despliegue de recursos humanos y materiales** — cuando un gobierno necesita llevar servicios a la población (transporte escolar, brigadas de vacunación, distribución de alimentos, inspecciones sanitarias, recolección de residuos), la herramienta calcula la mejor asignación de flota y cuadrillas respetando restricciones reales: capacidad, horarios, habilidades específicas como cadena de frío, descansos, múltiples puntos de salida, y prioridades. La herramienta puede minimizar costo operativo, no solo distancia o tiempo. Además, soporta operaciones de recogida y entrega vinculada: recoger insumos en un centro de acopio y entregarlos en las comunidades, garantizando que la recogida ocurre antes de la entrega.

---

## El problema

Los gobiernos de la región necesitan responder preguntas como: *¿qué comunidades están demasiado lejos de una escuela secundaria?* *¿qué porcentaje de la población rural tiene acceso a un hospital en menos de una hora?* *¿cuántas brigadas necesitamos para alcanzar 200 comunidades y cuánto cuesta?*

Responder estas preguntas correctamente es complejo:

- **La distancia en línea recta no refleja el tiempo real de viaje**: dos comunidades pueden estar a la misma distancia de un hospital, pero una tiene camino pavimentado y la otra solo un camino rural.
- **La cobertura no es un círculo**: un servicio no cubre un radio de X kilómetros, sino un área que depende de los caminos disponibles.
- **Planificar el despliegue con restricciones reales es difícil**: capacidad, horarios, cadena de frío, múltiples puntos de salida — hacerlo a mano es inviable para cientos de comunidades.

---

## Cómo funciona

```
Datos de servicios y comunidades
         │
         ▼
┌─────────────────────────────────────┐
│  Accesibilidad y Optimización       │
│                                     │
│  Paso 1: ¿Quién está lejos?         │
│  · Tiempo de viaje real por red vial│
│  · Mapa de cobertura por minutos    │
│  · Comunidades fuera de alcance     │
│                                     │
│  Paso 2: ¿Cómo llega el Estado?     │
│  · Filtrar por alcance              │
│  · Asignar flota y cuadrillas       │
│  · Respetar capacidad, horarios,    │
│    capacidades especiales,          │
│    descansos, prioridades           │
│                                     │
│  Paso 3: Entregar resultado         │
│  · Plan de despliegue por brigada   │
│  · Tiempos y distancias             │
│  · Costos desglosados               │
│  · Comunidades no atendidas         │
└─────────────────────────────────────┘
         │
         ▼
Plan de despliegue y diagnóstico de cobertura
listos para integrar al sistema del gobierno
```

La herramienta puede funcionar de dos formas:

- **Con datos reales de red vial**: usando [OpenRouteService](https://openrouteservice.org/) (nivel gratuito disponible), calcula tiempos y distancias reales por los caminos de OpenStreetMap.
- **Con datos sintéticos**: sin conexión a internet ni clave de acceso, estima distancias y tiempos a partir de coordenadas geográficas. Ideal para evaluaciones rápidas, demostraciones, o cuando no se dispone de acceso al servicio de mapas.

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

## Uso rápido

### Como API

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

### Como librería

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

## Casos de uso

### Accesibilidad a maternidades de alta complejidad

Un ministerio de salud necesita identificar qué población está fuera del alcance de maternidades de alta complejidad. La herramienta calcula el área alcanzable en 60, 90 y 120 minutos en auto desde cada maternidad, identifica los radios censales que quedan fuera, y calcula qué porcentaje de mujeres en edad reproductiva queda excluida.

### Transporte escolar rural

Una provincia necesita organizar el transporte escolar para 500 niños distribuidos en 80 parajes rurales. La herramienta calcula el tiempo de viaje desde cada paraje hasta cada escuela, asigna cada niño a la escuela más cercana por tiempo de viaje real, y planifica el despliegue de los colectivos respetando asientos, horarios y tiempo máximo de viaje.

### Vacunación móvil

Un programa de vacunación despliega brigadas móviles para alcanzar comunidades rurales. La herramienta identifica las comunidades fuera del alcance de los centros fijos y planifica el despliegue de las brigadas considerando cadena de frío, horarios, capacidad de vacunas y habilidades requeridas por equipo. El resultado: cuántas brigadas se necesitan, qué comunidades atiende cada una, y cuánto cuesta.

### Distribución de alimentos escolares

Un programa de alimentación escolar distribuye raciones desde 5 centros de acopio a 200 escuelas. La herramienta planifica el despliegue de los camiones respetando capacidad, horarios de entrega y costo por kilómetro, con desglose de costos por brigada para presupuestar la operación.

---

## Roadmap

- [x] Tiempo de viaje real por red vial entre todos los puntos (también modo sintético sin internet)
- [x] Mapas de cobertura por minutos de viaje con guardado automático
- [x] Planificación del despliegue con capacidad, horarios, habilidades especiales, descansos, múltiples puntos de salida, y prioridades
- [x] Filtrado automático de comunidades fuera del alcance
- [x] Desglose de costos por brigada (fijo + distancia + tiempo + paradas)
- [x] Reintento automático entregando la mejor solución parcial
- [x] Manejo de prioridades alta, media y baja
- [x] Agrupación automática por territorio para planificar cientos de comunidades
- [x] Mapa interactivo de demostración con 8 casos predefinidos
- [x] Pruebas automatizadas con datos reales de red vial
- [ ] Módulo de diagnóstico de accesibilidad sin planificar despliegue
- [ ] Descubrimiento automático de servicios públicos desde bases de datos abiertas
- [ ] Exportación a mapas interactivos para visualización web
- [ ] Panel web para explorar brechas de cobertura
- [ ] Conectores para fuentes de datos gubernamentales

*Estas funcionalidades están en desarrollo y se incorporarán en futuras versiones.*

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

---

## Contribuir

Las contribuciones son bienvenidas. Áreas donde se busca ayuda:

- **Conectores para fuentes de datos gubernamentales**: INDEC, BAHRA, ministerios sectoriales
- **Casos de uso**: datos reales de escuelas, hospitales, programas sociales
- **Documentación**: guías de implementación por país, traducciones
- **Optimización**: perfiles de transporte adicionales (transporte público, motocicleta)

---

## Licencia

[Apache License 2.0](LICENSE) — permite uso comercial, modificación y distribución con atribución.

---

## Contacto

Para colaboración, adaptación o reportar problemas:

- **GitHub Issues**: [https://github.com/rogelioGuerrero/accesibilidad-territorial/issues](https://github.com/rogelioGuerrero/accesibilidad-territorial/issues)
- **Email**: [info@agtisa.com]

---

*Accesibilidad y Optimización Territorial es un Bien Público Digital candidato al catálogo de Código para el Desarrollo del BID. Ver [BID_CATALOG_DESCRIPTION.md](BID_CATALOG_DESCRIPTION.md) para la descripción completa del catálogo.*

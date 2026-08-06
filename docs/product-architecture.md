# Arquitectura de Producto — VRP Solver

## Visión General

El solver es un **motor abstracto** que recibe un payload estructurado, lo procesa, y entrega rutas optimizadas. No asume nada sobre el origen de los datos ni el destino de los resultados.

## Flujo del Producto

```
[Captura de demanda]          [Solver]                    [Entrega]
WhatsApp/Email/Portal    →    /optimize    →    JSON con rutas optimizadas
   ↓                              ↓                    ↓
Stepper LLM               Validación + OR-Tools    El cliente lo integra
(tool calling)            + Matrix (ORS real)      a su sistema/frontend
```

## Componentes

### 1. Captura de Demanda (Stepper LLM) — externo al solver

El cliente no arma payloads. Un agente LLM con tool calling sigue una receta determinística:

1. Recibir mensaje del cliente (WhatsApp, email, portal)
2. Extraer dirección → tool: geocode(address) → coords
3. Extraer producto y cantidad → tool: lookup_product(name) → weight, volume, skill
4. Extraer ventana de tiempo → tool: parse_time_window(text) → TimeWindow
5. Validar que todos los ingredientes estén presentes → tool: validate_demand(draft)
6. Si falta algo → preguntar al cliente
7. Si todo OK → tool: add_to_pool(demand)
8. Trigger "optimizar" → tool: optimize(fleet_id) → POST /optimize

**Datos estáticos (ya configurados por el cliente):**
- Bodegas/depots con coords
- Flota (vehículos, capacidades, skills, horarios)
- Zonas de cobertura

**Datos dinámicos (capturados por el LLM):**
- Pedidos del día (dirección, cantidad, ventana de tiempo, skill requerido)

### 2. Solver — el producto核心

Recibe un `OptimizeRequest` (payload) y entrega rutas optimizadas:

- **Validación estructural** (`validate_request`) — rechaza payloads mal formados
- **Selección de nodos** (`NodeSelector`) — filtra por cobertura (isocrona), prioridad (H/M/L), capacidad
- **Matriz de distancias/tiempos** — ORS real, cached, o sintético (intercambiable)
- **Optimización** (OR-Tools) — respeta capacity (peso/volumen), time windows, skills, breaks, pickup-delivery, multi-depot
- **Extracción de resultados** (`ResultExtractor`) — rutas, paradas, distancias, tiempos, diagnósticos
- **Clustering para 100+ pedidos** — agrupación por zona, optimización independiente por cluster

### 3. Entrega — externo al solver

El solver entrega un **JSON estructurado**. El cliente decide qué hacer con él:
- Integrarlo a su app de conductores
- Mostrarlo en su propio frontend
- Mandarlo a su sistema de tracking
- Generar reportes

## Lo que NO es el producto

- **El mapa (`/demo`)** — es una herramienta de demostración para validar que el solver funciona. No es el entregable.
- **El stepper LLM** — es la capa de captura, no el solver. Es un medio para garantizar payload limpio.
- **El frontend del cliente** — el solver no asume cómo el cliente presenta los resultados.

## Escalabilidad

- **≤30 pedidos por optimización**: OR-Tools resuelve en ~5s
- **50+ pedidos**: clustering por zona, optimización paralela por cluster
- **100+ pedidos**: `NodeSelector` prioriza por H/M/L, lo que no cabe queda como backlog

## Constraints Soportados

- Capacidad: peso + volumen
- Time windows: soft (penalty) o hard
- Skills: vehículo refrigerado, frágil, etc.
- Breaks: descansos programados con ventana de tiempo
- Pickup & delivery: pares vinculados con orden obligatorio
- Multi-depot: múltiples bodegas con flota asignada
- Horarios de vehículos: start_time, end_time

## Pitch

> "Envías tus pedidos por WhatsApp. Recibes las rutas optimizadas en JSON — orden de paradas, tiempos, distancias, cumplimiento de constraints. Lo integras a tu sistema como quieras."

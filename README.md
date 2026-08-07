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
- [Casos de uso](#casos-de-uso)
- [Diferenciación con herramientas existentes](#diferenciación-con-herramientas-existentes)
- [Demostración](#demostración)
- [Nivel de esfuerzo de implementación](#nivel-de-esfuerzo-de-implementación)
- [Requisitos técnicos](#requisitos-técnicos)
- [Roadmap](#roadmap)
- [Contribuir](#contribuir)
- [Licencia](#licencia)
- [Contacto](#contacto)

---

## Descripción

Accesibilidad y Optimización Territorial es una herramienta de código abierto que responde dos preguntas críticas para la planificación de servicios públicos: **¿quién está lejos?** y **cómo se llega?**

La herramienta combina tres capacidades:

1. **Tiempo de viaje real por red vial** — calcula cuánto tarda una persona en llegar desde su comunidad hasta cada servicio disponible (escuela, hospital, centro de vacunación), considerando la red de caminos reales y el modo de transporte (auto, a pie, bicicleta, motocicleta). No usa distancia en línea recta: mide el tiempo real que toma recorrer el camino.

2. **Mapas de cobertura por tiempo** — dibuja el área que se puede alcanzar desde cada servicio en un tiempo determinado (15, 30, 60 minutos). Esto permite responder: *"¿qué porcentaje de la población está a más de 30 minutos de una maternidad de alta complejidad?"* y identificar las comunidades que quedan fuera del alcance.

3. **Planificación del despliegue de recursos humanos y materiales** — cuando un gobierno necesita llevar servicios a la población (transporte escolar, brigadas de vacunación, distribución de alimentos, inspecciones sanitarias), la herramienta calcula la mejor asignación de flota y cuadrillas respetando restricciones reales: capacidad, horarios, habilidades específicas como cadena de frío, descansos, múltiples puntos de salida, y prioridades. La herramienta puede minimizar costo operativo, no solo distancia o tiempo. Además, soporta operaciones de recogida y entrega vinculada: recoger insumos en un centro de acopio y entregarlos en las comunidades, garantizando que la recogida ocurre antes de la entrega. Permite responder: *"¿cuántas brigadas necesito y qué comunidades atiende cada una para servir 200 comunidades?"*

La herramienta se integra a los sistemas existentes del gobierno: recibe los datos de servicios, población y recursos disponibles, y entrega planes de despliegue y diagnósticos de cobertura listos para usar. Para detalles de instalación, API y uso como librería, ver [docs/USO_TECNICO.md](docs/USO_TECNICO.md).

---

## El problema

Los gobiernos de la región necesitan responder preguntas como: *¿qué comunidades están demasiado lejos de una escuela secundaria?* *¿qué porcentaje de la población rural tiene acceso a un hospital en menos de una hora?* *¿cuántas brigadas necesitamos para alcanzar 200 comunidades y cuánto cuesta?*

Para responder estas preguntas, se necesita saber cuánto tarda realmente una persona en llegar desde su comunidad hasta el servicio más cercano, por el camino real, en el transporte disponible. Y cuando hay que desplegar brigadas, se necesita saber cuántas se necesitan, qué comunidades atiende cada una, y cuánto cuesta.

Sin embargo, responder estas preguntas correctamente es complejo:

1. **La distancia en línea recta no refleja el tiempo real de viaje**: dos comunidades pueden estar a la misma distancia en línea recta de un hospital, pero una tiene camino pavimentado y la otra solo un camino rural. El tiempo de viaje puede ser muy distinto.

2. **La cobertura no es un círculo**: un servicio no cubre un radio de X kilómetros, sino un área que depende de los caminos disponibles. Un mapa de cobertura real debe basarse en minutos de viaje, no en kilómetros en línea recta.

3. **Planificar el despliegue con restricciones reales es difícil**: cuando un gobierno despliega brigadas, debe respetar cuánto lleva cada una, en qué horarios debe entregar, qué capacidades necesita (como refrigeración para vacunas), y desde qué puntos sale. Hacer esto a mano es inviable para cientos de comunidades.

4. **Comparar todos los orígenes con todos los destinos**: para saber cuál es el servicio más cercano a cada comunidad, hay que calcular el tiempo de viaje desde cada comunidad a cada servicio — no solo al más cercano en línea recta, que puede no ser el más cercano por camino real.

**Accesibilidad y Optimización Territorial resuelve estas cuatro necesidades** con tiempos de viaje reales por red vial, mapas de cobertura por minutos, y planificación automática del despliegue.

---

## Cómo funciona

La herramienta opera en dos modos que pueden usarse independientemente o en conjunto:

### Modo 1: Diagnóstico de Accesibilidad

Responde: *"¿quién está lejos y cuánto tarda?"*

1. **Cargar los datos**: ubicación de los servicios (escuelas, hospitales, centros de vacunación) y ubicación de las comunidades (radios censales, localidades, parajes rurales).
2. **Calcular el tiempo de viaje real** desde cada comunidad hasta cada servicio, por la red de caminos reales y según el modo de transporte (auto, a pie, bicicleta).
3. **Identificar el servicio más cercano a cada comunidad** por tiempo de viaje real — no por distancia en línea recta.
4. **Dibujar el mapa de cobertura** de cada servicio: el área que se alcanza en 15, 30 o 60 minutos. Los resultados se guardan para no recalcularlos cada vez.
5. **Identificar brechas**: las comunidades que quedan fuera de todos los mapas de cobertura son la población sin acceso.

### Modo 2: Planificación del Despliegue

Responde: *"¿cómo llega el Estado con los recursos disponibles?"*

1. **Cargar la flota**: vehículos con su capacidad (peso, volumen, asientos), horarios, costos, y capacidades especiales (refrigeración, etc.).
2. **Cargar los puntos a visitar**: entregas, recogidas, o servicios a realizar, con sus ventanas de tiempo y prioridades.
3. **Filtrar por alcance**: la herramienta descarta los puntos que ningún vehículo puede alcanzar y asigna cada punto al punto de salida más cercano.
4. **Calcular el mejor plan de despliegue** respetando:
   - Cuánto lleva cada vehículo (peso y volumen)
   - Horarios de entrega o servicio
   - Capacidades especiales requeridas (cadena de frío, manipulación de frágiles)
   - Descansos del equipo con ventana horaria
   - Recogidas y entregas vinculadas (recoger en un punto, entregar en otro)
   - Múltiples puntos de salida
   - Horarios de inicio y fin de jornada
   - Distancia o cantidad máxima de paradas por brigada
   - Prioridades: las comunidades de alta prioridad se atienden primero
5. **Entregar el resultado**: plan de despliegue por brigada con orden de paradas, tiempos de llegada y salida, distancias, costos desglosados por brigada, y lista de comunidades que no se pudieron atender con diagnóstico de causa.

### Modo 3: Diagnóstico + Intervención

El flujo completo: diagnosticar brechas de cobertura (Modo 1) → diseñar intervención optimizada (Modo 2). Por ejemplo: *"30% de los niños rurales están a más de 60 minutos de una escuela secundaria → con 3 brigadas de transporte escolar adicionales, se cubre el 95%"*.

La herramienta puede funcionar de dos formas:

- **Con datos reales de red vial**: usando [OpenRouteService](https://openrouteservice.org/) (nivel gratuito disponible), calcula tiempos y distancias reales por los caminos de OpenStreetMap.
- **Con datos sintéticos**: sin conexión a internet ni clave de acceso, estima distancias y tiempos a partir de coordenadas geográficas. Ideal para evaluaciones rápidas, demostraciones, o cuando no se dispone de acceso al servicio de mapas.

---

## Casos de uso

### Accesibilidad a maternidades de alta complejidad

Un ministerio de salud necesita identificar qué población está fuera del alcance de maternidades de alta complejidad neonatal. La herramienta calcula el área alcanzable en 60, 90 y 120 minutos en auto desde cada maternidad, identifica los radios censales que quedan fuera, y calcula qué porcentaje de mujeres en edad reproductiva (15-49 años) queda excluida. Para cada comunidad, identifica la maternidad más cercana por tiempo de viaje real.

### Transporte escolar rural

Una provincia necesita organizar el transporte escolar para 500 niños distribuidos en 80 parajes rurales que asisten a 12 escuelas. La herramienta calcula el tiempo de viaje desde cada paraje hasta cada escuela, asigna cada niño a la escuela más cercana por tiempo de viaje real, y planifica el despliegue de los colectivos respetando: cantidad de asientos, horario de entrada (08:00), horario de salida (16:00), y tiempo máximo de viaje por niño. El resultado: número mínimo de colectivos necesarios, qué comunidades atiende cada uno, y costo total estimado.

### Vacunación móvil

Un programa de vacunación necesita desplegar brigadas móviles para alcanzar comunidades rurales. La herramienta identifica las comunidades fuera del alcance de los centros de salud fijos, y planifica el despliegue de las brigadas considerando: cadena de frío, horarios de atención por comunidad, capacidad de vacunas por equipo, habilidades requeridas, y múltiples puntos de salida.

### Distribución de alimentos escolares

Un programa de alimentación escolar necesita distribuir raciones desde 5 centros de acopio a 200 escuelas. La herramienta planifica el despliegue de los camiones respetando: capacidad de peso y volumen, horarios de entrega por escuela, múltiples centros de acopio, y costo por kilómetro. El resultado incluye el costo desglosado por brigada para presupuestar la operación.

---

## Diferenciación con herramientas existentes

| Herramienta | Qué hace | Qué le falta |
|-------------|----------|-------------|
| geo_escuelas (Fundación Bunge y Born) | Mide distancia a la escuela más cercana y muestra el resultado en un mapa | Selecciona la escuela por distancia en línea recta, no por tiempo de viaje real. No calcula mapas de cobertura por minutos. No planifica el despliegue de brigadas |
| IVS-MI (Fundación Bunge y Born) | Mide distancia a la maternidad más cercana y la cruza con datos socioeconómicos | Selecciona la maternidad por distancia en línea recta. No calcula mapas de cobertura por minutos. No planifica el despliegue de brigadas |
| Matriz OD Transporte Público (BID) | Construye matriz de viajes en transporte público desde datos de tarjeta SUBE | Solo aplica al transporte público del AMBA. No mide accesibilidad a servicios. No planifica el despliegue de brigadas |
| Congestiometro (BID) | Mide la congestión vehicular en ciudades | Mide congestión, no accesibilidad a servicios ni planificación del despliegue |

**Esta es la única herramienta que combina: tiempo de viaje real por red vial + mapas de cobertura por minutos + planificación automática del despliegue con restricciones reales.**

---

## Demostración

La herramienta incluye un **mapa interactivo de demostración** con casos predefinidos que pueden ejecutarse sin instalación ni clave de acceso, usando datos sintéticos. Los casos disponibles incluyen: despliegue básico, múltiples brigadas, múltiples puntos de salida, ventanas de tiempo, cobertura por minutos, recogidas y entregas vinculadas, capacidades especiales (cadena de frío), y descansos del equipo.

![Demostración del mapa interactivo](img/demo_map.png)

Además, la herramienta cuenta con **pruebas automatizadas** que verifican el funcionamiento correcto de cada capacidad usando datos reales de red vial: capacidad de brigadas, ventanas de tiempo, recogidas y entregas, múltiples puntos de salida, costos, prioridades, y manejo de comunidades fuera de cobertura.

---

## Nivel de esfuerzo de implementación

**Medio** — La herramienta se instala y se conecta a los sistemas del gobierno. La implementación requiere:

1. **Instalar la herramienta**: requiere Python y una clave de acceso al servicio de ruteo (hay un nivel gratuito disponible).
2. **Cargar los datos del dominio**: ubicación de los servicios (escuelas, hospitales) y de las comunidades (radios censales, localidades). La herramienta acepta cualquier archivo con coordenadas, sin importar la fuente.
3. **Configurar el modo de transporte**: auto, a pie, bicicleta o motocicleta, según el caso de uso.
4. **Integrar los resultados**: la herramienta entrega planes de despliegue y diagnósticos de cobertura que se incorporan al sistema existente del gobierno.

La configuración específica de cada país o ministerio (datos de escuelas, padrón de hospitales, flota vehicular) se adapta fácilmente gracias a que la herramienta es de código abierto y acepta cualquier fuente de datos con coordenadas.

---

## Requisitos técnicos

- **Python 3.12+**
- **Acceso al servicio de ruteo OpenRouteService** (nivel gratuito disponible, también se puede instalar localmente)
- **Todas las demás dependencias se instalan automáticamente** (motor de optimización, servidor web, etc.)
- **Despliegue**: local, en servidores propios del gobierno, o en la nube
- **No requiere software adicional**: no necesita R, PostgreSQL, ni herramientas de mapas externas

---

## Roadmap

**Completado:**
- Cálculo de tiempos de viaje reales por red vial entre todos los puntos (también modo sintético sin internet)
- Mapas de cobertura por minutos de viaje, con guardado automático para no recalcular
- Planificación del despliegue respetando capacidad, horarios, habilidades especiales, descansos, múltiples puntos de salida, y prioridades
- Filtrado automático de comunidades fuera del alcance de cualquier punto de salida
- Desglose de costos por brigada (fijo + distancia + tiempo + paradas)
- Reintento automático cuando no hay solución exacta, entregando la mejor solución parcial
- Manejo de comunidades con prioridad alta, media y baja
- Agrupación automática para planificar más de 100 puntos
- Mapa interactivo de demostración con 8 casos predefinidos
- Pruebas automatizadas con datos reales de red vial

**Futuras versiones:**
- Módulo de diagnóstico de accesibilidad sin necesidad de planificar despliegue
- Descubrimiento automático de servicios públicos por categoría (escuelas, hospitales, etc.) desde bases de datos abiertas
- Exportación a mapas interactivos para visualización web
- Panel web para explorar brechas de cobertura
- Conectores para fuentes de datos gubernamentales (institutos de estadística, ministerios sectoriales)

*Estas funcionalidades están en desarrollo y se incorporarán en futuras versiones.*

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

## Datos de la herramienta

| Campo | Valor |
|-------|-------|
| **Nombre** | Accesibilidad y Optimización Territorial |
| **Tipo de herramienta** | API, Algoritmo |
| **Licencia** | Apache License 2.0 |
| **Lenguaje** | Python |
| **Versión** | 1.0.0 |
| **Categorías** | Transporte, Salud, Educación, Planificación territorial |
| **País de origen** | El Salvador |
| **Estado** | Activo |

---

*Accesibilidad y Optimización Territorial aspira a ser reconocido como Bien Público Digital por su contribución a la mejora de la planificación de servicios públicos en América Latina y el Caribe. La herramienta es de código abierto bajo licencia Apache 2.0, permite uso comercial, y está diseñada para ser reutilizable por cualquier gobierno de la región sin depender de proveedores específicos. A diferencia de enfoques que miden accesibilidad por distancia en línea recta, esta herramienta utiliza tiempos de viaje reales por red vial, mapas de cobertura por minutos, y planificación automática del despliegue — entregando evidencia territorial confiable para la toma de decisiones en políticas públicas.*

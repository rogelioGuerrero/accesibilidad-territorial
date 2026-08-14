"""
Casos de validación con eventos reales documentados.

Cada caso tiene:
  - Datos del evento (fecha, ubicación, magnitud)
  - Ground truth publicado por agencias independientes
  - Fuentes verificables (URLs, papers, reportes oficiales)
  - Parámetros para simular la detección
  - Métrica de validación (qué comparar contra el real)

Eventos seleccionados por diversidad geográfica y tipo de análisis:
  1. Beirut 2020 — explosión (SAR damage, Líbano)
  2. Australia 2019-2020 — incendios (NBR, Oceanía)
  3. Amazonía Brasil 2022 — deforestación (NDVI+SAR, Sudamérica)
  4. Dubai 2015-2025 — construcción (NDBI, Medio Oriente)

Filosofía NOOA: dataclass = caso, campos = evidencia.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationCase:
    """Caso de validación con evento real documentado."""
    name: str
    event_type: str  # explosion, fire, deforestation, construction
    date: str
    location: str
    coordinates: tuple[float, float]  # (lat, lng)
    description: str

    # Ground truth publicado
    ground_truth: dict[str, Any] = field(default_factory=dict)

    # Fuentes verificables
    sources: list[dict[str, str]] = field(default_factory=list)

    # Parámetros para la simulación
    zones: list[dict] = field(default_factory=list)
    sim_params: dict[str, Any] = field(default_factory=dict)

    # Qué comparar
    validation_metric: str = ""
    expected_value: float = 0.0
    tolerance_pct: float = 15.0  # ±15% aceptable


# ═════════════════════════════════════════════════════════════════════
# CASO 1: Beirut — Explosión del puerto (4 agosto 2020)
# ═════════════════════════════════════════════════════════════════════

BEIRUT_2020 = ValidationCase(
    name="Explosión del Puerto de Beirut",
    event_type="explosion",
    date="2020-08-04",
    location="Beirut, Líbano",
    coordinates=(33.9018, 35.5188),
    description=(
        "Explosión de 2,750 toneladas de nitrato de amonio en el puerto de Beirut. "
        "Una de las explosiones no nucleares más grandes de la historia. "
        "Sentinel-1 capturó imagen pre-evento (30 jul) y post-evento (5 ago)."
    ),
    ground_truth={
        "blast_yield_tnt_tons": 1100,  # estimado: 1.1 kilotones TNT
        "blast_radius_severe_km": 3.0,  # daño severo dentro de 3km
        "deaths": 218,
        "injured": 6500,
        "displaced": 300000,
        "buildings_damaged": 77000,
        "buildings_destroyed": 6000,
        "port_silos_destroyed": True,
        "nasa_aria_damage_proxy": "Publicado 5 ago 2020 — SAR change detection",
        "copernicus_ems_activation": "EMSR369 — Beirut Explosion",
    },
    sources=[
        {
            "name": "NASA ARIA — Damage Proxy Map",
            "url": "https://aria.jpl.nasa.gov/products/beirut-explosion-2020.html",
            "note": "Mapa de daño desde Sentinel-1 SAR, pre 30-jul / post 5-ago",
        },
        {
            "name": "Copernicus EMS — EMSR369",
            "url": "https://emergency.copernicus.eu/mapping/list-of-components/EMSR369",
            "note": "Activación de mapeo de emergencia oficial",
        },
        {
            "name": "BBC News — Beirut explosion",
            "url": "https://www.bbc.com/news/world-middle-east-53659782",
            "note": "218 muertos, 6,500 heridos, 300,000 desplazados",
        },
    ],
    zones=[
        {"name": "Puerto (epicentro)", "lat": 33.9018, "lng": 35.5188},
        {"name": "Mar Mikhael (1km)", "lat": 33.8950, "lng": 35.5150},
        {"name": "Gemmayzeh (1.5km)", "lat": 33.8920, "lng": 35.5100},
        {"name": "Achrafieh (2.5km)", "lat": 33.8870, "lng": 35.5100},
        {"name": "Hamra (3.5km)", "lat": 33.8980, "lng": 35.4820},
        {"name": "Ras Beirut (5km)", "lat": 33.8950, "lng": 35.4800},
    ],
    sim_params={
        "blast_radius_km": 5.0,
        "seed": 2020,
    },
    validation_metric="área de daño severo (SAR > 6dB, radio ~3km → ~28 km²)",
    expected_value=28.0,  # km² (π * 3² ≈ 28.3)
    tolerance_pct=25.0,
)


# ═════════════════════════════════════════════════════════════════════
# CASO 2: Australia — Incendios "Black Summer" (Nov 2019 – Ene 2020)
# ═════════════════════════════════════════════════════════════════════

AUSTRALIA_FIRES = ValidationCase(
    name="Incendios Black Summer — Australia",
    event_type="fire",
    date="2019-11-01 a 2020-01-31",
    location="Nueva Gales del Sur y Victoria, Australia",
    coordinates=(-35.0, 149.0),
    description=(
        "Los incendios más destructivos de la historia moderna de Australia. "
        "Sentinel-2 capturó imágenes antes y después con ventanas sin nubes. "
        "NBR (Normalized Burn Ratio) mapeó el área quemada con precisión."
    ),
    ground_truth={
        "total_burned_hectares": 18_600_000,  # 18.6M ha
        "total_burned_km2": 186_000,
        "deaths": 33,
        "animals_killed_estimated": "3 mil millones",
        "homes_destroyed": 3094,
        "nsw_burned_km2": 56_000,
        "victoria_burned_km2": 15_000,
        "afac_report": "Australasian Fire and Emergency Service Authorities Council",
        "rmit_analysis": "RMIT University — NBR analysis from Sentinel-2",
    },
    sources=[
        {
            "name": "AFAC — Official Report",
            "url": "https://knowledge.aidr.org.au/resources/black-summer-bushfires-2019-20/",
            "note": "Reporte oficial: 18.6M hectáreas, 33 muertos, 3,094 casas",
        },
        {
            "name": "NASA FIRMS — Fire Information",
            "url": "https://firms.modaps.eosdis.nasa.gov/",
            "note": "Satellite fire detection — MODIS + VIIRS",
        },
        {
            "name": "Copernicus EMS — EMSR421",
            "url": "https://emergency.copernicus.eu/mapping/list-of-components/EMSR421",
            "note": "Activación de mapeo de incendios australianos",
        },
    ],
    zones=[
        {"name": "South Coast NSW", "lat": -35.5, "lng": 150.0},
        {"name": "Snowy Mountains NSW", "lat": -36.0, "lng": 148.5},
        {"name": "East Gippsland VIC", "lat": -37.5, "lng": 148.0},
        {"name": "Blue Mountains NSW", "lat": -33.7, "lng": 150.3},
        {"name": "Kangaroo Island SA", "lat": -35.8, "lng": 137.2},
        {"name": "Sydney Metro (no quemada)", "lat": -33.9, "lng": 151.2},
    ],
    sim_params={
        "burn_severity_map": {
            "South Coast NSW": "alta",
            "Snowy Mountains NSW": "alta",
            "East Gippsland VIC": "alta",
            "Blue Mountains NSW": "moderada",
            "Kangaroo Island SA": "alta",
            "Sydney Metro (no quemada)": "no_quemada",
        },
        "seed": 2020,
    },
    validation_metric="área quemada total (dNBR > 0.10)",
    expected_value=186_000,  # km²
    tolerance_pct=25.0,  # mayor tolerancia por estimación de área
)


# ═════════════════════════════════════════════════════════════════════
# CASO 3: Amazonía Brasil — Deforestación 2022
# ═════════════════════════════════════════════════════════════════════

AMAZON_DEFORESTATION = ValidationCase(
    name="Deforestación Amazónica — Brasil 2022",
    event_type="deforestation",
    date="Agosto 2021 a Julio 2022 (año PRODES)",
    location="Amazonía, Brasil",
    coordinates=(-5.0, -60.0),
    description=(
        "INPE (Instituto Nacional de Pesquisas Espaciais de Brasil) publica "
        "datos oficiales de deforestación vía PRODES y DETER. "
        "Sentinel-2 detecta caída de NDVI y Sentinel-1 confirma cambio de rugosidad. "
        "Convergencia de ambos índices = detección contundente."
    ),
    ground_truth={
        "prodes_2022_km2": 13_038,  # INPE PRODES 2022
        "prodes_2021_km2": 13_075,
        "deter_alerts_2022": 1987,  # número de alertas DETER
        "pará_state_km2": 4_100,
        "amazonas_state_km2": 3_200,
        "rondonia_state_km2": 1_900,
        "mato_grosso_state_km2": 1_500,
        "inpe_source": "PRODES — Monitoramento da Floresta Amazônica Brasileira por Satélite",
        "global_forest_watch": "World Resources Institute — tree cover loss",
    },
    sources=[
        {
            "name": "INPE PRODES — Datos oficiales",
            "url": "http://www.obt.inpe.br/OBT/assuntos/programas/amazonia/prodes",
            "note": "13,038 km² deforestados en 2022 (año PRODES ago-2021 a jul-2022)",
        },
        {
            "name": "INPE DETER — Alertas en tiempo real",
            "url": "http://www.obt.inpe.br/OBT/assuntos/programas/amazonia/deter/deter",
            "note": "Sistema de alertas de deforestación en tiempo casi real",
        },
        {
            "name": "Global Forest Watch",
            "url": "https://www.globalforestwatch.org/",
            "note": "World Resources Institute — datos de pérdida de cobertura forestal",
        },
    ],
    zones=[
        {"name": "Pará (sudeste)", "lat": -6.0, "lng": -52.0},
        {"name": "Amazonas (sur)", "lat": -7.0, "lng": -60.0},
        {"name": "Rondônia", "lat": -10.5, "lng": -62.5},
        {"name": "Mato Grosso (norte)", "lat": -10.0, "lng": -55.0},
        {"name": "Acre", "lat": -9.0, "lng": -70.0},
        {"name": "Reserva Yanomami (intacto)", "lat": -2.0, "lng": -64.0},
    ],
    sim_params={
        "clearing_status": {
            "Pará (sudeste)": "deforestado",
            "Amazonas (sur)": "deforestado",
            "Rondônia": "deforestado",
            "Mato Grosso (norte)": "degradado",
            "Acre": "degradado",
            "Reserva Yanomami (intacto)": "intacto",
        },
        "seed": 2022,
    },
    validation_metric="área deforestada total (NDVI drop + SAR confirm)",
    expected_value=13_038,  # km²
    tolerance_pct=20.0,
)


# ═════════════════════════════════════════════════════════════════════
# CASO 4: Dubai — Expansión urbana 2015-2025
# ═════════════════════════════════════════════════════════════════════

DUBAI_CONSTRUCTION = ValidationCase(
    name="Expansión Urbana — Dubai 2015-2025",
    event_type="construction",
    date="2015 a 2025",
    location="Dubai, Emiratos Árabes Unidos",
    coordinates=(25.2048, 55.2708),
    description=(
        "Dubai es una de las ciudades con mayor expansión urbana del siglo XXI. "
        "Sentinel-2 ha documentado el cambio década a década. "
        "NDBI sube donde hay nueva construcción, NDVI cae donde era desierto/vegetación. "
        "La convergencia NDBI↑ + NDVI↓ discrimina construcción de cambios estacionales."
    ),
    ground_truth={
        "built_area_2015_km2": 850,
        "built_area_2025_km2": 1200,  # estimación
        "new_construction_km2": 350,
        "population_2015_millions": 2.4,
        "population_2025_millions": 3.6,
        "new_land_reclamation": "Palm Jebel Ali, Dubai Creek Harbour",
        "tallest_buildings_built": "Burj Khalifa (2010), Marina 101 (2014)",
        "world_bank_urban_expansion": "World Bank — Urban development indicators",
    },
    sources=[
        {
            "name": "Dubai Statistics Center",
            "url": "https://www.dsc.gov.ae/",
            "note": "Estadísticas oficiales de población y construcción",
        },
        {
            "name": "Sentinel-2 Time Series — Copernicus",
            "url": "https://browser.dataspace.copernicus.eu/",
            "note": "Imágenes Sentinel-2 desde 2015, comparación decenal",
        },
        {
            "name": "World Bank — Urban Indicators",
            "url": "https://data.worldbank.org/indicator/SP.URB.TOTL.IN.ZS?locations=AE",
            "note": "Indicadores de desarrollo urbano de Emiratos Árabes",
        },
    ],
    zones=[
        {"name": "Dubai Marina (construido)", "lat": 25.08, "lng": 55.14},
        {"name": "Dubai Creek Harbour (construido)", "lat": 25.20, "lng": 55.34},
        {"name": "Meydan (en construcción)", "lat": 25.18, "lng": 55.22},
        {"name": "Expo City (construido)", "lat": 24.96, "lng": 55.16},
        {"name": "Desierto sur (sin cambio)", "lat": 24.80, "lng": 55.30},
        {"name": "Palm Jumeirah (construido)", "lat": 25.11, "lng": 55.13},
    ],
    sim_params={
        "construction_status": {
            "Dubai Marina (construido)": "construido",
            "Dubai Creek Harbour (construido)": "construido",
            "Meydan (en construcción)": "en_construccion",
            "Expo City (construido)": "construido",
            "Desierto sur (sin cambio)": "sin_cambio",
            "Palm Jumeirah (construido)": "construido",
        },
        "seed": 2025,
    },
    validation_metric="área nueva construida (NDBI↑ + NDVI↓ convergencia)",
    expected_value=350,  # km²
    tolerance_pct=30.0,
)


# ═════════════════════════════════════════════════════════════════════
# Registro de todos los casos
# ═════════════════════════════════════════════════════════════════════

ALL_CASES: list[ValidationCase] = [
    BEIRUT_2020,
    AUSTRALIA_FIRES,
    AMAZON_DEFORESTATION,
    DUBAI_CONSTRUCTION,
]

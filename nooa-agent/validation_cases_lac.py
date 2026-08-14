"""
Casos de validación LAC (Latin America & Caribbean) con eventos reales.

5 eventos documentados en Latinoamérica:
  1. Brumadinho, Brasil 2019 — rotura de presa de relaves (SAR damage)
  2. Chile 2017 — incendios forestales (NBR burned area)
  3. Chaco Paraguayo 2022 — deforestación (NDVI + SAR)
  4. Tren Maya, México 2020-2024 — construcción (NDBI + NDVI)
  5. Rio Grande do Sul, Brasil 2024 — inundación (SAR + NDWI)

Cada caso tiene ground truth de agencias LAC:
  - ANM (Agência Nacional de Mineração, Brasil)
  - CONAF (Corporación Nacional Forestal, Chile)
  - INFONA (Instituto Forestal Nacional, Paraguay)
  - FONATUR (Fondo Nacional de Fomento al Turismo, México)
  - Defesa Civil do Rio Grande do Sul, Brasil

Filosofía NOOA: dataclass = caso, campos = evidencia.
"""

from __future__ import annotations

from validation_cases import ValidationCase


# ═════════════════════════════════════════════════════════════════════
# CASO 1: Brumadinho — Rotura de presa de relaves (25 enero 2019)
# ═════════════════════════════════════════════════════════════════════

BRUMADINHO_2019 = ValidationCase(
    name="Rotura de Presa de Brumadinho",
    event_type="explosion",  # reusamos detect_explosion_damage (SAR change)
    date="2019-01-25",
    location="Brumadinho, Minas Gerais, Brasil",
    coordinates=(-19.6428, -44.0978),
    description=(
        "Rotura de la presa de relaves de Córrego do Feijão (Vale S.A.). "
        "12 millones de m³ de lodo de minería recorrieron 10 km en minutos. "
        "270 muertos, 16 desaparecidos. "
        "Sentinel-1 capturó imagen pre (24-ene) y post (30-ene) — "
        "el flujo de lodo cambió drásticamente el backscatter SAR."
    ),
    ground_truth={
        "deaths": 270,
        "missing": 16,
        "tailings_volume_m3": 12_000_000,
        "mudflow_distance_km": 10,
        "mudflow_area_km2": 3.0,  # área cubierta por lodo
        "affected_buildings": 250,
        "anm_report": "Agência Nacional de Mineração — Reporte oficial",
        "copernicus_ems": "EMSR313 — Brumadinho Dam Collapse",
        "nasa_aria": "Damage proxy map from Sentinel-1 SAR",
        "independent_investigation": "Informe de la Comisión Independiente de Brumadinho",
    },
    sources=[
        {
            "name": "Copernicus EMS — EMSR313",
            "url": "https://emergency.copernicus.eu/mapping/list-of-components/EMSR313",
            "note": "Activación de mapeo de emergencia — Brumadinho dam collapse",
        },
        {
            "name": "NASA ARIA — Damage Proxy",
            "url": "https://aria.jpl.nasa.gov/products/brumadinho-dam-collapse-2019.html",
            "note": "Mapa de daño SAR Sentinel-1, pre 24-ene / post 30-ene 2019",
        },
        {
            "name": "Comisión Independiente Brumadinho",
            "url": "https://www.gov.br/anm/pt-br/assuntos/noticias-anm/relatorio-final-da-cibr",
            "note": "Investigación oficial: 270 muertos, 12M m³ de relaves",
        },
    ],
    zones=[
        {"name": "Presa Córrego do Feijão (epicentro)", "lat": -19.6428, "lng": -44.0978},
        {"name": "Comunidade Parque da Cachoeira (1km)", "lat": -19.6350, "lng": -44.0900},
        {"name": "Refeitório Vale (1.5km)", "lat": -19.6300, "lng": -44.0850},
        {"name": "Comunidade João Fernandes (3km)", "lat": -19.6200, "lng": -44.0800},
        {"name": "Río Paraopeba (5km)", "lat": -19.6100, "lng": -44.0700},
        {"name": "Brumadinho centro (8km, no afectado)", "lat": -19.6700, "lng": -44.0400},
    ],
    sim_params={
        "blast_radius_km": 6.0,  # radio del flujo de lodo
        "seed": 2019,
        "area_per_zone_km2": (0.3, 1.2),
    },
    validation_metric="área afectada por flujo de lodo (SAR backscatter change)",
    expected_value=3.0,  # km² cubiertos por lodo
    tolerance_pct=30.0,
)


# ═════════════════════════════════════════════════════════════════════
# CASO 2: Chile — Incendios forestales 2017 (enero-febrero)
# ═════════════════════════════════════════════════════════════════════

CHILE_FIRES_2017 = ValidationCase(
    name="Incendios Forestales — Chile 2017",
    event_type="fire",
    date="2017-01-15 a 2017-02-05",
    location="Región del Maule y Biobío, Chile",
    coordinates=(-35.5, -71.5),
    description=(
        "Los incendios más destructivos en la historia de Chile. "
        "Sentinel-2 capturó imágenes pre y post con ventanas sin nubes. "
        "NBR mapeó el área quemada con precisión. "
        "CONAF activó respuesta de emergencia internacional."
    ),
    ground_truth={
        "total_burned_hectares": 530_000,  # 530,000 ha = 5,300 km²
        "total_burned_km2": 5_300,
        "deaths": 11,
        "homes_destroyed": 1500,
        "firefighters_international": "Brasil, Argentina, Perú, México, USA, España, Francia, Portugal, Rusia",
        "conaf_report": "Corporación Nacional Forestal — Reporte oficial",
        "copernicus_ems": "EMSR207 — Chile Forest Fires",
        "regions_affected": "O'Higgins, Maule, Biobío, Araucanía",
        "maule_burned_km2": 2_200,
        "biobio_burned_km2": 1_800,
    },
    sources=[
        {
            "name": "CONAF — Reporte oficial",
            "url": "https://www.conaf.cl/incendios-forestales/",
            "note": "530,000 hectáreas quemadas, 11 muertos, 1,500 casas destruidas",
        },
        {
            "name": "Copernicus EMS — EMSR207",
            "url": "https://emergency.copernicus.eu/mapping/list-of-components/EMSR207",
            "note": "Activación de mapeo de incendios forestales Chile 2017",
        },
        {
            "name": "NASA FIRMS — Fire detection",
            "url": "https://firms.modaps.eosdis.nasa.gov/",
            "note": "Detección de incendios por satélite MODIS + VIIRS",
        },
    ],
    zones=[
        {"name": "Maule Centro (alta severidad)", "lat": -35.5, "lng": -71.5},
        {"name": "Maule Costa (alta severidad)", "lat": -35.3, "lng": -72.2},
        {"name": "Biobío Interior (alta severidad)", "lat": -37.2, "lng": -71.8},
        {"name": "Biobío Costa (moderada)", "lat": -37.0, "lng": -73.0},
        {"name": "Araucanía (moderada)", "lat": -38.5, "lng": -72.5},
        {"name": "Concepción (no quemada)", "lat": -36.8, "lng": -73.0},
    ],
    sim_params={
        "burn_severity_map": {
            "Maule Centro (alta severidad)": "alta",
            "Maule Costa (alta severidad)": "alta",
            "Biobío Interior (alta severidad)": "alta",
            "Biobío Costa (moderada)": "moderada",
            "Araucanía (moderada)": "moderada",
            "Concepción (no quemada)": "no_quemada",
        },
        "seed": 2017,
        "area_per_zone_km2": (400, 1600),
    },
    validation_metric="área quemada total (dNBR > 0.10)",
    expected_value=5_300,  # km²
    tolerance_pct=25.0,
)


# ═════════════════════════════════════════════════════════════════════
# CASO 3: Chaco Paraguayo — Deforestación 2022
# ═════════════════════════════════════════════════════════════════════

CHACO_PARAGUAY_2022 = ValidationCase(
    name="Deforestación del Chaco — Paraguay 2022",
    event_type="deforestation",
    date="Enero a Diciembre 2022",
    location="Chaco Paraguayo (Alto Paraguay, Boquerón, Presidente Hayes)",
    coordinates=(-21.0, -61.0),
    description=(
        "El Chaco Paraguayo tiene una de las tasas de deforestación más altas "
        "del mundo por hectárea. INFONA publica datos oficiales anuales. "
        "Sentinel-2 detecta caída de NDVI y Sentinel-1 confirma cambio de rugosidad. "
        "La convergencia de ambos índices discrimina deforestación real de "
        "cambios estacionales del bosque seco chaqueño."
    ),
    ground_truth={
        "infona_2022_km2": 2_350,  # INFONA 2022
        "infona_2021_km2": 2_680,
        "global_forest_watch_2022_km2": 2_410,
        "alto_paraguay_km2": 1_100,
        "boqueron_km2": 850,
        "presidente_hayes_km2": 400,
        "infona_source": "Instituto Forestal Nacional — Monitoreo de cambio de uso de suelo",
        "wri_source": "World Resources Institute — Global Forest Watch",
        "maapproject": "MAAP (Monitoring of the Andean Amazon Project) — Chaco deforestation",
    },
    sources=[
        {
            "name": "INFONA — Datos oficiales",
            "url": "https://www.infona.gov.py/",
            "note": "Instituto Forestal Nacional de Paraguay — monitoreo de cobertura forestal",
        },
        {
            "name": "Global Forest Watch — Paraguay",
            "url": "https://www.globalforestwatch.org/country/PRY/",
            "note": "WRI — 2,410 km² pérdida de cobertura forestal en 2022",
        },
        {
            "name": "MAAP — Chaco Deforestation",
            "url": "https://maaproject.org/",
            "note": "Monitoring of the Andean Amazon Project — incluye Chaco paraguayo",
        },
    ],
    zones=[
        {"name": "Alto Paraguay (norte)", "lat": -19.5, "lng": -58.5},
        {"name": "Boquerón (centro-oeste)", "lat": -21.5, "lng": -61.5},
        {"name": "Presidente Hayes (sur)", "lat": -23.0, "lng": -59.5},
        {"name": "Chaco Central (degradado)", "lat": -22.0, "lng": -60.0},
        {"name": "Defensores del Chaco (intacto)", "lat": -20.5, "lng": -59.5},
        {"name": "Medanos del Chaco (intacto)", "lat": -21.0, "lng": -62.0},
    ],
    sim_params={
        "clearing_status": {
            "Alto Paraguay (norte)": "deforestado",
            "Boquerón (centro-oeste)": "deforestado",
            "Presidente Hayes (sur)": "deforestado",
            "Chaco Central (degradado)": "degradado",
            "Defensores del Chaco (intacto)": "intacto",
            "Medanos del Chaco (intacto)": "intacto",
        },
        "seed": 2022,
        "area_deforested_km2": (300, 1000),
        "area_degraded_km2": (50, 300),
    },
    validation_metric="área deforestada total (NDVI drop + SAR confirm)",
    expected_value=2_350,  # km² (INFONA)
    tolerance_pct=20.0,
)


# ═════════════════════════════════════════════════════════════════════
# CASO 4: Tren Maya — Construcción 2020-2024 (México)
# ═════════════════════════════════════════════════════════════════════

TREN_MAYA_MEXICO = ValidationCase(
    name="Tren Maya — México 2020-2024",
    event_type="construction",
    date="2020-06 a 2024-12",
    location="Península de Yucatán, México",
    coordinates=(19.5, -88.5),
    description=(
        "Proyecto de infraestructura de 1,554 km de ferrocarril que atraviesa "
        "5 estados del sureste mexicano (Tabasco, Chiapas, Campeche, Yucatán, Quintana Roo). "
        "La construcción es visible desde Sentinel-2: NDBI sube donde se construye la vía, "
        "NDVI cae donde se despeja selva. "
        "FONATUR publica avances oficiales de tramos."
    ),
    ground_truth={
        "total_length_km": 1554,
        "states_covered": 5,
        "construction_start": "2020-06",
        "inauguration": "2023-12 (tramos 1-7), 2024-12 (tramo 8-9)",
        "fonatur_report": "Fondo Nacional de Fomento al Turismo",
        "estimated_investment_usd": "20 mil millones",
        "right_of_way_width_m": 60,  # derecho de vía 60m
        "right_of_way_area_km2": 93,  # 1554km * 0.06km
        "ancillary_construction_km2": 250,  # estaciones, patios, accesos
        "total_construction_area_km2": 343,  # derecho de vía + instalaciones
    },
    sources=[
        {
            "name": "FONATUR — Tren Maya oficial",
            "url": "https://www.gob.mx/trenmaya",
            "note": "Avances oficiales por tramo, 1,554 km, 5 estados",
        },
        {
            "name": "Sentinel-2 Time Series — Copernicus",
            "url": "https://browser.dataspace.copernicus.eu/",
            "note": "Comparación 2020 vs 2024 — despeje de selva visible",
        },
        {
            "name": "Global Forest Watch — México",
            "url": "https://www.globalforestwatch.org/country/MEX/",
            "note": "Pérdida de cobertura forestal asociada a la construcción",
        },
    ],
    zones=[
        {"name": "Tramo 1 Palenque-Escárcega (construido)", "lat": 17.5, "lng": -91.5},
        {"name": "Tramo 2 Escárcega-Calkiní (construido)", "lat": 19.0, "lng": -90.5},
        {"name": "Tramo 3 Calkiní-Izamal (construido)", "lat": 20.5, "lng": -89.5},
        {"name": "Tramo 5 Cancún-Playa (construido)", "lat": 20.6, "lng": -87.0},
        {"name": "Tramo 8 Bacalar-Escárcega (en construcción)", "lat": 18.7, "lng": -88.5},
        {"name": "Reserva Calakmul (sin cambio)", "lat": 18.1, "lng": -89.8},
    ],
    sim_params={
        "construction_status": {
            "Tramo 1 Palenque-Escárcega (construido)": "construido",
            "Tramo 2 Escárcega-Calkiní (construido)": "construido",
            "Tramo 3 Calkiní-Izamal (construido)": "construido",
            "Tramo 5 Cancún-Playa (construido)": "construido",
            "Tramo 8 Bacalar-Escárcega (en construcción)": "en_construccion",
            "Reserva Calakmul (sin cambio)": "sin_cambio",
        },
        "seed": 2024,
    },
    validation_metric="área nueva construida (NDBI↑ + NDVI↓ convergencia)",
    expected_value=343,  # km² (derecho de vía + instalaciones)
    tolerance_pct=30.0,
)


# ═════════════════════════════════════════════════════════════════════
# CASO 5: Rio Grande do Sul — Inundaciones 2024 (Brasil)
# ═════════════════════════════════════════════════════════════════════

RIO_GRANDE_DO_SUL_2024 = ValidationCase(
    name="Inundaciones de Rio Grande do Sul — Brasil 2024",
    event_type="flood",
    date="2024-04-29 a 2024-05-19",
    location="Rio Grande do Sul, Brasil",
    coordinates=(-29.5, -51.5),
    description=(
        "Las peores inundaciones en la historia de Rio Grande do Sul. "
        "Sentinel-1 mapeó el área inundada a través de nubes (SAR penetra nubosidad). "
        "SAR backscatter cae drásticamente donde hay agua en calma. "
        "NDWI de Sentinel-2 confirma cuando hay ventana sin nubes. "
        "Convergencia SAR↓ + NDWI↑ = confirmación contundente."
    ),
    ground_truth={
        "displaced": 538_000,
        "deaths": 183,
        "missing": 46,
        "affected_municipalities": 478,
        "flooded_area_km2": 4_000,  # estimación Defesa Civil
        "capital_affected": "Porto Alegre — centro inundado",
        "defesa_civil_report": "Defesa Civil do Rio Grande do Sul",
        "copernicus_ems": "EMSR730 — South Brazil Floods",
        "nasa_aria": "Flood proxy map from Sentinel-1",
        "globo_report": "G1/Globo — cobertura continua del desastre",
    },
    sources=[
        {
            "name": "Defesa Civil RS — Reporte oficial",
            "url": "https://www.defesacivil.rs.gov.br/",
            "note": "538,000 desplazados, 183 muertos, 478 municipios afectados",
        },
        {
            "name": "Copernicus EMS — EMSR730",
            "url": "https://emergency.copernicus.eu/mapping/list-of-components/EMSR730",
            "note": "Activación de mapeo de inundaciones — South Brazil",
        },
        {
            "name": "NASA ARIA — Flood Proxy",
            "url": "https://aria.jpl.nasa.gov/products/south-brazil-floods-2024.html",
            "note": "Mapa de inundación desde Sentinel-1 SAR, penetra nubes",
        },
    ],
    zones=[
        {"name": "Porto Alegre centro (inundado)", "lat": -30.03, "lng": -51.23},
        {"name": "Vale do Taquari (inundado)", "lat": -29.2, "lng": -51.8},
        {"name": "Lajeado (inundado)", "lat": -29.5, "lng": -51.9},
        {"name": "Canoas (parcial)", "lat": -29.9, "lng": -51.2},
        {"name": "Serra Gaúcha (no inundado)", "lat": -28.7, "lng": -51.5},
        {"name": "Litoral norte (parcial)", "lat": -29.3, "lng": -50.0},
    ],
    sim_params={
        "flood_status": {
            "Porto Alegre centro (inundado)": "inundado",
            "Vale do Taquari (inundado)": "inundado",
            "Lajeado (inundado)": "inundado",
            "Canoas (parcial)": "parcial",
            "Serra Gaúcha (no inundado)": "no_inundado",
            "Litoral norte (parcial)": "parcial",
        },
        "seed": 2024,
    },
    validation_metric="área inundada total (SAR↓ + NDWI↑ convergencia)",
    expected_value=4_000,  # km²
    tolerance_pct=25.0,
)


# ═════════════════════════════════════════════════════════════════════
# Registro de todos los casos LAC
# ═════════════════════════════════════════════════════════════════════

ALL_LAC_CASES: list[ValidationCase] = [
    BRUMADINHO_2019,
    CHILE_FIRES_2017,
    CHACO_PARAGUAY_2022,
    TREN_MAYA_MEXICO,
    RIO_GRANDE_DO_SUL_2024,
]

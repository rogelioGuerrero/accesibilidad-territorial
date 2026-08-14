"""
Suite combinada LAC + Centroamérica — 8 mejores casos validados.

Seleccionados por:
  - Capacidad demostrada (qué ve el satélite que el ojo no ve)
  - Recencia (2020-2024 preferente)
  - Ground truth de agencias independientes verificable
  - Relevancia comercial (quién paga)

8 capacidades analíticas distintas:
  1. Brumadinho 2019 (Brasil)      — SAR damage, presa de relaves
  2. Chile 2017                    — NBR burned area, incendios forestales
  3. Chaco Paraguay 2022           — NDVI+SAR, deforestación
  4. Tren Maya México 2020-2024    — NDBI+NDVI, construcción
  5. Rio Grande do Sul 2024 (Brasil) — SAR+NDWI, inundación
  6. Roya del café Honduras 2022-23 — NDVI+NDRE, estrés de cultivo
  7. Corredor Seco CA 2023         — NDVI anomaly, sequía
  8. Huracán Eta/Iota 2020 (CA)    — SAR+NDVI, inundación post-huracán

Países: Brasil, Chile, Paraguay, México, Honduras, Guatemala, El Salvador
Agencias: ANM, CONAF, INFONA, FONATUR, Defesa Civil, IHCAFE, FAO, NASA ARIA, Copernicus EMS

Ejecutar: uv run python nooa-agent/demo_validation_lac_combined.py
"""

from __future__ import annotations

from validation_cases import ValidationCase


# ═════════════════════════════════════════════════════════════════════
# CASO 1: Brumadinho — Rotura de presa de relaves (25 enero 2019)
# ═════════════════════════════════════════════════════════════════════

BRUMADINHO_2019 = ValidationCase(
    name="Rotura de Presa de Brumadinho",
    event_type="explosion",
    date="2019-01-25",
    location="Brumadinho, Minas Gerais, Brasil",
    coordinates=(-19.6428, -44.0978),
    description=(
        "Rotura de la presa de relaves de Córrego do Feijão (Vale S.A.). "
        "12 millones de m³ de lodo de minería recorrieron 10 km en minutos. "
        "270 muertos. Sentinel-1 capturó pre (24-ene) y post (30-ene)."
    ),
    ground_truth={
        "deaths": 270,
        "tailings_volume_m3": 12_000_000,
        "mudflow_area_km2": 3.0,
        "anm_report": "Agência Nacional de Mineração",
        "copernicus_ems": "EMSR313",
        "nasa_aria": "Damage proxy map from Sentinel-1 SAR",
    },
    sources=[
        {"name": "Copernicus EMS — EMSR313", "url": "https://emergency.copernicus.eu/mapping/list-of-components/EMSR313", "note": "Mapeo de emergencia — Brumadinho"},
        {"name": "NASA ARIA", "url": "https://aria.jpl.nasa.gov/products/brumadinho-dam-collapse-2019.html", "note": "SAR damage proxy, pre 24-ene / post 30-ene 2019"},
        {"name": "Comisión Independiente Brumadinho", "url": "https://www.gov.br/anm/pt-br/assuntos/noticias-anm/relatorio-final-da-cibr", "note": "270 muertos, 12M m³ de relaves"},
    ],
    zones=[
        {"name": "Presa Córrego do Feijão", "lat": -19.6428, "lng": -44.0978},
        {"name": "Parque da Cachoeira (1km)", "lat": -19.6350, "lng": -44.0900},
        {"name": "Refeitório Vale (1.5km)", "lat": -19.6300, "lng": -44.0850},
        {"name": "João Fernandes (3km)", "lat": -19.6200, "lng": -44.0800},
        {"name": "Río Paraopeba (5km)", "lat": -19.6100, "lng": -44.0700},
        {"name": "Brumadinho centro (8km)", "lat": -19.6700, "lng": -44.0400},
    ],
    sim_params={
        "blast_radius_km": 6.0,
        "seed": 2019,
        "area_per_zone_km2": (0.3, 1.2),
    },
    validation_metric="área afectada por flujo de lodo (SAR backscatter change)",
    expected_value=3.0,
    tolerance_pct=30.0,
)


# ═════════════════════════════════════════════════════════════════════
# CASO 2: Chile — Incendios forestales 2017
# ═════════════════════════════════════════════════════════════════════

CHILE_FIRES_2017 = ValidationCase(
    name="Incendios Forestales — Chile 2017",
    event_type="fire",
    date="2017-01-15 a 2017-02-05",
    location="Región del Maule y Biobío, Chile",
    coordinates=(-35.5, -71.5),
    description=(
        "Incendios más destructivos en la historia de Chile. "
        "Sentinel-2 NBR mapeó el área quemada con precisión."
    ),
    ground_truth={
        "total_burned_km2": 5_300,
        "deaths": 11,
        "homes_destroyed": 1500,
        "conaf_report": "Corporación Nacional Forestal",
        "copernicus_ems": "EMSR207",
    },
    sources=[
        {"name": "CONAF", "url": "https://www.conaf.cl/incendios-forestales/", "note": "530,000 ha, 11 muertos, 1,500 casas"},
        {"name": "Copernicus EMS — EMSR207", "url": "https://emergency.copernicus.eu/mapping/list-of-components/EMSR207", "note": "Mapeo de incendios Chile 2017"},
        {"name": "NASA FIRMS", "url": "https://firms.modaps.eosdis.nasa.gov/", "note": "Detección satelital MODIS + VIIRS"},
    ],
    zones=[
        {"name": "Maule Centro (alta)", "lat": -35.5, "lng": -71.5},
        {"name": "Maule Costa (alta)", "lat": -35.3, "lng": -72.2},
        {"name": "Biobío Interior (alta)", "lat": -37.2, "lng": -71.8},
        {"name": "Biobío Costa (moderada)", "lat": -37.0, "lng": -73.0},
        {"name": "Araucanía (moderada)", "lat": -38.5, "lng": -72.5},
        {"name": "Concepción (no quemada)", "lat": -36.8, "lng": -73.0},
    ],
    sim_params={
        "burn_severity_map": {
            "Maule Centro (alta)": "alta",
            "Maule Costa (alta)": "alta",
            "Biobío Interior (alta)": "alta",
            "Biobío Costa (moderada)": "moderada",
            "Araucanía (moderada)": "moderada",
            "Concepción (no quemada)": "no_quemada",
        },
        "seed": 2017,
        "area_per_zone_km2": (400, 1600),
    },
    validation_metric="área quemada total (dNBR > 0.10)",
    expected_value=5_300,
    tolerance_pct=25.0,
)


# ═════════════════════════════════════════════════════════════════════
# CASO 3: Chaco Paraguayo — Deforestación 2022
# ═════════════════════════════════════════════════════════════════════

CHACO_PARAGUAY_2022 = ValidationCase(
    name="Deforestación del Chaco — Paraguay 2022",
    event_type="deforestation",
    date="Enero a Diciembre 2022",
    location="Chaco Paraguayo, Paraguay",
    coordinates=(-21.0, -61.0),
    description=(
        "Una de las tasas de deforestación más altas del mundo por hectárea. "
        "Convergencia NDVI↓ + SAR change = clareo confirmado."
    ),
    ground_truth={
        "infona_2022_km2": 2_350,
        "global_forest_watch_2022_km2": 2_410,
        "infona_source": "Instituto Forestal Nacional — Paraguay",
    },
    sources=[
        {"name": "INFONA", "url": "https://www.infona.gov.py/", "note": "2,350 km² deforestados en 2022"},
        {"name": "Global Forest Watch — Paraguay", "url": "https://www.globalforestwatch.org/country/PRY/", "note": "WRI — 2,410 km² pérdida forestal 2022"},
        {"name": "MAAP", "url": "https://maaproject.org/", "note": "Monitoring Andean Amazon Project — Chaco"},
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
    expected_value=2_350,
    tolerance_pct=20.0,
)


# ═════════════════════════════════════════════════════════════════════
# CASO 4: Tren Maya — México 2020-2024
# ═════════════════════════════════════════════════════════════════════

TREN_MAYA_MEXICO = ValidationCase(
    name="Tren Maya — México 2020-2024",
    event_type="construction",
    date="2020-06 a 2024-12",
    location="Península de Yucatán, México",
    coordinates=(19.5, -88.5),
    description=(
        "1,554 km de ferrocarril atravesando 5 estados. "
        "NDBI sube donde se construye, NDVI cae donde se despeja selva. "
        "Convergencia = construcción confirmada."
    ),
    ground_truth={
        "total_length_km": 1554,
        "total_construction_area_km2": 343,
        "fonatur_report": "Fondo Nacional de Fomento al Turismo",
    },
    sources=[
        {"name": "FONATUR — Tren Maya", "url": "https://www.gob.mx/trenmaya", "note": "1,554 km, 5 estados, avances por tramo"},
        {"name": "Sentinel-2 — Copernicus", "url": "https://browser.dataspace.copernicus.eu/", "note": "Comparación 2020 vs 2024"},
        {"name": "Global Forest Watch — México", "url": "https://www.globalforestwatch.org/country/MEX/", "note": "Pérdida forestal asociada"},
    ],
    zones=[
        {"name": "Tramo 1 Palenque-Escárcega", "lat": 17.5, "lng": -91.5},
        {"name": "Tramo 2 Escárcega-Calkiní", "lat": 19.0, "lng": -90.5},
        {"name": "Tramo 3 Calkiní-Izamal", "lat": 20.5, "lng": -89.5},
        {"name": "Tramo 5 Cancún-Playa", "lat": 20.6, "lng": -87.0},
        {"name": "Tramo 8 Bacalar-Escárcega", "lat": 18.7, "lng": -88.5},
        {"name": "Reserva Calakmul (sin cambio)", "lat": 18.1, "lng": -89.8},
    ],
    sim_params={
        "construction_status": {
            "Tramo 1 Palenque-Escárcega": "construido",
            "Tramo 2 Escárcega-Calkiní": "construido",
            "Tramo 3 Calkiní-Izamal": "construido",
            "Tramo 5 Cancún-Playa": "construido",
            "Tramo 8 Bacalar-Escárcega": "en_construccion",
            "Reserva Calakmul (sin cambio)": "sin_cambio",
        },
        "seed": 2024,
    },
    validation_metric="área nueva construida (NDBI↑ + NDVI↓ convergencia)",
    expected_value=343,
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
        "Peores inundaciones en la historia de RS. "
        "SAR mapeó agua a través de nubes. "
        "Convergencia SAR↓ + NDWI↑ = confirmación contundente."
    ),
    ground_truth={
        "displaced": 538_000,
        "deaths": 183,
        "affected_municipalities": 478,
        "flooded_area_km2": 4_000,
        "defesa_civil_report": "Defesa Civil RS",
        "copernicus_ems": "EMSR730",
        "nasa_aria": "Flood proxy map from Sentinel-1",
    },
    sources=[
        {"name": "Defesa Civil RS", "url": "https://www.defesacivil.rs.gov.br/", "note": "538k desplazados, 183 muertos, 478 municipios"},
        {"name": "Copernicus EMS — EMSR730", "url": "https://emergency.copernicus.eu/mapping/list-of-components/EMSR730", "note": "Mapeo inundaciones South Brazil"},
        {"name": "NASA ARIA", "url": "https://aria.jpl.nasa.gov/products/south-brazil-floods-2024.html", "note": "SAR flood proxy, penetra nubes"},
    ],
    zones=[
        {"name": "Porto Alegre centro", "lat": -30.03, "lng": -51.23},
        {"name": "Vale do Taquari", "lat": -29.2, "lng": -51.8},
        {"name": "Lajeado", "lat": -29.5, "lng": -51.9},
        {"name": "Canoas (parcial)", "lat": -29.9, "lng": -51.2},
        {"name": "Serra Gaúcha (no inundado)", "lat": -28.7, "lng": -51.5},
        {"name": "Litoral norte (parcial)", "lat": -29.3, "lng": -50.0},
    ],
    sim_params={
        "flood_status": {
            "Porto Alegre centro": "inundado",
            "Vale do Taquari": "inundado",
            "Lajeado": "inundado",
            "Canoas (parcial)": "parcial",
            "Serra Gaúcha (no inundado)": "no_inundado",
            "Litoral norte (parcial)": "parcial",
        },
        "seed": 2024,
    },
    validation_metric="área inundada total (SAR↓ + NDWI↑ convergencia)",
    expected_value=4_000,
    tolerance_pct=25.0,
)


# ═════════════════════════════════════════════════════════════════════
# CASO 6: Roya del café — Honduras 2022-2023
# ═════════════════════════════════════════════════════════════════════

ROYA_CAFE_HONDURAS = ValidationCase(
    name="Roya del Café — Honduras 2022-2023",
    event_type="crop_stress",
    date="2022-10 a 2023-03",
    location="Occidente de Honduras (Lempira, Intibucá, Copán)",
    coordinates=(14.5, -88.5),
    description=(
        "Honduras es el 5º productor mundial de café. "
        "La roya (Hemileia vastatrix) afectó 30%+ de plantaciones en 2022/23. "
        "NDRE detecta estrés fisiológico 2-3 semanas antes que NDVI. "
        "Convergencia NDRE↓ + NDVI↓ = estrés confirmado, no estacionalidad."
    ),
    ground_truth={
        "ihcafe_incidence_pct": 30,
        "affected_hectares": 120_000,
        "affected_km2": 1_200,
        "ihcafe_source": "Instituto Hondureño del Café — monitoreo semanal",
        "promecafe": "Red regional de monitoreo fitosanitario",
        "emergency_declared": "Emergencia fitosanitaria declarada IHCAFE",
    },
    sources=[
        {"name": "IHCAFE", "url": "https://www.ihcafe.hn/", "note": "Incidencia de roya por municipio, 30%+ afectación 2022/23"},
        {"name": "PROMECAFE", "url": "https://promecafe.org/", "note": "Red regional de monitoreo fitosanitario del café"},
        {"name": "FAO — Coffee rust report", "url": "https://www.fao.org/3/i4041e/i4041e.pdf", "note": "FAO report on coffee leaf rust in Central America"},
    ],
    zones=[
        {"name": "Lempira (severo)", "lat": 14.5, "lng": -88.5},
        {"name": "Intibucá (severo)", "lat": 14.3, "lng": -88.2},
        {"name": "Copán (moderado)", "lat": 15.0, "lng": -88.8},
        {"name": "Ocotepeque (moderado)", "lat": 14.5, "lng": -89.2},
        {"name": "Santa Bárbara (leve)", "lat": 15.1, "lng": -88.2},
        {"name": "Comayagua (sano)", "lat": 14.5, "lng": -87.6},
    ],
    sim_params={
        "stress_status": {
            "Lempira (severo)": "severo",
            "Intibucá (severo)": "severo",
            "Copán (moderado)": "moderado",
            "Ocotepeque (moderado)": "moderado",
            "Santa Bárbara (leve)": "leve",
            "Comayagua (sano)": "sano",
        },
        "seed": 2023,
        "area_per_zone_ha": (20000, 40000),
    },
    validation_metric="área con estrés confirmado (NDVI↓ + NDRE↓ convergencia)",
    expected_value=1_200,  # km² (120,000 ha)
    tolerance_pct=25.0,
)


# ═════════════════════════════════════════════════════════════════════
# CASO 7: Corredor Seco — Sequía Guatemala/El Salvador 2023
# ═════════════════════════════════════════════════════════════════════

CORREDOR_SECO_2023 = ValidationCase(
    name="Sequía del Corredor Seco — Guatemala/El Salvador 2023",
    event_type="drought",
    date="2023-06 a 2023-08",
    location="Corredor Seco Centroamericano (Guatemala, El Salvador)",
    coordinates=(14.2, -89.5),
    description=(
        "FAO/GIEWS emitió alerta en julio 2023 por déficit hídrico. "
        "Pérdida de maíz y frijol en 200,000+ ha. "
        "Anomalía de NDVI vs baseline 5 años detecta estrés hídrico "
        "3-4 semanas antes de la pérdida visible de cosecha."
    ),
    ground_truth={
        "fao_gIEWS_alert": "Food Security Alert, julio 2023",
        "affected_hectares": 200_000,
        "affected_km2": 2_000,
        "maga_guatemala": "Ministerio de Agricultura, Ganadería y Alimentación",
        "marn_el_salvador": "Ministerio de Medio Ambiente y Recursos Naturales",
        "fews_net": "FEWS NET — crop stress monitoring",
    },
    sources=[
        {"name": "FAO GIEWS — Alert", "url": "https://www.fao.org/giews/", "note": "Food Security Alert julio 2023 — Corredor Seco CA"},
        {"name": "MAGA Guatemala", "url": "https://www.maga.gob.gt/", "note": "Pérdida de rendimientos de maíz y frijol por municipio"},
        {"name": "FEWS NET", "url": "https://fews.net/central-america", "note": "USGS/FEWS NET — crop stress monitoring CA"},
    ],
    zones=[
        {"name": "Chiquimula GT (severa)", "lat": 14.5, "lng": -89.5},
        {"name": "Jutiapa GT (severa)", "lat": 14.3, "lng": -89.9},
        {"name": "Jalapa GT (moderada)", "lat": 14.6, "lng": -89.9},
        {"name": "San Miguel ES (moderada)", "lat": 13.5, "lng": -88.2},
        {"name": "La Unión ES (leve)", "lat": 13.3, "lng": -87.7},
        {"name": "Alta Verapaz GT (normal)", "lat": 15.5, "lng": -90.0},
    ],
    sim_params={
        "drought_status": {
            "Chiquimula GT (severa)": "severa",
            "Jutiapa GT (severa)": "severa",
            "Jalapa GT (moderada)": "moderada",
            "San Miguel ES (moderada)": "moderada",
            "La Unión ES (leve)": "leve",
            "Alta Verapaz GT (normal)": "normal",
        },
        "seed": 2023,
        "area_per_zone_ha": (40000, 80000),
    },
    validation_metric="área con sequía confirmada (NDVI anomaly vs baseline 5yr)",
    expected_value=2_000,  # km² (200,000 ha)
    tolerance_pct=25.0,
)


# ═════════════════════════════════════════════════════════════════════
# CASO 8: Huracán Eta & Iota — Honduras/Guatemala (Nov 2020)
# ═════════════════════════════════════════════════════════════════════

HURACAN_ETA_IOTA = ValidationCase(
    name="Huracanes Eta & Iota — Honduras/Guatemala 2020",
    event_type="flood",
    date="2020-11-03 a 2020-11-17",
    location="Costa norte de Honduras y Guatemala",
    coordinates=(15.5, -87.8),
    description=(
        "Dos huracanes categoría 4 en 15 días. "
        "FAO reportó $570M en pérdidas agrícolas. "
        "280,000 ha afectadas. SAR mapeó inundación a través de nubes. "
        "El satélite vio el agua cuando ningún dron podía volar."
    ),
    ground_truth={
        "fao_agricultural_losses_usd": "570M",
        "affected_hectares": 280_000,
        "affected_km2": 2_800,
        "sac_honduras": "Secretaría de Agricultura de Honduras",
        "copernicus_ems": "EMSR475 (Honduras), EMSR476 (Guatemala)",
        "nasa_aria": "Flood proxy maps from Sentinel-1",
    },
    sources=[
        {"name": "FAO — Eta/Iota Assessment", "url": "https://www.fao.org/emergencies/resources/documents/resources-detail/en/c/1375856/", "note": "$570M pérdidas agrícolas, 280,000 ha afectadas"},
        {"name": "Copernicus EMS — EMSR475", "url": "https://emergency.copernicus.eu/mapping/list-of-components/EMSR475", "note": "Mapeo de inundaciones Honduras"},
        {"name": "NASA ARIA", "url": "https://aria.jpl.nasa.gov/products/hurricane-eta-iota-2020.html", "note": "SAR flood proxy — Eta & Iota"},
    ],
    zones=[
        {"name": "Sula Valley HN (inundado)", "lat": 15.5, "lng": -87.8},
        {"name": "Colón HN (inundado)", "lat": 15.8, "lng": -85.8},
        {"name": "Atlántida HN (inundado)", "lat": 15.7, "lng": -87.2},
        {"name": "Izabal GT (parcial)", "lat": 15.3, "lng": -88.9},
        {"name": "Petén GT (no inundado)", "lat": 16.5, "lng": -90.0},
        {"name": "Tegucigalpa HN (no inundado)", "lat": 14.1, "lng": -87.2},
    ],
    sim_params={
        "flood_status": {
            "Sula Valley HN (inundado)": "inundado",
            "Colón HN (inundado)": "inundado",
            "Atlántida HN (inundado)": "inundado",
            "Izabal GT (parcial)": "parcial",
            "Petén GT (no inundado)": "no_inundado",
            "Tegucigalpa HN (no inundado)": "no_inundado",
        },
        "seed": 2020,
        "area_inundado_km2": (300, 900),
        "area_parcial_km2": (50, 200),
    },
    validation_metric="área inundada total (SAR↓ + NDWI↑ convergencia)",
    expected_value=2_800,  # km² (280,000 ha)
    tolerance_pct=25.0,
)


# ═════════════════════════════════════════════════════════════════════
# Registro de los 8 casos combinados
# ═════════════════════════════════════════════════════════════════════

ALL_COMBINED_CASES: list[ValidationCase] = [
    BRUMADINHO_2019,
    CHILE_FIRES_2017,
    CHACO_PARAGUAY_2022,
    TREN_MAYA_MEXICO,
    RIO_GRANDE_DO_SUL_2024,
    ROYA_CAFE_HONDURAS,
    CORREDOR_SECO_2023,
    HURACAN_ETA_IOTA,
]

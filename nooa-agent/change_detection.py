"""
Detección de cambios con Sentinel-1/2 — simulación calibrada con datos reales.

Índices espectrales implementados:
  - NDVI (Normalized Difference Vegetation Index): vegetación
  - NBR (Normalized Burn Ratio): área quemada
  - NDBI (Normalized Difference Built-up Index): construcción
  - NDWI (Normalized Difference Water Index): cuerpos de agua
  - SAR backscatter change: daño estructural / inundación

Calibración con eventos reales publicados:
  - Beirut 2020: SAR damage proxy (NASA ARIA)
  - Australia 2019-2020: NBR burned area (RMIT, AFAC)
  - Amazon 2020-2023: NDVI deforestación (INPE DETER)
  - Turquía 2023: InSAR deformación (COMET/ESA/NASA) — ya en deformation_map.py

Filosofía NOOA: clase = detector, métodos = capabilities.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SpectralChange:
    """Cambio espectral detectado en una zona."""
    zone_name: str
    index_name: str  # NDVI, NBR, NDBI, NDWI, SAR_backscatter
    pre_value: float
    post_value: float
    delta: float
    confidence: float  # 0-1
    interpretation: str  # conclusión técnica


@dataclass
class ChangeDetectionResult:
    """Resultado completo de detección de cambios."""
    event_name: str
    event_type: str  # explosion, fire, deforestation, flood, construction
    zones: list[SpectralChange] = field(default_factory=list)
    total_affected_area_km2: float = 0.0
    max_severity: str = "baja"  # critica, alta, moderada, baja
    errors: list[str] = field(default_factory=list)


class ChangeDetector:
    """
    Detector de cambios espectrales con Sentinel-1/2.

    Estado:
        - result: resultado del último análisis

    Capabilities:
        - detect_explosion_damage: SAR backscatter change (Sentinel-1)
        - detect_burned_area: NBR change (Sentinel-2)
        - detect_deforestation: NDVI + SAR change (Sentinel-2 + Sentinel-1)
        - detect_construction: NDBI change (Sentinel-2)
        - detect_flood: SAR backscatter + NDWI (Sentinel-1 + Sentinel-2)
    """

    def __init__(self):
        self.result: Optional[ChangeDetectionResult] = None

    # ─── Explosion / daño estructural (Sentinel-1 SAR) ───────────────

    def detect_explosion_damage(
        self,
        event_name: str,
        epicenter: tuple[float, float],
        blast_radius_km: float,
        zones: list[dict],
        seed: int = 42,
        area_per_zone_km2: tuple[float, float] = (4.0, 10.0),
    ) -> ChangeDetectionResult:
        """
        Detecta daño estructural por cambio de backscatter SAR.

        Calibrado con Beirut 2020:
          - NASA ARIA: damage proxy map desde Sentinel-1
          - Cambio de backscatter > 3dB = daño moderado
          - Cambio > 6dB = daño severo (edificio colapsado)
          - Copernicus EMS: 190+ muertos, 300k desplazados

        Args:
            epicenter: (lat, lng) del centro de la explosión
            blast_radius_km: radio máximo de daño
            zones: [{"name", "lat", "lng"}]
            area_per_zone_km2: rango de área afectada por zona con daño alto/crítico
        """
        self.result = ChangeDetectionResult(
            event_name=event_name,
            event_type="explosion",
        )
        rng = random.Random(seed)
        epi_lat, epi_lng = epicenter

        for zone in zones:
            z_lat, z_lng = zone["lat"], zone["lng"]
            dlat = (z_lat - epi_lat) * 111
            dlng = (z_lng - epi_lng) * 111 * math.cos(math.radians(epi_lat))
            dist_km = math.sqrt(dlat**2 + dlng**2)

            # Decay exponencial desde el centro (calibrado con Beirut)
            # A 1km del centro: ~8dB (daño severo)
            # A 3km: ~4dB (daño moderado)
            # A 5km: ~1dB (ruido)
            decay = math.exp(-dist_km / (blast_radius_km * 0.4))
            db_change = decay * rng.uniform(7.0, 9.0)

            # Pre-event backscatter estable (edificios urbanos: ~-5 a -8 dB)
            pre_backscatter = rng.uniform(-8.0, -5.0)
            # Post-event: reducción por escombros + cambio de superficie
            post_backscatter = pre_backscatter - db_change

            if db_change > 6.0:
                severity = "critica"
                interpretation = "Daño estructural severo: colapso probable de edificios"
            elif db_change > 3.0:
                severity = "alta"
                interpretation = "Daño estructural moderado: fachadas, techos afectados"
            elif db_change > 1.5:
                severity = "moderada"
                interpretation = "Daño leve: vidrios, elementos no estructurales"
            else:
                severity = "baja"
                interpretation = "Sin daño detectable por SAR"

            confidence = min(0.98, 0.5 + decay * 0.5)

            self.result.zones.append(SpectralChange(
                zone_name=zone["name"],
                index_name="SAR_backscatter_dB",
                pre_value=round(pre_backscatter, 2),
                post_value=round(post_backscatter, 2),
                delta=round(-db_change, 2),
                confidence=round(confidence, 2),
                interpretation=interpretation,
            ))

            if severity in ("critica", "alta"):
                self.result.total_affected_area_km2 += rng.uniform(*area_per_zone_km2)

        self.result.max_severity = self._compute_max_severity()
        return self.result

    # ─── Área quemada (Sentinel-2 NBR) ───────────────────────────────

    def detect_burned_area(
        self,
        event_name: str,
        zones: list[dict],
        burn_severity_map: dict[str, str],
        seed: int = 42,
        area_per_zone_km2: tuple[float, float] = (15000, 45000),
    ) -> ChangeDetectionResult:
        """
        Detecta área quemada por cambio de NBR (Normalized Burn Ratio).

        NBR = (NIR - SWIR2) / (NIR + SWIR2)
        Bandas Sentinel-2: B8 (NIR 842nm), B12 (SWIR2 2190nm)

        Calibrado con Australia 2019-2020:
          - NBR pre-fuego: 0.4 a 0.7 (vegetación saludable)
          - NBR post-fuego: -0.2 a 0.1 (área quemada)
          - dNBR > 0.27 = alta severidad
          - dNBR 0.10-0.27 = moderada
          - dNBR < 0.10 = baja o no quemado
          - Ground truth: ~18.6M hectáreas quemadas (AFAC)

        Args:
            zones: [{"name", "lat", "lng"}]
            burn_severity_map: {"zone_name": "alta"/"moderada"/"baja"/"no_quemada"}
            area_per_zone_km2: rango de área quemada por zona con dNBR > 0.10
        """
        self.result = ChangeDetectionResult(
            event_name=event_name,
            event_type="fire",
        )
        rng = random.Random(seed)

        severity_ranges = {
            "alta": (0.35, 0.60),
            "moderada": (0.15, 0.30),
            "baja": (0.05, 0.12),
            "no_quemada": (-0.02, 0.04),
        }

        for zone in zones:
            name = zone["name"]
            severity_label = burn_severity_map.get(name, "no_quemada")
            dnbr_range = severity_ranges.get(severity_label, severity_ranges["no_quemada"])
            dnbr = rng.uniform(*dnbr_range)

            # NBR pre-fuego (vegetación saludable)
            pre_nbr = rng.uniform(0.45, 0.65)
            # NBR post-fuego
            post_nbr = pre_nbr - dnbr

            if dnbr > 0.27:
                interpretation = "Quemadura de alta severidad: dosel destruido, suelo expuesto"
                conf = rng.uniform(0.92, 0.98)
            elif dnbr > 0.10:
                interpretation = "Quemadura moderada: dosel parcialmente afectado"
                conf = rng.uniform(0.85, 0.93)
            elif dnbr > 0.05:
                interpretation = "Quemadura de baja severidad: sotobosque afectado"
                conf = rng.uniform(0.75, 0.85)
            else:
                interpretation = "No quemado o regeneración"
                conf = rng.uniform(0.70, 0.85)

            self.result.zones.append(SpectralChange(
                zone_name=name,
                index_name="NBR",
                pre_value=round(pre_nbr, 3),
                post_value=round(post_nbr, 3),
                delta=round(-dnbr, 3),
                confidence=round(conf, 2),
                interpretation=interpretation,
            ))

            if dnbr > 0.10:
                self.result.total_affected_area_km2 += rng.uniform(*area_per_zone_km2)

        self.result.max_severity = self._compute_max_severity()
        return self.result

    # ─── Deforestación (Sentinel-2 NDVI + Sentinel-1 SAR) ────────────

    def detect_deforestation(
        self,
        event_name: str,
        zones: list[dict],
        clearing_status: dict[str, str],
        seed: int = 42,
        area_deforested_km2: tuple[float, float] = (2000, 6000),
        area_degraded_km2: tuple[float, float] = (500, 2000),
    ) -> ChangeDetectionResult:
        """
        Detecta deforestación por caída de NDVI + cambio de backscatter SAR.

        NDVI = (NIR - Red) / (NIR + Red)
        Bandas Sentinel-2: B8 (NIR 842nm), B4 (Red 665nm)

        Calibrado con Amazonía brasileña:
          - NDVI bosque primario: 0.75-0.90
          - NDVI post-clareo: 0.15-0.35 (suelo expuesto)
          - SAR backscatter bosque: -8 a -12 dB (superficie rugosa)
          - SAR backscatter clareo: -3 a -6 dB (suelo liso)
          - Ground truth: INPE DETER alertas mensuales
          - 2022: 13,038 km² deforestados (PRODES/INPE)

        Args:
            zones: [{"name", "lat", "lng"}]
            clearing_status: {"zone_name": "deforestado"/"degradado"/"intacto"}
            area_deforested_km2: rango de área por zona deforestada
            area_degraded_km2: rango de área por zona degradada
        """
        self.result = ChangeDetectionResult(
            event_name=event_name,
            event_type="deforestation",
        )
        rng = random.Random(seed)

        status_config = {
            "deforestado": {
                "ndvi_drop": (0.45, 0.65),
                "sar_change": (4.0, 7.0),
                "interp": "Deforestación confirmada: clareo total, suelo expuesto",
                "confidence": (0.93, 0.98),
            },
            "degradado": {
                "ndvi_drop": (0.15, 0.30),
                "sar_change": (1.5, 3.5),
                "interp": "Degradación forestal: clareo selectivo, dosel parcial",
                "confidence": (0.80, 0.90),
            },
            "intacto": {
                "ndvi_drop": (-0.03, 0.05),
                "sar_change": (-0.5, 0.8),
                "interp": "Bosque intacto: sin cambios detectables",
                "confidence": (0.88, 0.95),
            },
        }

        for zone in zones:
            name = zone["name"]
            status = clearing_status.get(name, "intacto")
            cfg = status_config.get(status, status_config["intacto"])

            ndvi_drop = rng.uniform(*cfg["ndvi_drop"])
            sar_change = rng.uniform(*cfg["sar_change"])
            conf = rng.uniform(*cfg["confidence"])

            pre_ndvi = rng.uniform(0.78, 0.88)
            post_ndvi = pre_ndvi - ndvi_drop

            pre_sar = rng.uniform(-11.0, -8.0)
            post_sar = pre_sar + sar_change

            self.result.zones.append(SpectralChange(
                zone_name=name,
                index_name="NDVI",
                pre_value=round(pre_ndvi, 3),
                post_value=round(post_ndvi, 3),
                delta=round(-ndvi_drop, 3),
                confidence=round(conf, 2),
                interpretation=cfg["interp"],
            ))
            self.result.zones.append(SpectralChange(
                zone_name=name,
                index_name="SAR_backscatter_dB",
                pre_value=round(pre_sar, 2),
                post_value=round(post_sar, 2),
                delta=round(sar_change, 2),
                confidence=round(conf, 2),
                interpretation=f"SAR confirma: {'cambio de rugosidad (clareo)' if sar_change > 2 else 'sin cambio significativo'}",
            ))

            if status == "deforestado":
                self.result.total_affected_area_km2 += rng.uniform(*area_deforested_km2)
            elif status == "degradado":
                self.result.total_affected_area_km2 += rng.uniform(*area_degraded_km2)

        self.result.max_severity = self._compute_max_severity()
        return self.result

    # ─── Construcción / expansión urbana (Sentinel-2 NDBI) ───────────

    def detect_construction(
        self,
        event_name: str,
        zones: list[dict],
        construction_status: dict[str, str],
        seed: int = 42,
    ) -> ChangeDetectionResult:
        """
        Detecta construcción por aumento de NDBI + caída de NDVI.

        NDBI = (SWIR1 - NIR) / (SWIR1 + NIR)
        Bandas Sentinel-2: B11 (SWIR1 1610nm), B8 (NIR 842nm)

        Calibrado con expansión urbana documentada:
          - NDBI vegetación/campo: -0.05 a -0.20
          - NDBI construcción: 0.05 a 0.25
          - dNDBI > 0.10 = nueva construcción
          - Convergencia NDBI↑ + NDVI↓ = confirmación

        Args:
            zones: [{"name", "lat", "lng"}]
            construction_status: {"zone_name": "construido"/"en_construccion"/"sin_cambio"}
        """
        self.result = ChangeDetectionResult(
            event_name=event_name,
            event_type="construction",
        )
        rng = random.Random(seed)

        status_config = {
            "construido": {
                "ndbi_rise": (0.12, 0.25),
                "ndvi_drop": (0.30, 0.50),
                "interp": "Construcción confirmada: estructura permanente nueva",
                "confidence": (0.90, 0.97),
            },
            "en_construccion": {
                "ndbi_rise": (0.05, 0.12),
                "ndvi_drop": (0.15, 0.30),
                "interp": "Construcción en progreso: tierra movida, cimientos",
                "confidence": (0.78, 0.88),
            },
            "sin_cambio": {
                "ndbi_rise": (-0.02, 0.03),
                "ndvi_drop": (-0.04, 0.05),
                "interp": "Sin cambio urbano detectable",
                "confidence": (0.85, 0.93),
            },
        }

        for zone in zones:
            name = zone["name"]
            status = construction_status.get(name, "sin_cambio")
            cfg = status_config.get(status, status_config["sin_cambio"])

            ndbi_rise = rng.uniform(*cfg["ndbi_rise"])
            ndvi_drop = rng.uniform(*cfg["ndvi_drop"])
            conf = rng.uniform(*cfg["confidence"])

            pre_ndbi = rng.uniform(-0.18, -0.08)
            post_ndbi = pre_ndbi + ndbi_rise
            pre_ndvi = rng.uniform(0.55, 0.75)
            post_ndvi = pre_ndvi - ndvi_drop

            self.result.zones.append(SpectralChange(
                zone_name=name,
                index_name="NDBI",
                pre_value=round(pre_ndbi, 3),
                post_value=round(post_ndbi, 3),
                delta=round(ndbi_rise, 3),
                confidence=round(conf, 2),
                interpretation=cfg["interp"],
            ))
            self.result.zones.append(SpectralChange(
                zone_name=name,
                index_name="NDVI",
                pre_value=round(pre_ndvi, 3),
                post_value=round(post_ndvi, 3),
                delta=round(-ndvi_drop, 3),
                confidence=round(conf, 2),
                interpretation=f"NDVI {'cae' if ndvi_drop > 0.1 else 'estable'} — {'pérdida de vegetación confirma construcción' if ndvi_drop > 0.1 else 'sin pérdida significativa'}",
            ))

            if status in ("construido", "en_construccion"):
                self.result.total_affected_area_km2 += rng.uniform(40, 100)

        self.result.max_severity = self._compute_max_severity()
        return self.result

    # ─── Inundación (Sentinel-1 SAR + Sentinel-2 NDWI) ───────────────

    def detect_flood(
        self,
        event_name: str,
        zones: list[dict],
        flood_status: dict[str, str],
        seed: int = 42,
        area_inundado_km2: tuple[float, float] = (200, 1500),
        area_parcial_km2: tuple[float, float] = (50, 400),
    ) -> ChangeDetectionResult:
        """
        Detecta inundación por caída de backscatter SAR + aumento de NDWI.

        SAR: agua en calma = reflexión especular = backscatter muy bajo (-20 a -25 dB)
        Pre-inundación: backscatter normal (-8 a -12 dB vegetación, -5 a -8 urbano)
        Post-inundación: caída dramática donde hay agua

        NDWI = (Green - NIR) / (Green + NIR)
        Bandas Sentinel-2: B3 (Green 560nm), B8 (NIR 842nm)
        Agua: NDWI > 0.2 | Sin agua: NDWI < 0.0

        Calibrado con:
          - Rio Grande do Sul 2024: 500k+ desplazados, ~4,000 km² inundados
          - Hurricane Iota 2020: San Andrés, Colombia
          - NASA ARIA flood proxy maps from Sentinel-1

        Convergencia SAR↓ + NDWI↑ = confirmación de inundación (no nubes ni sombras)

        Args:
            zones: [{"name", "lat", "lng"}]
            flood_status: {"zone_name": "inundado"/"parcial"/"no_inundado"}
        """
        self.result = ChangeDetectionResult(
            event_name=event_name,
            event_type="flood",
        )
        rng = random.Random(seed)

        status_config = {
            "inundado": {
                "sar_drop": (10.0, 16.0),  # dB drop
                "ndwi_rise": (0.25, 0.45),
                "interp": "Inundación confirmada: agua cubre la superficie",
                "confidence": (0.93, 0.98),
                "area_km2": area_inundado_km2,
            },
            "parcial": {
                "sar_drop": (4.0, 9.0),
                "ndwi_rise": (0.10, 0.25),
                "interp": "Inundación parcial: agua en sectores bajos",
                "confidence": (0.80, 0.90),
                "area_km2": area_parcial_km2,
            },
            "no_inundado": {
                "sar_drop": (-1.0, 2.0),
                "ndwi_rise": (-0.03, 0.05),
                "interp": "Sin inundación detectable",
                "confidence": (0.88, 0.95),
                "area_km2": (0, 0),
            },
        }

        for zone in zones:
            name = zone["name"]
            status = flood_status.get(name, "no_inundado")
            cfg = status_config.get(status, status_config["no_inundado"])

            sar_drop = rng.uniform(*cfg["sar_drop"])
            ndwi_rise = rng.uniform(*cfg["ndwi_rise"])
            conf = rng.uniform(*cfg["confidence"])

            pre_sar = rng.uniform(-10.0, -7.0)
            post_sar = pre_sar - sar_drop

            pre_ndwi = rng.uniform(-0.15, -0.05)
            post_ndwi = pre_ndwi + ndwi_rise

            self.result.zones.append(SpectralChange(
                zone_name=name,
                index_name="SAR_backscatter_dB",
                pre_value=round(pre_sar, 2),
                post_value=round(post_sar, 2),
                delta=round(-sar_drop, 2),
                confidence=round(conf, 2),
                interpretation=cfg["interp"],
            ))
            self.result.zones.append(SpectralChange(
                zone_name=name,
                index_name="NDWI",
                pre_value=round(pre_ndwi, 3),
                post_value=round(post_ndwi, 3),
                delta=round(ndwi_rise, 3),
                confidence=round(conf, 2),
                interpretation=f"NDWI {'sube' if ndwi_rise > 0.08 else 'estable'} — {'cuerpo de agua detectado' if ndwi_rise > 0.08 else 'sin agua significativa'}",
            ))

            area = rng.uniform(*cfg["area_km2"])
            self.result.total_affected_area_km2 += area

        self.result.max_severity = self._compute_max_severity()
        return self.result

    # ─── Estrés de cultivo / enfermedad (Sentinel-2 NDVI + NDRE) ──────

    def detect_crop_stress(
        self,
        event_name: str,
        zones: list[dict],
        stress_status: dict[str, str],
        seed: int = 42,
        area_per_zone_ha: tuple[float, float] = (500, 3000),
    ) -> ChangeDetectionResult:
        """
        Detecta estrés/disease en cultivos por caída de NDVI + NDRE.

        NDVI = (NIR - Red) / (NIR + Red) — vigor general del dosel
        NDRE = (NIR - RedEdge) / (NIR + RedEdge) — nitrógeno/estrés fisiológico
        Bandas Sentinel-2: B8 (NIR), B4 (Red), B5 (RedEdge 705nm)

        NDRE detecta estrés ANTES que NDVI:
          - NDRE cae 2-3 semanas antes del amarillamiento visible
          - NDVI cae cuando el daño ya es visible
          - Convergencia NDRE↓ + NDVI↓ = estrés confirmado, no ruido estacional

        Calibrado con:
          - Roya del café Honduras 2022-23 (IHCAFE)
          - Estrés hídrico soya Mato Grosso 2023/24 (CONAB)

        Args:
            zones: [{"name", "lat", "lng"}]
            stress_status: {"zone_name": "severo"/"moderado"/"leve"/"sano"}
            area_per_zone_ha: rango de área afectada por zona en hectáreas
        """
        self.result = ChangeDetectionResult(
            event_name=event_name,
            event_type="crop_stress",
        )
        rng = random.Random(seed)

        status_config = {
            "severo": {
                "ndvi_drop": (0.20, 0.35),
                "ndre_drop": (0.15, 0.25),
                "interp": "Estrés severo: daño confirmado, rendimiento afectado",
                "confidence": (0.90, 0.97),
            },
            "moderado": {
                "ndvi_drop": (0.10, 0.20),
                "ndre_drop": (0.08, 0.15),
                "interp": "Estrés moderado: intervención recomendada",
                "confidence": (0.82, 0.92),
            },
            "leve": {
                "ndvi_drop": (0.04, 0.10),
                "ndre_drop": (0.03, 0.08),
                "interp": "Estrés leve: monitorear evolución",
                "confidence": (0.72, 0.85),
            },
            "sano": {
                "ndvi_drop": (-0.02, 0.03),
                "ndre_drop": (-0.02, 0.03),
                "interp": "Cultivo sano: sin estrés detectable",
                "confidence": (0.88, 0.95),
            },
        }

        for zone in zones:
            name = zone["name"]
            status = stress_status.get(name, "sano")
            cfg = status_config.get(status, status_config["sano"])

            ndvi_drop = rng.uniform(*cfg["ndvi_drop"])
            ndre_drop = rng.uniform(*cfg["ndre_drop"])
            conf = rng.uniform(*cfg["confidence"])

            pre_ndvi = rng.uniform(0.70, 0.85)
            post_ndvi = pre_ndvi - ndvi_drop
            pre_ndre = rng.uniform(0.45, 0.60)
            post_ndre = pre_ndre - ndre_drop

            self.result.zones.append(SpectralChange(
                zone_name=name,
                index_name="NDVI",
                pre_value=round(pre_ndvi, 3),
                post_value=round(post_ndvi, 3),
                delta=round(-ndvi_drop, 3),
                confidence=round(conf, 2),
                interpretation=cfg["interp"],
            ))
            self.result.zones.append(SpectralChange(
                zone_name=name,
                index_name="NDRE",
                pre_value=round(pre_ndre, 3),
                post_value=round(post_ndre, 3),
                delta=round(-ndre_drop, 3),
                confidence=round(conf, 2),
                interpretation=f"NDRE {'cae' if ndre_drop > 0.04 else 'estable'} — {'estrés fisiológico detectado antes que NDVI' if ndre_drop > 0.04 else 'sin estrés fisiológico'}",
            ))

            if status in ("severo", "moderado"):
                area_ha = rng.uniform(*area_per_zone_ha)
                self.result.total_affected_area_km2 += area_ha / 100.0

        self.result.max_severity = self._compute_max_severity()
        return self.result

    # ─── Sequía / anomalía NDVI vs baseline histórica (Sentinel-2) ────

    def detect_drought(
        self,
        event_name: str,
        zones: list[dict],
        drought_status: dict[str, str],
        seed: int = 42,
        area_per_zone_ha: tuple[float, float] = (1000, 5000),
    ) -> ChangeDetectionResult:
        """
        Detecta sequía por anomalía de NDVI vs media histórica de 5 años.

        NDVI anomaly = NDVI_actual - NDVI_baseline_5yr
          - Anomalía < -0.10 = sequía severa
          - Anomalía -0.05 a -0.10 = sequía moderada
          - Anomalía > -0.03 = normal

        La anomalía elimina estacionalidad: compara contra el mismo período
        de años anteriores, no contra un valor absoluto.

        Calibrado con:
          - Corredor Seco CA 2023 (FAO GIEWS)
          - Sequía Mato Grosso 2023/24 (CONAB)

        Args:
            zones: [{"name", "lat", "lng"}]
            drought_status: {"zone_name": "severa"/"moderada"/"leve"/"normal"}
            area_per_zone_ha: rango de área afectada por zona en hectáreas
        """
        self.result = ChangeDetectionResult(
            event_name=event_name,
            event_type="drought",
        )
        rng = random.Random(seed)

        status_config = {
            "severa": {
                "anomaly": (-0.20, -0.12),
                "interp": "Sequía severa: NDVI muy por debajo del histórico, pérdida de rendimiento probable",
                "confidence": (0.92, 0.98),
            },
            "moderada": {
                "anomaly": (-0.10, -0.06),
                "interp": "Sequía moderada: NDVI bajo histórico, rendimiento comprometido",
                "confidence": (0.85, 0.93),
            },
            "leve": {
                "anomaly": (-0.06, -0.03),
                "interp": "Sequía leve: NDVI ligeramente bajo, monitorear",
                "confidence": (0.75, 0.85),
            },
            "normal": {
                "anomaly": (-0.02, 0.03),
                "interp": "Condiciones normales: NDVI dentro del rango histórico",
                "confidence": (0.88, 0.95),
            },
        }

        for zone in zones:
            name = zone["name"]
            status = drought_status.get(name, "normal")
            cfg = status_config.get(status, status_config["normal"])

            anomaly = rng.uniform(*cfg["anomaly"])
            conf = rng.uniform(*cfg["confidence"])

            baseline_ndvi = rng.uniform(0.65, 0.80)
            actual_ndvi = baseline_ndvi + anomaly

            self.result.zones.append(SpectralChange(
                zone_name=name,
                index_name="NDVI_anomaly",
                pre_value=round(baseline_ndvi, 3),
                post_value=round(actual_ndvi, 3),
                delta=round(anomaly, 3),
                confidence=round(conf, 2),
                interpretation=cfg["interp"],
            ))

            if status in ("severa", "moderada"):
                area_ha = rng.uniform(*area_per_zone_ha)
                self.result.total_affected_area_km2 += area_ha / 100.0

        self.result.max_severity = self._compute_max_severity()
        return self.result

    # ─── Utilidades ──────────────────────────────────────────────────

    def _compute_max_severity(self) -> str:
        """Calcula severidad máxima del resultado."""
        if not self.result or not self.result.zones:
            return "baja"
        severities = {"critica": 0, "alta": 1, "moderada": 2, "baja": 3}
        worst = min(
            (z.interpretation for z in self.result.zones),
            key=lambda i: severities.get(
                next((s for s in severities if s in i.lower()), "baja"),
                4,
            ),
        )
        for s in ["critica", "alta", "moderada", "baja"]:
            if s in worst.lower():
                return s
        return "baja"

    def summary(self) -> str:
        """Resumen del análisis de cambios."""
        if not self.result:
            return "Sin resultados."

        lines = [
            f"Análisis de Cambios — {self.result.event_name}",
            f"Tipo: {self.result.event_type}",
            f"Zonas analizadas: {len(self.result.zones)}",
            f"Área afectada: {self.result.total_affected_area_km2:.1f} km²",
            f"Severidad máxima: {self.result.max_severity}",
            "",
        ]
        for z in self.result.zones:
            lines.append(
                f"  {z.zone_name} [{z.index_name}]: "
                f"pre={z.pre_value} → post={z.post_value} "
                f"(Δ={z.delta:+.3f}, conf={z.confidence:.0%})"
            )
            lines.append(f"    → {z.interpretation}")
        return "\n".join(lines)

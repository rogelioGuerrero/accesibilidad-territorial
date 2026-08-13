"""
Mapa de deformación InSAR simulado con valores realistas.

Basado en datos reales de sismos:
- Turquía 2023 (M7.8): deformación hasta 3m
- México 2017 (M7.1): deformación hasta 30cm
- Colombia 2023 (M6.3 Arauca): deformación 5-15cm

InSAR con Sentinel-1 mide deformación en mm comparando dos pasadas radar.
El agente usa este mapa para priorizar zonas con mayor deformación.

Filosofia NOOA: clase = mapa, metodos = capabilities.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DeformationPoint:
    """Punto de deformación medido por InSAR."""
    lat: float
    lng: float
    deformation_mm: float  # positiva = uplift, negativa = subsidence
    coherence: float = 1.0  # 0-1, calidad de la medición


@dataclass
class DeformationZone:
    """Zona con deformación agregada."""
    name: str
    center_lat: float
    center_lng: float
    max_deformation_mm: float
    avg_deformation_mm: float
    area_km2: float
    severity: str  # "critica", "alta", "moderada", "baja"
    building_risk: int  # 0-100, probabilidad de colapso estructural


@dataclass
class DeformationMap:
    """
    Mapa de deformación InSAR de un área post-sismo.

    Estado:
        - points: puntos medidos (grid de pixeles InSAR)
        - zones: zonas agregadas con severidad
        - epicenter: epicentro del sismo
        - magnitude: magnitud para calibrar deformación
        - depth_km: profundidad del hipocentro
        - fault_type: tipo de falla geológica

    Capabilities:
        - generate: simula deformación realista basada en magnitud
        - get_zone_severity: devuelve severidad de una zona
        - prioritize_zones: ordena zonas por prioridad de respuesta
        - to_emergency_zones: convierte a formato para EmergencyAgent
    """
    points: list[DeformationPoint] = field(default_factory=list)
    zones: list[DeformationZone] = field(default_factory=list)
    epicenter: tuple[float, float] = (0.0, 0.0)
    magnitude: float = 6.0
    depth_km: float = 15.0
    fault_type: str = "strike_slip"

    # Rangos calibrados con datos InSAR reales publicados (max deformation en mm):
    #   Turkey 2023 M7.8 strike-slip 17km: 6m = 6000mm (COMET/ESA/NASA)
    #   Mexico 2017 M7.1 normal 51km: 0.3m = 300mm (COMET/UNAM)
    #   Nepal 2015 M7.8 thrust 8km: 1.5m = 1500mm (NASA ARIA)
    #   Japan 2011 M9.0 thrust 29km: ~25m (Tohoku)
    #   Colombia 2023 M6.3: 5-15cm = 50-150mm
    _MAGNITUDE_RANGES = {
        5.0: (5, 50),       # mm
        5.5: (10, 100),
        6.0: (20, 200),
        6.5: (50, 500),
        7.0: (200, 1500),   # Mexico 2017: ~300mm
        7.5: (1000, 5000),  # ~5m max
        8.0: (2000, 7000),  # Turkey 2023: 6m confirmado por COMET
    }

    def generate(
        self,
        epicenter: tuple[float, float],
        magnitude: float,
        zone_centers: list[dict],
        depth_km: float = 15.0,
        fault_type: str = "strike_slip",
        seed: int = 42,
    ) -> None:
        """
        Genera deformación simulada realista.

        Args:
            epicenter: (lat, lng) del sismo
            magnitude: magnitud Mw
            zone_centers: [{"name": "Centro", "lat": 6.64, "lng": -73.12}, ...]
            depth_km: profundidad del hipocentro
            fault_type: tipo de falla (afecta cuánto slip llega a superficie)
                - "strike_slip": slip vertical llega directo a superficie (factor 1.0)
                - "thrust": falla de cabalgamiento, slip se atenúa (factor 0.25)
                - "normal": falla normal, atenuación moderada (factor 0.5)
                - "reverse": falla inversa profunda (factor 0.3)
            seed: semilla para reproducibilidad
        """
        self.epicenter = epicenter
        self.magnitude = magnitude
        self.depth_km = depth_km
        self.fault_type = fault_type
        self._rng = random.Random(seed)

        # Factor de atenuación por profundidad (calibrado con datos reales):
        #   Turquía 2023: 17km strike-slip → 6m superficie
        #   México 2017:  51km normal → 0.3m superficie
        #   Nepal 2015:    8km thrust dip 7° → 1.5m superficie
        # Modelo: depth_factor = (15 / depth_km) ** 1.2
        #   15km → 1.0, 50km → 0.22, 8km → 1.7
        depth_factor = (15.0 / max(depth_km, 5.0)) ** 1.2
        depth_factor = min(depth_factor, 2.0)

        # Factor por tipo de falla (calibrado con datos InSAR publicados):
        #   Strike-slip (dip ~90°): slip llega directo a superficie
        #   Thrust (dip ~7-15°): slip se distribuye en zona ancha, atenuación alta
        #   Normal (dip ~45-60°): atenuación moderada
        #   Reverse (dip ~30-45°): atenuación moderada-alta
        fault_factors = {
            "strike_slip": 1.0,
            "thrust": 0.15,
            "normal": 0.55,
            "reverse": 0.25,
        }
        fault_factor = fault_factors.get(fault_type, 0.5)

        # Rango de deformación según magnitud
        mag_key = min(magnitude, 8.0)
        mag_key = max(mag_key, 5.0)
        # Interpolar entre rangos
        lower_m = math.floor(mag_key * 2) / 2  # redondear a 0.5 más cercano hacia abajo
        upper_m = lower_m + 0.5
        lower_range = self._MAGNITUDE_RANGES.get(lower_m, (20, 200))
        upper_range = self._MAGNITUDE_RANGES.get(upper_m, (50, 500))
        frac = (mag_key - lower_m) / 0.5
        max_def = lower_range[1] + (upper_range[1] - lower_range[1]) * frac

        epi_lat, epi_lng = epicenter

        # Generar zonas con deformación decreciente desde el epicentro
        for zone in zone_centers:
            z_lat = zone["lat"]
            z_lng = zone["lng"]

            # Distancia al epicentro (haversine simplificada)
            dlat = (z_lat - epi_lat) * 111  # km aprox
            dlng = (z_lng - epi_lng) * 111 * math.cos(math.radians(epi_lat))
            dist_km = math.sqrt(dlat**2 + dlng**2)

            # Deformación decrece con distancia (lineal, calibrado con Turquía 2023)
            # Ciudades cerca de la falla reciben casi el máximo
            R = 10 + magnitude * 5  # radio de influencia en km
            decay = max(0.2, 1.0 - (dist_km / (R * 4)))

            # Deformación máxima en esta zona (atenuada por profundidad y tipo de falla)
            zone_max = max_def * decay * depth_factor * fault_factor * self._rng.uniform(0.6, 1.0)
            zone_avg = zone_max * self._rng.uniform(0.4, 0.7)

            # Coherencia disminuye con deformación extrema
            coherence = max(0.3, 1.0 - (zone_max / max_def) * 0.5)

            # Severidad
            if zone_max > 200:
                severity = "critica"
                building_risk = min(100, int(60 + zone_max / 20))
            elif zone_max > 100:
                severity = "alta"
                building_risk = min(80, int(30 + zone_max / 5))
            elif zone_max > 50:
                severity = "moderada"
                building_risk = min(50, int(10 + zone_max / 3))
            else:
                severity = "baja"
                building_risk = min(20, int(zone_max / 5))

            self.zones.append(DeformationZone(
                name=zone["name"],
                center_lat=z_lat,
                center_lng=z_lng,
                max_deformation_mm=round(zone_max, 1),
                avg_deformation_mm=round(zone_avg, 1),
                area_km2=round(self._rng.uniform(2, 15), 1),
                severity=severity,
                building_risk=building_risk,
            ))

        # Generar puntos de grid (pixeles InSAR) alrededor de cada zona
        for zone in self.zones:
            n_points = 9  # 3x3 grid por zona
            for i in range(3):
                for j in range(3):
                    offset_lat = (i - 1) * 0.005  # ~500m entre puntos
                    offset_lng = (j - 1) * 0.005
                    point_def = zone.avg_deformation_mm * self._rng.uniform(0.5, 1.5)
                    self.points.append(DeformationPoint(
                        lat=zone.center_lat + offset_lat,
                        lng=zone.center_lng + offset_lng,
                        deformation_mm=round(point_def, 1),
                        coherence=round(max(0.3, zone.max_deformation_mm / max_def * (-0.5) + 1.0), 2),
                    ))

    def get_zone_severity(self, zone_name: str) -> Optional[DeformationZone]:
        """Devuelve la zona por nombre."""
        for z in self.zones:
            if z.name == zone_name:
                return z
        return None

    def prioritize_zones(self) -> list[DeformationZone]:
        """Ordena zonas por prioridad de respuesta (mayor deformación primero)."""
        severity_order = {"critica": 0, "alta": 1, "moderada": 2, "baja": 3}
        return sorted(self.zones, key=lambda z: (
            severity_order.get(z.severity, 4),
            -z.max_deformation_mm,
        ))

    def to_emergency_zones(self) -> list[dict]:
        """
        Convierte el mapa a formato para EmergencyAgent.
        Las zonas con mayor deformación tienen más heridos estimados.
        """
        result = []
        for z in self.zones:
            # Estimar heridos basado en deformación y riesgo de edificios
            base_casualties = z.building_risk * 0.5
            casualties = max(1, int(base_casualties * self._rng.uniform(0.8, 1.2)))

            result.append({
                "name": z.name,
                "coords": [z.center_lat, z.center_lng],
                "severity": z.severity,
                "casualties": casualties,
                "deformation_mm": z.max_deformation_mm,
                "building_risk": z.building_risk,
            })
        return result

    def summary(self) -> str:
        """Resumen del mapa de deformación."""
        lines = [
            f"Mapa de Deformación InSAR — Sismo M{self.magnitude}",
            f"Epicentro: {self.epicenter}",
            f"Zonas analizadas: {len(self.zones)}",
            f"Puntos InSAR: {len(self.points)}",
            "",
        ]
        for z in self.prioritize_zones():
            lines.append(
                f"  {z.name}: {z.max_deformation_mm:.0f}mm max, "
                f"{z.avg_deformation_mm:.0f}mm prom, "
                f"severidad={z.severity}, "
                f"riesgo edificios={z.building_risk}/100"
            )
        return "\n".join(lines)

"""
Agente de Emergencias con POO (filosofia NOOA).

Recibe datos de un evento (sismo, inundacion, deslizamiento) desde Sentinel/CDSE
o datos manuales, y orquesta los motores OR-Tools para:

1. VRP — evacuacion de heridos (ambulancias)
2. Min Cost Flow — asignacion de heridos a hospitales por capacidad
3. Bin Packing + VRP — distribucion de ayuda humanitaria

Filosofia NOOA:
- Clase = agente
- Metodos = capabilities (tools que el LLM puede llamar)
- Campos = estado (evento, recursos, resultados)
- Docstrings = prompts
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from llm_utils import llm_call

from vrp_solver.models import Location, LocationType, OptimizeRequest, Vehicle
from vrp_solver.solver import VRPSolver
from vrp_solver.validator import validate_request
from vrp_solver.utils import haversine

from engines.bin_packing import BinPackingItem, BinPackingBin, BinPackingRequest, BinPackingSolver
from engines.min_cost_flow import (
    AssignmentNode, AssignmentArc, AssignmentRequest, MinCostFlowSolver,
    build_school_assignment,
)
from sentinel_client import SentinelClient, bbox_to_wkt
from deformation_map import DeformationMap

from config import FIXTURES_DIR

load_dotenv()


@dataclass
class EmergencyEvent:
    """Estado: evento de emergencia detectado."""
    event_type: str  # "sismo", "inundacion", "deslizamiento"
    epicenter: tuple[float, float]  # [lat, lng]
    magnitude: float = 0.0
    affected_zones: list[dict] = field(default_factory=list)  # [{"name", "coords", "severity", "casualties", "blocked_roads"}]
    timestamp: str = ""
    source: str = "manual"  # "sentinel" o "manual"


@dataclass
class Hospital:
    """Recurso: hospital disponible."""
    id: str
    name: str
    coords: tuple[float, float]  # [lat, lng]
    capacity: int  # camas disponibles
    trauma_level: int = 1  # 1=basico, 2=avanzado, 3=trauma completo


@dataclass
class Ambulance:
    """Recurso: ambulancia disponible."""
    id: str
    name: str
    base_coords: tuple[float, float]  # [lat, lng]
    capacity: int = 2  # pacientes por viaje


@dataclass
class AidItem:
    """Recurso: item de ayuda humanitaria."""
    id: str
    name: str
    weight: float  # kg


@dataclass
class EmergencyResult:
    """Resultado completo de la respuesta de emergencia."""
    evacuation_routes: list[dict] = field(default_factory=list)
    hospital_assignment: list[dict] = field(default_factory=list)
    aid_distribution: list[dict] = field(default_factory=list)
    sentinel_products: list[dict] = field(default_factory=list)
    summary: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class EmergencyAgent:
    """
    Agente de respuesta a emergencias con POO (filosofia NOOA).

    Estado (campos que persisten):
        - event: evento de emergencia activo
        - hospitals: hospitales disponibles
        - ambulances: ambulancias disponibles
        - aid_items: items de ayuda disponibles
        - sentinel: cliente de CDSE para imagenes satelitales

    Capabilities (metodos = tools):
        - on_event: recibe alerta de emergencia
        - fetch_sentinel_imagery: busca imagenes post-desastre
        - optimize_evacuation: rutas de ambulancias (VRP)
        - optimize_hospital_assignment: heridos -> hospitales (MCF)
        - optimize_aid_distribution: empacar + rutar ayuda (Bin Packing + VRP)
        - explain: explica todo en espanol natural
    """

    def __init__(self, city: str = "bogota"):
        self.event: Optional[EmergencyEvent] = None
        self.hospitals: list[Hospital] = []
        self.ambulances: list[Ambulance] = []
        self.aid_items: list[AidItem] = []
        self.sentinel = SentinelClient()
        self.deformation_map: Optional[DeformationMap] = None
        self.city = city
        self._result = EmergencyResult()

        # Cargar fixture de matriz si existe
        fixture_map = {
            "bogota": FIXTURES_DIR / "matrix_bogota_6.json",
            "madrid": FIXTURES_DIR / "matrix_madrid_15.json",
        }
        self._matrix_path = str(fixture_map.get(city, fixture_map["bogota"]))

    # ═══════════════════════════════════════════════════════════════════
    # CAPABILITY: recibir evento
    # ═══════════════════════════════════════════════════════════════════

    def on_event(self, event: EmergencyEvent) -> str:
        """
        Recibe un evento de emergencia y prepara la respuesta.
        Si hay credenciales de Sentinel, busca imagenes post-desastre.
        Genera mapa de deformacion InSAR simulado basado en magnitud.
        """
        self.event = event
        self._result = EmergencyResult()

        # Generar mapa de deformacion InSAR
        self._generate_deformation_map()

        # Buscar imagenes Sentinel si hay credenciales
        if self.sentinel._check_credentials():
            self._fetch_sentinel_imagery()

        # LLM genera plan de respuesta
        plan = self._generate_response_plan()
        return plan

    def _generate_deformation_map(self):
        """Capability interna: genera mapa de deformacion InSAR basado en magnitud."""
        if not self.event:
            return

        zone_centers = []
        for z in self.event.affected_zones:
            coords = z["coords"]
            zone_centers.append({
                "name": z["name"],
                "lat": coords[0],
                "lng": coords[1],
            })

        self.deformation_map = DeformationMap()
        self.deformation_map.generate(
            epicenter=self.event.epicenter,
            magnitude=self.event.magnitude,
            zone_centers=zone_centers,
        )

    def _fetch_sentinel_imagery(self):
        """Capability interna: busca imagenes Sentinel del area afectada."""
        if not self.event:
            return

        # Bounding box alrededor del epicentro (~50km)
        lat, lng = self.event.epicenter
        aoi = bbox_to_wkt(lng - 0.5, lat - 0.5, lng + 0.5, lat + 0.5)

        # Buscar desde 7 dias antes del evento hasta hoy
        event_date_str = self.event.timestamp or datetime.now().strftime('%Y-%m-%d')
        try:
            event_date = datetime.strptime(event_date_str[:10], '%Y-%m-%d')
        except ValueError:
            event_date = datetime.now()
        search_start = (event_date - timedelta(days=7)).strftime('%Y-%m-%dT00:00:00.000Z')
        search_end = datetime.now(timezone.utc).strftime('%Y-%m-%dT23:59:59.000Z')

        # Buscar Sentinel-1 (radar, ve de noche y nubes) post-evento
        s1_result = self.sentinel.search_products(
            collection="SENTINEL-1",
            product_type="S1GRD",
            aoi_wkt=aoi,
            start_date=search_start,
            end_date=search_end,
            top=3,
        )

        for p in s1_result.products:
            self._result.sentinel_products.append({
                "id": p.id,
                "name": p.name,
                "collection": p.collection,
                "sensing_date": p.sensing_date,
                "type": "radar",
            })

        # Buscar Sentinel-2 (optico) si hay ventana de claros
        s2_result = self.sentinel.search_products(
            collection="SENTINEL-2",
            product_type="S2MSI1C",
            aoi_wkt=aoi,
            start_date=search_start,
            end_date=search_end,
            max_cloud_cover=50,
            top=3,
        )

        for p in s2_result.products:
            self._result.sentinel_products.append({
                "id": p.id,
                "name": p.name,
                "collection": p.collection,
                "sensing_date": p.sensing_date,
                "cloud_cover": p.cloud_cover,
                "type": "optical",
            })

    def _generate_response_plan(self) -> str:
        """LLM genera un plan de respuesta basado en el evento."""
        event_data = (
            f"Evento: {self.event.event_type}\n"
            f"Magnitud: {self.event.magnitude}\n"
            f"Epicentro: {self.event.epicenter}\n"
            f"Zonas afectadas: {len(self.event.affected_zones)}\n"
        )
        for z in self.event.affected_zones:
            event_data += f"  - {z['name']}: {z.get('casualties', '?')} heridos, severidad {z.get('severity', '?')}\n"

        event_data += f"\nHospitales disponibles: {len(self.hospitals)}\n"
        for h in self.hospitals:
            event_data += f"  - {h.name}: {h.capacity} camas, trauma nivel {h.trauma_level}\n"

        event_data += f"\nAmbulancias: {len(self.ambulances)}\n"
        event_data += f"Items de ayuda: {len(self.aid_items)}\n"

        if self._result.sentinel_products:
            event_data += f"\nImagenes Sentinel encontradas: {len(self._result.sentinel_products)}\n"
            for sp in self._result.sentinel_products:
                event_data += f"  - {sp['name']} ({sp['collection']}, {sp['sensing_date'][:10]})\n"

        if self.deformation_map and self.deformation_map.zones:
            event_data += f"\nMapa de deformacion InSAR (Sentinel-1):\n"
            for z in self.deformation_map.prioritize_zones():
                event_data += (
                    f"  - {z.name}: {z.max_deformation_mm:.0f}mm max, "
                    f"severidad={z.severity}, riesgo edificios={z.building_risk}/100\n"
                )

        response = llm_call(
            messages=[
                {"role": "system", "content": "Eres un coordinador de emergencias experto. Analiza el evento y genera un plan de respuesta en español claro y conciso. No uses JSON ni markdown."},
                {"role": "user", "content": f"Analiza esta emergencia y propone un plan de respuesta:\n\n{event_data}"},
            ],
            temperature=0.3,
            max_tokens=800,
        )
        return response.choices[0].message.content.strip()

    # ═══════════════════════════════════════════════════════════════════
    # CAPABILITY: evacuacion (VRP)
    # ═══════════════════════════════════════════════════════════════════

    def optimize_evacuation(self) -> str:
        """
        Capability: optimiza rutas de evacuacion con VRP.
        Las ambulancias salen de su base, recogen heridos en zonas afectadas,
        los llevan al hospital mas cercano, y vuelven.

        Los heridos se dividen en grupos del tamano de la capacidad de la
        ambulancia mas grande, para que el VRP pueda asignarlos.
        """
        if not self.event or not self.ambulances:
            return "Sin datos para optimizar evacuación."

        # Capacidad maxima de cualquier ambulancia
        max_amb_capacity = max(a.capacity for a in self.ambulances)

        # Construir locations: base + zonas afectadas (divididas en grupos)
        locations = []
        vehicles = []

        # Location 0: base de ambulancias (deposito)
        base = self.ambulances[0].base_coords
        locations.append(Location(
            id="base", name="Base Ambulancias",
            coords=list(base), type=LocationType.depot,
        ))

        # Zonas afectadas: dividir heridos en grupos que caben en una ambulancia
        loc_idx = 1
        for zone in self.event.affected_zones:
            casualties = zone.get("casualties", 1)
            group_size = min(max_amb_capacity, casualties)
            num_groups = (casualties + group_size - 1) // group_size  # ceil division

            for g in range(num_groups):
                remaining = casualties - g * group_size
                this_group = min(group_size, remaining)
                locations.append(Location(
                    id=f"zone_{loc_idx}", name=f"{zone['name']} (grupo {g+1})",
                    coords=list(zone["coords"]),
                    type=LocationType.pickup,
                    weight_demand=float(this_group),
                    service_time=300,  # 5 min para cargar heridos
                ))
                loc_idx += 1

        # Vehiculos: ambulancias
        for amb in self.ambulances:
            vehicles.append(Vehicle(
                id=amb.id, name=amb.name,
                start_location_id="base", end_location_id="base",
                weight_capacity=float(amb.capacity),
            ))

        request = OptimizeRequest(locations=locations, vehicles=vehicles)

        # Validar
        validation = validate_request(request)
        if not validation.is_valid:
            errors = "\n".join(f"- [{e.code.value}] {e.message}" for e in validation.errors)
            return f"Validación falló para evacuación:\n{errors}"

        # Resolver
        solver = VRPSolver.from_request(
            request,
            matrix_provider="synthetic",  # usamos sintetica para emergencias (no hay matriz cacheada de zonas arbitrarias)
        )
        result = solver.solve()

        if result.errors:
            return f"Error en evacuación: {[e.message for e in result.errors]}"

        # Guardar resultado estructurado
        for r in result.routes:
            stops = " -> ".join(s.name or s.location_id for s in r.stops)
            self._result.evacuation_routes.append({
                "vehicle": r.vehicle_name or r.vehicle_id,
                "stops": stops,
                "distance_km": r.total_distance / 1000,
                "duration_min": r.total_duration / 60 if r.total_duration else 0,
            })

        # Explicar
        routes_info = []
        for r in result.routes:
            stops = " -> ".join(s.name or s.location_id for s in r.stops)
            routes_info.append(
                f"Ambulancia {r.vehicle_name or r.vehicle_id}: {stops}\n"
                f"  Distancia: {r.total_distance / 1000:.2f} km | "
                f"Tiempo: {r.total_duration / 60:.1f} min | "
                f"Paradas: {r.total_stops}"
            )

        data = "\n".join(routes_info)
        return self._llm_explain("Explica este plan de evacuación de ambulancias:", data)

    # ═══════════════════════════════════════════════════════════════════
    # CAPABILITY: asignacion hospitalaria (Min Cost Flow)
    # ═══════════════════════════════════════════════════════════════════

    def optimize_hospital_assignment(self) -> str:
        """
        Capability: asigna heridos a hospitales minimizando distancia.
        Usa Min Cost Flow como en la asignacion escolar.
        """
        if not self.event or not self.hospitals:
            return "Sin datos para asignación hospitalaria."

        # Construir datos para MCF
        neighborhoods = []
        for i, zone in enumerate(self.event.affected_zones):
            neighborhoods.append({
                "id": f"zone_{i+1}",
                "name": zone["name"],
                "coords": zone["coords"],
                "children": zone.get("casualties", 1),  # "children" = heridos
            })

        schools = []
        for h in self.hospitals:
            schools.append({
                "id": h.id,
                "name": h.name,
                "coords": list(h.coords),
                "capacity": h.capacity,
            })

        try:
            request = build_school_assignment(schools, neighborhoods)
        except Exception as e:
            return f"Error construyendo asignación: {e}"

        # Validar
        total_casualties = sum(z.get("casualties", 1) for z in self.event.affected_zones)
        total_capacity = sum(h.capacity for h in self.hospitals)
        if total_casualties > total_capacity:
            self._result.warnings.append(
                f"Capacidad insuficiente: {total_casualties} heridos vs {total_capacity} camas"
            )

        solver = MinCostFlowSolver(request)
        result = solver.solve()

        if result.errors:
            return f"Error en asignación hospitalaria: {result.errors}"

        # Guardar resultado
        zone_names = {f"zone_{i+1}": z["name"] for i, z in enumerate(self.event.affected_zones)}
        hosp_names = {h.id: h.name for h in self.hospitals}

        for a in result.assignments:
            self._result.hospital_assignment.append({
                "from": zone_names.get(a["from_id"], a["from_id"]),
                "to": hosp_names.get(a["to_id"], a["to_id"]),
                "patients": a["units"],
                "distance_km": a["total_cost"] / 1000,
            })

        # Explicar
        schools_info = []
        hosp_groups: dict[str, list] = {}
        for a in result.assignments:
            hosp_groups.setdefault(a["to_id"], []).append(a)

        for hid, assigns in hosp_groups.items():
            total = sum(a["units"] for a in assigns)
            from_list = ", ".join(
                f"{zone_names.get(a['from_id'], a['from_id'])} ({a['units']} heridos)"
                for a in assigns
            )
            schools_info.append(
                f"{hosp_names.get(hid, hid)}: {total} heridos\n  Desde: {from_list}"
            )

        unassigned = ""
        if result.unassigned_demand > 0:
            unassigned = f"\n\n{result.unassigned_demand} heridos sin asignar (capacidad insuficiente)"

        data = "\n".join(schools_info) + unassigned
        return self._llm_explain("Explica esta asignación de heridos a hospitales:", data)

    # ═══════════════════════════════════════════════════════════════════
    # CAPABILITY: distribucion de ayuda (Bin Packing)
    # ═══════════════════════════════════════════════════════════════════

    def optimize_aid_distribution(self, bin_capacity: float = 50.0, num_bins: int = 5) -> str:
        """
        Capability: empaca items de ayuda en cajas optimamente.
        Bin Packing para minimizar cajas usadas.
        """
        if not self.aid_items:
            return "Sin items de ayuda para distribuir."

        items = [
            BinPackingItem(id=item.id, name=item.name, weight=item.weight)
            for item in self.aid_items
        ]
        bins = [
            BinPackingBin(id=f"caja_{i+1}", name=f"Caja {i+1}", capacity_weight=bin_capacity)
            for i in range(num_bins)
        ]

        # Validar
        total_weight = sum(i.weight for i in items)
        total_capacity = bin_capacity * num_bins
        if total_weight > total_capacity:
            self._result.warnings.append(
                f"Capacidad insuficiente: {total_weight}kg vs {total_capacity}kg"
            )

        request = BinPackingRequest(items=items, bins=bins)
        solver = BinPackingSolver(request)
        result = solver.solve()

        if result.errors:
            return f"Error en empaquetado de ayuda: {result.errors}"

        # Propagar warnings del solver (items no empacados, capacidad excedida)
        if result.warnings:
            self._result.warnings.extend(result.warnings)

        # Guardar resultado
        for pb in result.packed_bins:
            self._result.aid_distribution.append({
                "bin": pb.bin_name,
                "items": [i.name for i in pb.items],
                "total_weight": pb.total_weight,
                "utilization": pb.utilization_weight,
            })

        # Explicar
        bins_info = []
        for pb in result.packed_bins:
            items_str = ", ".join(f"{i.name} ({i.weight}kg)" for i in pb.items)
            bins_info.append(
                f"{pb.bin_name}: {len(pb.items)} items, {pb.total_weight:.1f}kg / "
                f"{pb.utilization_weight * 100:.0f}% usado\n  Items: {items_str}"
            )

        unassigned = ""
        if result.unassigned_items:
            unassigned = "\n\nNo empacados:\n" + "\n".join(
                f"  - {i.name} ({i.weight}kg)" for i in result.unassigned_items
            )

        data = (
            f"{chr(10).join(bins_info)}{unassigned}\n\n"
            f"Total: {result.total_bins_used}/{result.total_bins_available} cajas usadas, "
            f"{result.total_items_packed}/{result.total_items} items empacados"
        )
        return self._llm_explain("Explica este plan de distribución de ayuda humanitaria:", data)

    # ═══════════════════════════════════════════════════════════════════
    # CAPABILITY: explicacion final
    # ═══════════════════════════════════════════════════════════════════

    def explain_full_response(self) -> str:
        """Capability: explica toda la respuesta de emergencia en un resumen."""
        data_parts = []

        if self._result.sentinel_products:
            data_parts.append(f"Imagenes Sentinel: {len(self._result.sentinel_products)}")
            for sp in self._result.sentinel_products:
                data_parts.append(f"  - {sp['name']} ({sp['collection']})")

        if self._result.evacuation_routes:
            data_parts.append(f"\nRutas de evacuacion: {len(self._result.evacuation_routes)}")
            for r in self._result.evacuation_routes:
                data_parts.append(f"  - {r['vehicle']}: {r['distance_km']:.1f}km, {r['duration_min']:.0f}min")

        if self._result.hospital_assignment:
            data_parts.append(f"\nAsignacion hospitalaria: {len(self._result.hospital_assignment)} asignaciones")
            for a in self._result.hospital_assignment:
                data_parts.append(f"  - {a['from']} -> {a['to']}: {a['patients']} heridos")

        if self._result.aid_distribution:
            data_parts.append(f"\nDistribucion de ayuda: {len(self._result.aid_distribution)} cajas")
            for d in self._result.aid_distribution:
                data_parts.append(f"  - {d['bin']}: {d['total_weight']:.0f}kg ({d['utilization']*100:.0f}%)")

        if self._result.warnings:
            data_parts.append(f"\nAlertas: {len(self._result.warnings)}")
            for w in self._result.warnings:
                data_parts.append(f"  - {w}")

        if not data_parts:
            return "No hay resultados para explicar."

        data = "\n".join(data_parts)
        return self._llm_explain(
            "Genera un resumen ejecutivo de la respuesta de emergencia en español, "
            "destacando acciones tomadas, recursos utilizados y alertas:",
            data,
        )

    def _llm_explain(self, system_msg: str, data: str) -> str:
        """LLM explica el resultado en espanol natural."""
        response = llm_call(
            messages=[
                {"role": "system", "content": "Eres un coordinador de emergencias que explica resultados en español claro y conciso. No uses JSON ni markdown."},
                {"role": "user", "content": f"{system_msg}\n\n{data}"},
            ],
            temperature=0.3,
            max_tokens=800,
        )
        return response.choices[0].message.content.strip()

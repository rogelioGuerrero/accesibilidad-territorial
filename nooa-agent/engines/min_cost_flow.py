"""
Motor de Min Cost Flow con OR-Tools.
Asigna supply a demand minimizando costo total.

Caso de uso: asignacion escolar (ninos a escuelas minimizando distancia).
Filosofia NOOA: clase = agente, metodos = capabilities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ortools.graph.python import min_cost_flow


@dataclass
class AssignmentNode:
    """Nodo de supply o demand."""
    id: str
    name: str
    coords: tuple[float, float]  # [lat, lng]
    supply: int = 0  # positivo = produce, negativo = consume, 0 = transito


@dataclass
class AssignmentArc:
    """Arista entre dos nodos con costo."""
    from_id: str
    to_id: str
    cost: float  # costo por unidad (ej: distancia en metros)
    capacity: int = 10000  # capacidad maxima del arco


@dataclass
class AssignmentRequest:
    """Payload de entrada para Min Cost Flow."""
    nodes: list[AssignmentNode]
    arcs: list[AssignmentArc]


@dataclass
class AssignmentResult:
    """Resultado de la asignacion."""
    assignments: list[dict] = field(default_factory=list)  # [{from, to, units, cost}]
    total_cost: float = 0.0
    total_units_assigned: int = 0
    unassigned_supply: int = 0
    unassigned_demand: int = 0
    solver_time: float = 0.0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class MinCostFlowSolver:
    """
    Resuelve asignacion con Min Cost Flow de OR-Tools.
    Asigna supply a demand minimizando costo total.
    """

    def __init__(self, request: AssignmentRequest):
        self.nodes = request.nodes
        self.arcs = request.arcs

    def solve(self) -> AssignmentResult:
        """Ejecuta el solver y devuelve el resultado."""
        import time
        t0 = time.time()

        result = AssignmentResult()

        if not self.nodes:
            result.errors.append("No hay nodos")
            result.solver_time = time.time() - t0
            return result

        # Validar: supply total debe ser >= demand total
        total_supply = sum(n.supply for n in self.nodes if n.supply > 0)
        total_demand = abs(sum(n.supply for n in self.nodes if n.supply < 0))
        if total_supply < total_demand:
            result.warnings.append(
                f"Supply total ({total_supply}) < demand total ({total_demand}). "
                f"No se podra asignar todo."
            )

        # Mapear IDs a indices
        node_ids = [n.id for n in self.nodes]
        id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

        # Validar arcos
        valid_arcs = []
        for arc in self.arcs:
            if arc.from_id not in id_to_idx or arc.to_id not in id_to_idx:
                result.warnings.append(f"Arco {arc.from_id}->{arc.to_id} referencia nodo inexistente")
                continue
            valid_arcs.append(arc)

        # Balancear supply/demand: Min Cost Flow requiere sum(supply) == 0
        # Si supply > demand, agregar nodo sink con demand = exceso
        # Si demand > supply, agregar nodo source con supply = deficit
        imbalance = total_supply - total_demand
        dummy_node_idx = None
        dummy_arcs: list[int] = []
        if imbalance != 0:
            dummy_node_idx = len(self.nodes)
            id_to_idx["__dummy__"] = dummy_node_idx

        smcf = min_cost_flow.SimpleMinCostFlow()

        # Agregar arcos reales
        arc_indices = []
        for arc in valid_arcs:
            src = id_to_idx[arc.from_id]
            dst = id_to_idx[arc.to_id]
            cost = int(round(arc.cost))
            cap = arc.capacity
            idx = smcf.add_arc_with_capacity_and_unit_cost(src, dst, cap, cost)
            arc_indices.append(idx)

        # Agregar arcos dummy para balancear
        if dummy_node_idx is not None:
            if imbalance > 0:
                # Supply > demand: arcos desde cada supply node al dummy (costo 0)
                for i, node in enumerate(self.nodes):
                    if node.supply > 0:
                        idx = smcf.add_arc_with_capacity_and_unit_cost(i, dummy_node_idx, 10000, 0)
                        dummy_arcs.append(idx)
            else:
                # Demand > supply: arcos desde dummy a cada demand node (costo 0)
                for i, node in enumerate(self.nodes):
                    if node.supply < 0:
                        idx = smcf.add_arc_with_capacity_and_unit_cost(dummy_node_idx, i, 10000, 0)
                        dummy_arcs.append(idx)

        # Agregar supply de los nodos reales
        for i, node in enumerate(self.nodes):
            smcf.set_node_supply(i, node.supply)

        # Agregar supply del dummy
        if dummy_node_idx is not None:
            smcf.set_node_supply(dummy_node_idx, -imbalance)

        # Resolver
        status = smcf.solve()

        if status != smcf.OPTIMAL and status != smcf.FEASIBLE:
            result.errors.append(f"Min Cost Flow no encontro solucion (status={status})")
            result.solver_time = time.time() - t0
            return result

        # Extraer resultado
        for i, arc in enumerate(valid_arcs):
            flow = smcf.flow(arc_indices[i])
            if flow > 0:
                unit_cost = smcf.unit_cost(arc_indices[i])
                result.assignments.append({
                    "from_id": arc.from_id,
                    "to_id": arc.to_id,
                    "units": flow,
                    "cost_per_unit": unit_cost,
                    "total_cost": flow * unit_cost,
                })
                result.total_cost += flow * unit_cost
                result.total_units_assigned += flow

        # Calcular no asignado
        assigned_supply = sum(a["units"] for a in result.assignments)
        result.unassigned_supply = max(0, total_supply - assigned_supply)
        result.unassigned_demand = max(0, total_demand - assigned_supply)

        result.solver_time = time.time() - t0
        return result


def build_school_assignment(
    schools: list[dict],
    neighborhoods: list[dict],
    distance_matrix: list[list[float]] | None = None,
) -> AssignmentRequest:
    """
    Helper: construye un AssignmentRequest para asignacion escolar.

    Args:
        schools: [{"id": "esc1", "name": "Escuela A", "coords": [lat,lng], "capacity": 60}]
        neighborhoods: [{"id": "bar1", "name": "Barrio Norte", "coords": [lat,lng], "children": 50}]
        distance_matrix: matriz [n_barrios][n_escuelas] con distancias. Si None, usa haversine.

    Returns:
        AssignmentRequest listo para solver.
    """
    from vrp_solver.utils import haversine

    nodes: list[AssignmentNode] = []
    arcs: list[AssignmentArc] = []

    # Nodos de barrios (supply positivo = tienen ninos)
    for nb in neighborhoods:
        nodes.append(AssignmentNode(
            id=nb["id"],
            name=nb["name"],
            coords=tuple(nb["coords"]),
            supply=nb["children"],
        ))

    # Nodos de escuelas (demand negativo = reciben ninos)
    for sc in schools:
        nodes.append(AssignmentNode(
            id=sc["id"],
            name=sc["name"],
            coords=tuple(sc["coords"]),
            supply=-sc["capacity"],
        ))

    # Arcos: cada barrio -> cada escuela, costo = distancia
    for i, nb in enumerate(neighborhoods):
        for j, sc in enumerate(schools):
            if distance_matrix:
                dist = distance_matrix[i][j]
            else:
                dist = haversine(tuple(nb["coords"]), tuple(sc["coords"]))
            arcs.append(AssignmentArc(
                from_id=nb["id"],
                to_id=sc["id"],
                cost=dist,
                capacity=10000,
            ))

    return AssignmentRequest(nodes=nodes, arcs=arcs)

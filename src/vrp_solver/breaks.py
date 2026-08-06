"""
Preprocesamiento de breaks del VRP.
Los breaks se modelan como nodos dummy en el grafo:
  - Cada break = un nodo extra
  - service_time = break_duration
  - time_window = [earliest_start, latest_start]
  - Restringido a un solo vehículo
  - Distancia y travel time hacia/desde el dummy = 0
"""

from __future__ import annotations

from dataclasses import dataclass

from .matrix import DistanceMatrix
from .models import Vehicle


@dataclass
class BreakNode:
    """Información de un nodo dummy de break."""
    node_idx: int           # índice en el grafo extendido
    vehicle_idx: int        # vehículo al que pertenece
    duration: int           # duración del break (segundos)
    earliest: int           # tiempo más temprano para iniciar
    latest: int             # tiempo más tardío para iniciar
    label: str = "break"    # etiqueta para la respuesta


def build_break_nodes(vehicles: list[Vehicle], n_real: int) -> tuple[list[BreakNode], set[int], dict[int, int], int]:
    """
    Crea los nodos dummy de break a partir de los vehículos.

    Retorna:
        - break_nodes: lista de BreakNode
        - dummy_indices: set de índices dummy
        - break_duration_map: node_idx → duration
        - n_total: nodos reales + dummies
    """
    break_nodes: list[BreakNode] = []
    dummy_indices: set[int] = set()
    break_duration_map: dict[int, int] = {}
    dummy_idx = n_real

    for veh_idx, veh in enumerate(vehicles):
        if not veh.breaks:
            continue
        for brk in veh.breaks:
            if brk.time_windows:
                # Usar la unión de todas las ventanas del break
                earliest = min(tw.start for tw in brk.time_windows)
                latest = max(tw.end for tw in brk.time_windows)
            else:
                earliest = brk.earliest_start or 0
                latest = brk.latest_start or 86400

            bn = BreakNode(
                node_idx=dummy_idx,
                vehicle_idx=veh_idx,
                duration=brk.duration,
                earliest=earliest,
                latest=latest,
            )
            break_nodes.append(bn)
            dummy_indices.add(dummy_idx)
            break_duration_map[dummy_idx] = brk.duration
            dummy_idx += 1

    n_total = dummy_idx
    return break_nodes, dummy_indices, break_duration_map, n_total


def extend_matrix(base: DistanceMatrix, n_real: int, n_total: int) -> DistanceMatrix:
    """Extiende la matriz N×N a (N+B)×(N+B) con ceros en filas/columnas dummy."""
    extended = DistanceMatrix(n_total)
    for i in range(n_real):
        for j in range(n_real):
            extended.distances[i][j] = base.distances[i][j]
            extended.durations[i][j] = base.durations[i][j]
    return extended

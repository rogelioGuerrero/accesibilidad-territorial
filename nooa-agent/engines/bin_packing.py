"""
Motor de Bin Packing con OR-Tools (Knapsack).
Empaqueta items en contenedores minimizando el numero de contenedores usados.

Filosofia NOOA: la clase es el agente, los metodos son capabilities,
los campos son estado, los docstrings son prompts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ortools.algorithms.python import knapsack_solver as pywrapknapsack_solver


@dataclass
class BinPackingItem:
    """Item a empacar."""
    id: str
    name: str
    weight: float  # kg
    volume: float = 0.0  # m³ (opcional)


@dataclass
class BinPackingBin:
    """Contenedor disponible."""
    id: str
    name: str
    capacity_weight: float  # kg
    capacity_volume: float = 0.0  # m³ (opcional)


@dataclass
class BinPackingRequest:
    """Payload de entrada para el motor de bin packing."""
    items: list[BinPackingItem]
    bins: list[BinPackingBin]


@dataclass
class PackedBin:
    """Resultado: un contenedor con sus items."""
    bin_id: str
    bin_name: str
    items: list[BinPackingItem] = field(default_factory=list)
    total_weight: float = 0.0
    total_volume: float = 0.0
    utilization_weight: float = 0.0  # 0-1


@dataclass
class BinPackingResult:
    """Resultado completo del bin packing."""
    packed_bins: list[PackedBin] = field(default_factory=list)
    unassigned_items: list[BinPackingItem] = field(default_factory=list)
    total_bins_used: int = 0
    total_bins_available: int = 0
    total_items: int = 0
    total_items_packed: int = 0
    total_weight: float = 0.0
    solver_time: float = 0.0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class BinPackingSolver:
    """
    Resuelve bin packing usando OR-Tools Knapsack.
    Empaqueta items en contenedores minimizando contenedores usados.
    """

    def __init__(self, request: BinPackingRequest):
        self.items = request.items
        self.bins = request.bins

    def solve(self) -> BinPackingResult:
        """Ejecuta el solver y devuelve el resultado estructurado."""
        import time
        t0 = time.time()

        result = BinPackingResult(
            total_items=len(self.items),
            total_bins_available=len(self.bins),
        )

        if not self.items:
            result.errors.append("No hay items para empacar")
            result.solver_time = time.time() - t0
            return result

        if not self.bins:
            result.errors.append("No hay contenedores disponibles")
            result.solver_time = time.time() - t0
            return result

        # Validar: ningun item excede la capacidad del contenedor mas grande
        max_bin_weight = max(b.capacity_weight for b in self.bins)
        for item in self.items:
            if item.weight > max_bin_weight:
                result.unassigned_items.append(item)
                result.warnings.append(
                    f"Item '{item.id}' pesa {item.weight}kg, excede el contenedor mas grande ({max_bin_weight}kg)"
                )

        packable_items = [i for i in self.items if i not in result.unassigned_items]

        # OR-Tools Knapsack: resolver multiple knapsack (0-1) para asignar
        # items a contenedores minimizando el numero de contenedores usados.
        #
        # Estrategia: resolver un knapsack por contenedor en orden de capacidad
        # descendente. El solver encuentra el subconjunto de items que maximiza
        # el peso empacado sin exceder la capacidad. Los items restantes se
        # intentan empacar en el siguiente contenedor.
        solver = pywrapknapsack_solver.KnapsackSolver(
            pywrapknapsack_solver.SolverType.KNAPSACK_MULTIDIMENSION_BRANCH_AND_BOUND_SOLVER,
            "BinPacking",
        )

        # Ordenar contenedores por capacidad descendente (llenar los grandes primero)
        sorted_bins = sorted(self.bins, key=lambda b: b.capacity_weight, reverse=True)

        # Mapear items a índices para OR-Tools
        remaining_items = list(packable_items)
        bin_assignments: dict[str, list[BinPackingItem]] = {b.id: [] for b in self.bins}
        bin_loads = {b.id: 0.0 for b in self.bins}
        bin_volumes = {b.id: 0.0 for b in self.bins}
        used_bin_ids: list[str] = []

        for bin_obj in sorted_bins:
            if not remaining_items:
                break

            # Preparar valores y pesos para este knapsack
            values = [int(i.weight * 100) for i in remaining_items]  # escalar a enteros
            weights = [[int(i.weight * 100) for i in remaining_items]]
            capacities = [int(bin_obj.capacity_weight * 100)]

            solver.init(values, weights, capacities)
            solver.solve()

            # Recoger items asignados a este contenedor
            assigned_indices = []
            for idx in range(len(remaining_items)):
                if solver.best_solution_contains(idx):
                    item = remaining_items[idx]
                    # Verificar volumen si aplica
                    if (item.volume <= (bin_obj.capacity_volume - bin_volumes[bin_obj.id]) or
                        bin_obj.capacity_volume == 0.0):
                        bin_assignments[bin_obj.id].append(item)
                        bin_loads[bin_obj.id] += item.weight
                        bin_volumes[bin_obj.id] += item.volume
                        assigned_indices.append(idx)

            if bin_assignments[bin_obj.id]:
                used_bin_ids.append(bin_obj.id)

            # Remover items asignados de remaining_items (de mayor a menor índice)
            for idx in sorted(assigned_indices, reverse=True):
                remaining_items.pop(idx)

        # Items que no cupieron en ningún contenedor
        for item in remaining_items:
            result.unassigned_items.append(item)
            result.warnings.append(
                f"Item '{item.id}' no cabe en ningun contenedor disponible"
            )

        # Construir resultado
        for b in self.bins:
            if bin_assignments[b.id]:
                packed = PackedBin(
                    bin_id=b.id,
                    bin_name=b.name,
                    items=bin_assignments[b.id],
                    total_weight=bin_loads[b.id],
                    total_volume=bin_volumes[b.id],
                    utilization_weight=bin_loads[b.id] / b.capacity_weight if b.capacity_weight > 0 else 0,
                )
                result.packed_bins.append(packed)
                result.total_weight += packed.total_weight
                result.total_items_packed += len(packed.items)

        result.total_bins_used = len(result.packed_bins)
        result.solver_time = time.time() - t0
        return result

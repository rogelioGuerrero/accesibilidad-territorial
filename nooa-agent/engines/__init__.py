"""Motores de optimización con OR-Tools."""

from engines.bin_packing import (
    BinPackingItem,
    BinPackingBin,
    BinPackingRequest,
    BinPackingSolver,
    BinPackingResult,
    PackedBin,
)
from engines.min_cost_flow import (
    AssignmentNode,
    AssignmentArc,
    AssignmentRequest,
    AssignmentResult,
    MinCostFlowSolver,
    build_school_assignment,
)

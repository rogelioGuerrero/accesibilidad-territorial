"""
DEPRECATED: Este archivo ya no se usa.

Toda la lógica de agentes autónomos se movió a:
- base_agent.py → AutonomousAgent (clase base abstracta)
- emergency_autonomous.py → EmergencyAutonomousAgent
- insurance_autonomous.py → InsuranceAutonomousAgent
- mining_autonomous.py → MiningAutonomousAgent

Para crear un nuevo agente, heredar de base_agent.AutonomousAgent.
"""

import warnings

warnings.warn(
    "autonomous_agent.py está deprecated. Usa base_agent.AutonomousAgent "
    "y sus subclases (emergency_autonomous, insurance_autonomous, mining_autonomous).",
    DeprecationWarning,
    stacklevel=2,
)

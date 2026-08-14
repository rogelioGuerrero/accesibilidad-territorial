"""NOOA Agent — Sistema multi-agente con Groq + OR-Tools + human-in-the-loop.

6 capacidades del harness NVIDIA NOOA:
1. Typed input/output — type hints + dataclasses
2. Pass by reference — ToolResult con bounded previews
3. Code as action — @strategy decorator para métodos completados por LLM
4. Programmable loop engineering — pipelines como Python ordinario
5. Explicit object state — campos tipados en el objeto agente
6. Model-callable harness APIs — tools para inspeccionar contexto y memoria
"""

from base_agent import AutonomousAgent
from agent import VRPAgent
from chat_agent import ChatVRPAgent
from multi_agent import MultiEngineAgent
from emergency_agent import EmergencyAgent, EmergencyEvent, Hospital, Ambulance, AidItem
from emergency_autonomous import EmergencyAutonomousAgent
from mining_autonomous import MiningAutonomousAgent
from logistics_agent import LogisticsAgent

# NOOA Harness
from harness import ToolResult, ResultRegistry
from memory_store import MemoryStore, Entity, Relation
from harness_api import HarnessAPI, HARNESS_TOOLS
from code_action import strategy, PredictStrategy

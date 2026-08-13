"""
Model-callable harness APIs.

NOOA capability #6: context blocks and event history are APIs the model
can inspect and manage. These are tools the LLM can call to:
- Inspect its own context window usage
- Query conversation history
- Retrieve tool results by reference name
- Manage long-term memory (create, search, relate entities)

Filosofía NOOA: el modelo puede inspeccionar y gestionar su propio contexto.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


# ─── Tools schema for harness APIs ─────────────────────────────────

HARNESS_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "inspect_context",
            "description": "View current context window: message count, estimated tokens, recent tool results.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_history",
            "description": "Search recent conversation history for specific information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to search for in conversation history"},
                    "last_n": {"type": "integer", "description": "Number of recent messages to search (default 10)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_tool_result",
            "description": "Retrieve the full value of a previous tool result by name (pass-by-reference).",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name of the tool result to retrieve"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tool_results",
            "description": "List all available tool results by name with their previews.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember",
            "description": "Store a fact or observation in long-term memory for future sessions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_name": {"type": "string", "description": "Unique name for this memory entity"},
                    "entity_type": {"type": "string", "description": "Type: event, insight, fact, preference, contact"},
                    "observations": {
                        "type": "array", "items": {"type": "string"},
                        "description": "List of observations/facts to store",
                    },
                    "importance": {"type": "number", "description": "Importance 0-1 (default 0.5)"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags for categorization"},
                },
                "required": ["entity_name", "entity_type", "observations"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall",
            "description": "Search long-term memory for relevant knowledge.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query for memory"},
                    "limit": {"type": "integer", "description": "Max results (default 5)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "relate",
            "description": "Create a typed relation between two memory entities.",
            "parameters": {
                "type": "object",
                "properties": {
                    "from_entity": {"type": "string", "description": "Source entity name"},
                    "to_entity": {"type": "string", "description": "Target entity name"},
                    "relation_type": {
                        "type": "string",
                        "enum": ["supports", "contradicts", "derived-from", "related-to"],
                        "description": "Type of relation",
                    },
                },
                "required": ["from_entity", "to_entity", "relation_type"],
            },
        },
    },
]


class HarnessAPI:
    """
    Model-callable introspection and memory management.

    Attached to an agent instance, provides tools the LLM can call
    to inspect context, query history, retrieve results by reference,
    and manage long-term memory.

    Usage:
        agent._harness = HarnessAPI(agent, memory_store, result_registry)
        # LLM can now call: inspect_context, query_history, get_tool_result, etc.
    """

    def __init__(self, agent: Any, memory_store: Any = None, result_registry: Any = None):
        self._agent = agent
        self._memory = memory_store
        self._results = result_registry

    def execute(self, name: str, args: dict) -> Any:
        """Route harness tool calls to the appropriate method."""
        if name == "inspect_context":
            return self._inspect_context()
        elif name == "query_history":
            return self._query_history(args.get("query", ""), args.get("last_n", 10))
        elif name == "get_tool_result":
            return self._get_tool_result(args.get("name", ""))
        elif name == "list_tool_results":
            return self._list_tool_results()
        elif name == "remember":
            return self._remember(
                args.get("entity_name", ""),
                args.get("entity_type", "fact"),
                args.get("observations", []),
                args.get("importance", 0.5),
                args.get("tags", []),
            )
        elif name == "recall":
            return self._recall(args.get("query", ""), args.get("limit", 5))
        elif name == "relate":
            return self._relate(
                args.get("from_entity", ""),
                args.get("to_entity", ""),
                args.get("relation_type", "related-to"),
            )
        return {"error": f"Unknown harness tool: {name}"}

    # ─── Context inspection ──────────────────────────────────────

    def _inspect_context(self) -> dict:
        """View current context window state."""
        messages = getattr(self._agent, "_messages", [])
        total_chars = sum(len(str(m.get("content", ""))) for m in messages)
        estimated_tokens = total_chars // 4  # rough estimate

        tool_results = {}
        if self._results:
            tool_results = {name: self._results.get_preview(name)[:100] for name in self._results.list_names()}

        return {
            "message_count": len(messages),
            "estimated_tokens": estimated_tokens,
            "estimated_tokens_remaining": max(0, 128000 - estimated_tokens),
            "tool_results_available": list(tool_results.keys()) if tool_results else [],
            "tool_result_previews": tool_results,
        }

    def _query_history(self, query: str, last_n: int = 10) -> dict:
        """Search recent conversation history."""
        messages = getattr(self._agent, "_messages", [])
        recent = messages[-last_n:] if len(messages) > last_n else messages

        query_lower = query.lower()
        matches = []
        for i, msg in enumerate(recent):
            content = str(msg.get("content", ""))
            if query_lower in content.lower():
                matches.append({
                    "index": len(messages) - len(recent) + i,
                    "role": msg.get("role", "unknown"),
                    "snippet": content[:200] + ("..." if len(content) > 200 else ""),
                })

        return {
            "query": query,
            "searched_messages": len(recent),
            "matches": len(matches),
            "results": matches[:5],
        }

    # ─── Pass-by-reference tool results ──────────────────────────

    def _get_tool_result(self, name: str) -> dict:
        """Retrieve full tool result by reference name."""
        if not self._results:
            return {"error": "No result registry available"}

        result = self._results.get(name)
        if not result:
            return {"error": f"No result named '{name}'. Available: {self._results.list_names()}"}

        if result.is_error:
            return {"name": name, "error": result.error}

        # Return the full value (pass-by-reference retrieval)
        return {
            "name": name,
            "type": result._type_hint,
            "preview": result.preview,
            "value": result.value,
        }

    def _list_tool_results(self) -> dict:
        """List all available tool results."""
        if not self._results:
            return {"results": [], "count": 0}

        names = self._results.list_names()
        previews = {name: self._results.get_preview(name)[:150] for name in names}
        return {"results": previews, "count": len(names)}

    # ─── Long-term memory ────────────────────────────────────────

    def _remember(
        self,
        entity_name: str,
        entity_type: str,
        observations: list[str],
        importance: float = 0.5,
        tags: list[str] | None = None,
    ) -> dict:
        """Store facts in long-term memory."""
        if not self._memory:
            return {"error": "No memory store available"}

        try:
            entity = self._memory.create_entity(
                name=entity_name,
                entity_type=entity_type,
                observations=observations,
                importance=importance,
                tags=tags or [],
            )
            return {
                "status": "stored",
                "entity": entity.name,
                "type": entity.entity_type,
                "observations_count": len(entity.observations),
                "importance": entity.importance,
            }
        except Exception as e:
            return {"error": str(e)}

    def _recall(self, query: str, limit: int = 5) -> dict:
        """Search long-term memory."""
        if not self._memory:
            return {"error": "No memory store available"}

        try:
            entities = self._memory.search(query, limit=limit)
            results = []
            for e in entities:
                relations = self._memory.get_relations(e.name)
                results.append({
                    "name": e.name,
                    "type": e.entity_type,
                    "observations": e.observations,
                    "importance": e.importance,
                    "tags": e.tags,
                    "relations": [
                        {"to": r.to_entity if r.from_entity == e.name else r.from_entity,
                         "type": r.relation_type}
                        for r in relations[:5]
                    ],
                })
            return {"query": query, "results": results, "count": len(results)}
        except Exception as e:
            return {"error": str(e)}

    def _relate(self, from_entity: str, to_entity: str, relation_type: str) -> dict:
        """Create a relation between memory entities."""
        if not self._memory:
            return {"error": "No memory store available"}

        try:
            rel = self._memory.create_relation(from_entity, to_entity, relation_type)
            if rel:
                return {"status": "created", "from": rel.from_entity, "to": rel.to_entity, "type": rel.relation_type}
            return {"error": f"Could not create relation (entities not found)"}
        except Exception as e:
            return {"error": str(e)}

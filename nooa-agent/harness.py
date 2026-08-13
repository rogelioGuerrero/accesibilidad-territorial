"""
Pass-by-reference system for tool results.

NOOA capability #2: instead of serializing full tool results into the
context window, results stay as live Python objects. The LLM sees only
a bounded preview (type, summary, first N chars). The full value is
accessible by reference name in subsequent tool calls.

This cuts token usage roughly in half — the key efficiency gain in NOOA.

Filosofía NOOA: tool results son variables Python, no texto serializado.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

PREVIEW_MAX_CHARS = 300
PREVIEW_MAX_ITEMS = 5


@dataclass
class ToolResult:
    """
    Wrapper for tool execution results with bounded preview.

    The full value stays in memory (pass-by-reference).
    Only the preview is sent to the LLM context window.

    Attributes:
        name: tool name (e.g. "optimize_vrp")
        value: the full Python object (list, dict, dataclass, etc.)
        preview: bounded text summary for the LLM
        error: error message if tool failed
        tool_call_id: matching tool call ID for OpenAI-style responses
    """

    name: str
    value: Any = None
    preview: str = ""
    error: str | None = None
    tool_call_id: str = ""
    _type_hint: str = ""

    @property
    def is_error(self) -> bool:
        return self.error is not None

    @classmethod
    def from_value(cls, name: str, value: Any, tool_call_id: str = "") -> ToolResult:
        """Create a ToolResult with auto-generated preview from the value."""
        preview = cls._build_preview(value)
        type_hint = type(value).__name__
        return cls(name=name, value=value, preview=preview, tool_call_id=tool_call_id, _type_hint=type_hint)

    @classmethod
    def from_error(cls, name: str, error: str, tool_call_id: str = "") -> ToolResult:
        return cls(name=name, error=error, preview=f"ERROR: {error}", tool_call_id=tool_call_id)

    @staticmethod
    def _build_preview(value: Any) -> str:
        """Generate a bounded text preview of any Python value."""
        if value is None:
            return "[null]"

        if isinstance(value, str):
            if len(value) <= PREVIEW_MAX_CHARS:
                return value
            return value[:PREVIEW_MAX_CHARS] + f"... ({len(value)} chars total)"

        if isinstance(value, (int, float, bool)):
            return str(value)

        if isinstance(value, dict):
            return ToolResult._preview_dict(value)

        if isinstance(value, (list, tuple)):
            return ToolResult._preview_list(value)

        # For dataclasses and objects, show type + public attributes
        if hasattr(value, "__dataclass_fields__"):
            fields = {}
            for f_name in value.__dataclass_fields__:
                f_val = getattr(value, f_name)
                fields[f_name] = ToolResult._summarize_value(f_val)
            return f"{type(value).__name__}({json.dumps(fields, ensure_ascii=False, default=str)})"

        # Fallback: type + str preview
        s = str(value)
        if len(s) <= PREVIEW_MAX_CHARS:
            return f"{type(value).__name__}: {s}"
        return f"{type(value).__name__}: {s[:PREVIEW_MAX_CHARS]}..."

    @staticmethod
    def _preview_dict(d: dict) -> str:
        if not d:
            return "{}"
        keys = list(d.keys())
        preview_keys = keys[:PREVIEW_MAX_ITEMS]
        parts = []
        for k in preview_keys:
            parts.append(f"  {k}: {ToolResult._summarize_value(d[k])}")
        suffix = f"\n  ... ({len(keys)} keys total)" if len(keys) > PREVIEW_MAX_ITEMS else ""
        return "{\n" + "\n".join(parts) + suffix + "\n}"

    @staticmethod
    def _preview_list(lst: list | tuple) -> str:
        if not lst:
            return "[]"
        items = []
        for i, item in enumerate(lst):
            if i >= PREVIEW_MAX_ITEMS:
                items.append(f"  ... ({len(lst)} items total)")
                break
            items.append(f"  [{i}] {ToolResult._summarize_value(item)}")
        return "[\n" + "\n".join(items) + "\n]"

    @staticmethod
    def _summarize_value(val: Any) -> str:
        """Single-line summary of any value."""
        if isinstance(val, str):
            return f'"{val[:80]}{"..." if len(val) > 80 else ""}"'
        if isinstance(val, (int, float, bool)):
            return str(val)
        if isinstance(val, dict):
            return f"dict({len(val)} keys)"
        if isinstance(val, (list, tuple)):
            return f"list({len(val)} items)"
        return f"{type(val).__name__}"


class ResultRegistry:
    """
    Registry of tool results accessible by name (pass-by-reference).

    The LLM references results by name instead of seeing full dumps.
    Methods like get_tool_result(name) retrieve the live Python object.

    Usage:
        registry = ResultRegistry()
        registry.store(ToolResult.from_value("vrp_result", routes_dict))
        # LLM sees only the preview
        preview = registry.get_preview("vrp_result")
        # Code can access the full value
        full = registry.get_value("vrp_result")
    """

    def __init__(self):
        self._results: dict[str, ToolResult] = {}

    def store(self, result: ToolResult) -> None:
        self._results[result.name] = result

    def get(self, name: str) -> ToolResult | None:
        return self._results.get(name)

    def get_value(self, name: str) -> Any:
        """Retrieve the full live Python object by reference name."""
        r = self._results.get(name)
        return r.value if r else None

    def get_preview(self, name: str) -> str:
        """Get the bounded preview for LLM context."""
        r = self._results.get(name)
        return r.preview if r else f"[no result: {name}]"

    def list_names(self) -> list[str]:
        return list(self._results.keys())

    def build_context_block(self) -> str:
        """
        Build a compact context block with all result previews.
        This is what gets injected into the LLM context — not the full values.
        """
        if not self._results:
            return ""
        lines = ["## Tool Results (previews — full values accessible by name)"]
        for name, result in self._results.items():
            status = "❌" if result.is_error else "✅"
            lines.append(f"{status} **{name}** ({result._type_hint}): {result.preview[:200]}")
        return "\n".join(lines)

    def clear(self):
        self._results.clear()

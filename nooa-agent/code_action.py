"""
Code-as-action: the model writes Python instead of selecting from a tool menu.

NOOA capability #3: methods with body `...` (ellipsis) are completed at
runtime by an LLM-driven loop. The model generates Python code that calls
agent methods directly, with control flow and inline composition.

This replaces JSON function calling for complex reasoning tasks.

Filosofía NOOA: el modelo actúa escribiendo código, no seleccionando tools.
"""

from __future__ import annotations

import logging
import textwrap
from typing import Any, Callable

from llm_utils import llm_call

logger = logging.getLogger(__name__)


class PredictStrategy:
    """Default strategy: LLM generates Python code to complete the method."""

    def __init__(self, temperature: float = 0.1, max_tokens: int = 2000):
        self.temperature = temperature
        self.max_tokens = max_tokens


def strategy(strat: PredictStrategy | None = None):
    """
    Decorator that marks a method for LLM-driven completion.

    Methods decorated with @strategy must have body `...` (ellipsis).
    At runtime, the LLM generates Python code to fulfill the method's
    contract based on its docstring, type annotations, and the agent's state.

    Usage:
        class MyAgent(AutonomousAgent):
            @strategy(PredictStrategy(temperature=0.2))
            def analyze_event(self, event: EmergencyEvent) -> str:
                '''Analyze the emergency event and return a response plan.'''
                ...

    The LLM receives:
        - The method's docstring (prompt)
        - The method's type annotations (contract)
        - The agent's state (accessible via self)
        - Available tools and their schemas
        - Recent tool results (from ResultRegistry)

    The LLM generates Python code that:
        - Can call self._execute_tool(name, args)
        - Can access self.<any_field>
        - Must return a value matching the return type annotation
    """

    def decorator(method: Callable) -> Callable:
        strat_obj = strat or PredictStrategy()

        def wrapper(self, *args, **kwargs):
            # Build the prompt for the LLM
            prompt = _build_code_action_prompt(self, method, args, kwargs)
            response = llm_call(
                messages=[{"role": "user", "content": prompt}],
                temperature=strat_obj.temperature,
                max_tokens=strat_obj.max_tokens,
            )
            code = _extract_code(response.choices[0].message.content)

            # Execute the generated code in a sandboxed namespace
            result = _execute_code_action(self, code, method, args, kwargs)
            return result

        wrapper.__name__ = method.__name__
        wrapper.__doc__ = method.__doc__
        wrapper.__is_strategy__ = True
        return wrapper

    return decorator


def _build_code_action_prompt(agent: Any, method: Callable, args: tuple, kwargs: dict) -> str:
    """Build the prompt for LLM-driven method completion."""
    doc = (method.__doc__ or "No description.").strip()
    ret_annotation = method.__annotations__.get("return", Any)
    if hasattr(ret_annotation, "__name__"):
        return_type = ret_annotation.__name__
    else:
        return_type = str(ret_annotation)

    # Gather agent state (public fields only, bounded previews)
    state_lines = []
    for attr_name in dir(agent):
        if attr_name.startswith("_"):
            continue
        try:
            val = getattr(agent, attr_name)
            if callable(val):
                continue
            preview = _summarize_for_prompt(val)
            state_lines.append(f"  self.{attr_name}: {preview}")
        except Exception:
            pass

    state_block = "\n".join(state_lines[:20]) if state_lines else "  (no public state)"

    # Gather available tools
    tools_block = ""
    if hasattr(agent, "tools_schema") and agent.tools_schema:
        tool_names = [t["function"]["name"] for t in agent.tools_schema]
        tools_block = "Available tools (call via self._execute_tool(name, args)):\n"
        for t in agent.tools_schema:
            tools_block += f"  - {t['function']['name']}: {t['function']['description'][:120]}\n"
    else:
        tools_block = "No tools available."

    # Gather recent tool results
    results_block = ""
    if hasattr(agent, "_result_registry"):
        results_block = agent._result_registry.build_context_block()

    # Gather result structures (compact, so the code accesses real keys)
    structures_block = ""
    if hasattr(agent, "_result_registry"):
        names = agent._result_registry.list_names()
        if names:
            struct_lines = ["## Result structures (full values via self._result_registry.get_value(name)):"]
            for name in names:
                value = agent._result_registry.get_value(name)
                struct_lines.append(f"- {name}: {_describe_structure(value)}")
            structures_block = "\n".join(struct_lines)

    return f"""You are completing a Python method on an agent object.

## Method to complete:
```python
def {method.__name__}(self{_format_params(method, args, kwargs)}) -> {return_type}:
    \"\"\"{doc}\"\"\"
    ...
```

## Agent state (self):
{state_block}

## {tools_block}

{results_block}

{structures_block}

## Instructions:
Write the body of the method as Python code. You can:
- Call self._execute_tool("tool_name", {{"arg": value}}) to invoke tools
- Access any field on self (e.g., self.event, self._tool_results)
- Use standard Python (if/else, for, list comprehensions, etc.)
- Call self._result_registry.get_value("name") to get full tool results

Return ONLY the Python code for the method body (no markdown, no explanation).
The code must end with a return statement matching the return type `{return_type}`.
"""


def _format_params(method: Callable, args: tuple, kwargs: dict) -> str:
    """Format method parameters with actual values for the prompt."""
    import inspect
    try:
        sig = inspect.signature(method)
        bound = sig.bind(None, *args, **kwargs)
        bound.apply_defaults()
        params = []
        for name, val in list(bound.arguments.items())[1:]:  # skip self
            params.append(f"{name}: {_summarize_for_prompt(val)}")
        return ", ".join(params)
    except Exception:
        return ", ".join(repr(a) for a in args)


def _extract_code(text: str) -> str:
    """Extract Python code from LLM response, stripping markdown fences."""
    text = text.strip()
    if text.startswith("```python"):
        text = text[9:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return textwrap.dedent(text).strip()


def _strip_method_def(code: str, method_name: str) -> str:
    """
    If the LLM returned a full method definition instead of just the body,
    extract the body (everything after the signature's closing ':').
    """
    stripped = code.lstrip()
    if not stripped.startswith(f"def {method_name}("):
        return code
    lines = stripped.split("\n")
    for i, line in enumerate(lines):
        if line.rstrip().endswith(":"):
            body = "\n".join(lines[i + 1:])
            return textwrap.dedent(body).strip()
    return code


def _describe_structure(val: Any, depth: int = 0, max_depth: int = 3) -> str:
    """Compact structural description of a value for prompt context."""
    if depth >= max_depth:
        return type(val).__name__
    if isinstance(val, dict):
        if not val:
            return "{}"
        inner = ", ".join(
            f"{k}: {_describe_structure(v, depth + 1, max_depth)}"
            for k, v in list(val.items())[:6]
        )
        return "{" + inner + "}"
    if isinstance(val, (list, tuple)):
        if not val:
            return "[]"
        return f"[{_describe_structure(val[0], depth + 1, max_depth)}]"
    if isinstance(val, str):
        return "str"
    if isinstance(val, bool):
        return "bool"
    if isinstance(val, (int, float)):
        return "number"
    return type(val).__name__


def _execute_code_action(agent: Any, code: str, method: Callable, args: tuple, kwargs: dict) -> Any:
    """
    Execute LLM-generated code in a sandboxed namespace.

    The code is wrapped in a function so `return` statements work naturally
    (the LLM is instructed to end the body with a return statement). The
    wrapper receives the method's bound arguments as parameters and `self`
    is available as a global.

    The code runs with access to:
        - self: the agent instance
        - All builtins (print, len, range, etc.)
        - Standard library modules already imported
    """
    import inspect

    # Bind method arguments as function parameters
    sig = inspect.signature(method)
    bound = sig.bind(agent, *args, **kwargs)
    bound.apply_defaults()
    params = list(bound.arguments.items())[1:]  # skip self

    # Build a safe namespace
    namespace: dict[str, Any] = {
        "self": agent,
        "__builtins__": __builtins__,
    }

    # If the LLM returned a full method definition, extract just the body
    code = _strip_method_def(code, method.__name__)

    # Wrap the code in a function so `return` works at the top level of the body
    param_defs = ", ".join(name for name, _ in params)
    wrapped = f"def __code_action__({param_defs}):\n{textwrap.indent(code, '    ')}"

    try:
        compiled = compile(wrapped, f"<code_action:{method.__name__}>", "exec")
        exec(compiled, namespace)
        call_args = {name: val for name, val in params}
        return namespace["__code_action__"](**call_args)
    except Exception as e:
        logger.error("Code action for %s failed: %s\nCode:\n%s", method.__name__, e, code)
        raise RuntimeError(f"Code action failed for {method.__name__}: {e}") from e


def _summarize_for_prompt(val: Any) -> str:
    """Single-line summary for prompt context."""
    if val is None:
        return "None"
    if isinstance(val, str):
        return f'"{val[:100]}{"..." if len(val) > 100 else ""}"'
    if isinstance(val, (int, float, bool)):
        return str(val)
    if isinstance(val, dict):
        return f"dict({len(val)} keys: {list(val.keys())[:5]})"
    if isinstance(val, (list, tuple)):
        return f"list({len(val)} items)"
    return f"{type(val).__name__}"

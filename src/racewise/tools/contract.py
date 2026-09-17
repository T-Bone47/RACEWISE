"""Tool contract: every deterministic tool exposes name, description,
input/output JSON schemas, a version, and execute().

The agent never receives raw database access — only this allow-listed
contract surface.
"""
from __future__ import annotations

import hashlib
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel


class ToolError(Exception):
    """Raised when a tool cannot produce a valid result."""

    def __init__(self, message: str, *, missing: bool = False) -> None:
        super().__init__(message)
        self.missing = missing


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    version: str
    limitations: list[str] = field(default_factory=list)


class Tool(ABC):
    """Base class for deterministic tools."""

    spec: ToolSpec

    @abstractmethod
    def execute(self, **kwargs: Any) -> dict[str, Any]:
        ...

    def validate_input(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        schema = self.spec.input_schema
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        validated: dict[str, Any] = {}
        for key in required:
            if key not in kwargs:
                raise ToolError(f"Missing required parameter '{key}' for tool '{self.spec.name}'")
        for key, value in kwargs.items():
            if properties and key not in properties:
                raise ToolError(f"Unknown parameter '{key}' for tool '{self.spec.name}'")
            validated[key] = value
        return validated

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.spec.name,
            "description": self.spec.description,
            "parameters": {
                "type": "object",
                "properties": self.spec.input_schema.get("properties", {}),
                "required": self.spec.input_schema.get("required", []),
            },
            "output_schema": self.spec.output_schema,
            "limitations": self.spec.limitations,
        }


def canonical_hash(payload: Any) -> str:
    """Stable hash of a JSON-serializable payload for provenance."""
    serialized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class ToolRegistry:
    """Allow-listed tool registry. The agent can only call registered tools."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.spec.name in self._tools:
            raise ValueError(f"Duplicate tool name: {tool.spec.name}")
        self._tools[tool.spec.name] = tool

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise ToolError(f"Tool '{name}' is not in the allow-list")
        return self._tools[name]

    def names(self) -> list[str]:
        return sorted(self._tools.keys())

    def descriptions(self) -> list[dict[str, Any]]:
        return [tool.describe() for tool in self._tools.values()]

    def execute(self, name: str, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool with timing + provenance metadata attached."""
        tool = self.get(name)
        validated = tool.validate_input(kwargs)
        start = time.perf_counter()
        output = tool.execute(**validated)
        duration_ms = int((time.perf_counter() - start) * 1000)
        return {
            "tool": name,
            "tool_version": tool.spec.version,
            "input": validated,
            "input_hash": canonical_hash(validated),
            "output": output,
            "output_hash": canonical_hash(output),
            "duration_ms": duration_ms,
            "status": "completed",
        }

"""Tool contract: every deterministic tool exposes name, description,
input/output JSON schemas, a version, and execute().

The agent never receives raw database access — only this allow-listed
contract surface.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


MAX_VALIDATION_DEPTH = 32
MAX_INPUT_BYTES = 64 * 1024
MAX_OUTPUT_BYTES = 4 * 1024 * 1024

_JSON_SCALARS = (str, int, float, bool, type(None))


class ToolError(Exception):
    """Raised when a tool cannot produce a valid result."""

    def __init__(self, message: str, *, missing: bool = False, code: str = "internal_error", field: str | None = None) -> None:
        super().__init__(message)
        self.missing = missing
        self.code = code
        self.field = field

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "field": self.field,
            "missing": self.missing,
        }


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
        if type(kwargs) is not dict:
            raise ToolError("Tool arguments must be an object", code="invalid_input")
        _reject_non_json(kwargs, "Tool arguments", code="invalid_input")
        if _serialized_size(kwargs) > MAX_INPUT_BYTES:
            raise ToolError("Tool arguments exceed maximum request size", code="request_too_large")
        validate_payload(kwargs, self.spec.input_schema, self.spec.name, code="invalid_input")
        return deepcopy(kwargs)

    def validate_output(self, output: Any) -> dict[str, Any]:
        if type(output) is not dict:
            raise ToolError(
                "Tool output must be an object",
                code="invalid_output",
                field=f"{self.spec.name}.output",
            )
        _reject_non_json(output, "Tool output", code="invalid_output")
        if _serialized_size(output) > MAX_OUTPUT_BYTES:
            raise ToolError(
                "Tool output exceeds maximum response size",
                code="invalid_output",
                field=f"{self.spec.name}.output",
            )
        validate_payload(
            output,
            self.spec.output_schema,
            f"{self.spec.name}.output",
            code="invalid_output",
        )
        return output

    def execute_safe(self, **kwargs: Any) -> dict[str, Any]:
        registry = ToolRegistry()
        registry.register(self)
        try:
            return registry.execute(self.spec.name, kwargs)["output"]
        except ToolError as exc:
            return exc.as_dict()

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


def _reject(value: Any) -> None:
    raise ValueError(f"Unsupported type for JSON: {type(value).__name__}")


def _reject_non_json(value: Any, label: str, *, code: str) -> None:
    validate_json_compat(value, label, code=code)
    try:
        json.dumps(value, allow_nan=False, default=_reject)
    except (ValueError, TypeError, RecursionError) as exc:
        raise ToolError(f"{label} must be JSON-serializable", code=code) from exc


def _serialized_size(value: Any) -> int:
    return len(json.dumps(value, allow_nan=False, default=_reject).encode("utf-8"))


def validate_payload(
    value: Any,
    schema: dict[str, Any],
    path: str,
    *,
    code: str,
    depth: int = 0,
) -> None:
    if depth > MAX_VALIDATION_DEPTH:
        raise ToolError(f"Parameter '{path}' exceeds maximum nesting depth", code=code)
    expected = schema.get("type")
    valid = {
        "string": type(value) is str,
        "integer": type(value) is int,
        "number": type(value) in (int, float),
        "boolean": type(value) is bool,
        "array": type(value) is list,
        "object": type(value) is dict,
        "null": value is None,
    }
    if expected is not None:
        expected_types = expected if type(expected) is list else [expected]
        for expected_type in expected_types:
            if type(expected_type) is not str:
                raise ToolError(f"Schema for '{path}' has invalid type entry", code=code, field=path)
            if valid.get(expected_type, False):
                break
        else:
            raise ToolError(f"Parameter '{path}' must have type '{expected}'", code=code, field=path)
    if type(value) is float and not math.isfinite(value):
        raise ToolError(f"Parameter '{path}' must be finite", code=code, field=path)
    enum = schema.get("enum")
    if enum is not None and value not in enum:
        raise ToolError(
            f"Parameter '{path}' must be one of {enum}", code=code, field=path
        )
    if type(value) is dict:
        properties = schema.get("properties", {})
        extra_schema = schema.get("additionalProperties")
        closed = "properties" in schema or extra_schema is False
        for key in schema.get("required", []):
            if key not in value:
                raise ToolError(f"Missing required parameter '{path}.{key}'", code=code, field=f"{path}.{key}")
        for key, item in value.items():
            if type(key) is not str:
                raise ToolError(f"Parameter '{path}' keys must be strings", code=code, field=f"{path}.{key}")
            if key in properties:
                validate_payload(item, properties[key], f"{path}.{key}", code=code, depth=depth + 1)
            elif isinstance(extra_schema, dict):
                validate_payload(item, extra_schema, f"{path}.{key}", code=code, depth=depth + 1)
            elif closed:
                raise ToolError(f"Unknown parameter '{path}.{key}'", code=code, field=f"{path}.{key}")
    elif type(value) is list:
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", MAX_OUTPUT_BYTES):
            raise ToolError(f"Array '{path}' has invalid length", code=code, field=path)
        for index, item in enumerate(value):
            validate_payload(item, schema.get("items", {}), f"{path}[{index}]", code=code, depth=depth + 1)
    elif type(value) not in _JSON_SCALARS:
        raise ToolError(f"Parameter '{path}' must be JSON-compatible", code=code, field=path)


def validate_json_compat(value: Any, path: str, *, code: str, depth: int = 0) -> None:
    if depth > MAX_VALIDATION_DEPTH:
        raise ToolError(f"Parameter '{path}' exceeds maximum nesting depth", code=code)
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise ToolError(f"Parameter '{path}' keys must be strings", code=code, field=f"{path}.{key}")
            validate_json_compat(item, f"{path}.{key}", code=code, depth=depth + 1)
    elif type(value) is list:
        for index, item in enumerate(value):
            validate_json_compat(item, f"{path}[{index}]", code=code, depth=depth + 1)
    elif type(value) not in _JSON_SCALARS:
        raise ToolError(f"Parameter '{path}' must be JSON-compatible", code=code, field=path)


def canonical_json(payload: Any) -> str:
    def encode(value: Any, depth: int = 0) -> str:
        if depth > 32:
            raise ValueError("Maximum canonical nesting depth exceeded")
        if value is None or type(value) in (str, bool, int):
            return json.dumps(value, ensure_ascii=True, allow_nan=False)
        if type(value) is float:
            if not math.isfinite(value):
                raise ValueError("Non-finite number cannot be hashed")
            if value.is_integer():
                return str(int(value))
            return json.dumps(value, allow_nan=False)
        if type(value) is dict:
            if any(type(key) is not str for key in value):
                raise ValueError("Canonical object keys must be strings")
            return "{" + ",".join(
                json.dumps(key, ensure_ascii=True) + ":" + encode(value[key], depth + 1)
                for key in sorted(value)
            ) + "}"
        if type(value) is list:
            return "[" + ",".join(encode(item, depth + 1) for item in value) + "]"
        raise ValueError(f"Unsupported canonical type: {type(value).__name__}")

    return encode(payload)


def canonical_hash(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


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
        validated_output = tool.validate_output(output)
        return {
            "tool": name,
            "tool_version": tool.spec.version,
            "input": validated,
            "input_hash": canonical_hash(validated),
            "output": validated_output,
            "output_hash": canonical_hash(validated_output),
            "duration_ms": duration_ms,
            "status": "completed",
        }

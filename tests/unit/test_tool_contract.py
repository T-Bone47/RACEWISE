import math

import pytest

from racewise.tools.contract import (
    MAX_INPUT_BYTES,
    MAX_OUTPUT_BYTES,
    MAX_VALIDATION_DEPTH,
    Tool,
    ToolError,
    ToolRegistry,
    ToolSpec,
    canonical_hash,
    canonical_json,
    validate_payload,
)


class EchoTool(Tool):
    spec = ToolSpec(
        name="echo",
        description="Test boundary",
        input_schema={
            "type": "object",
            "properties": {
                "driver": {"type": "string"},
                "lap": {"type": "integer"},
                "gap": {"type": "number"},
                "clean": {"type": "boolean"},
                "drivers": {"type": "array", "items": {"type": "string"}},
                "window": {
                    "type": "object",
                    "properties": {"start": {"type": "integer"}},
                    "required": ["start"],
                },
            },
            "required": ["driver"],
        },
        output_schema={"type": "object"},
        version="test",
    )

    def execute(self, **kwargs):
        return kwargs


@pytest.mark.parametrize("arguments", [
    {}, {"driver": 123}, {"driver": "VER", "extra": 1},
    {"driver": "VER", "lap": True}, {"driver": "VER", "lap": 2.5},
    {"driver": "VER", "gap": "1"}, {"driver": "VER", "gap": False},
    {"driver": "VER", "gap": math.nan}, {"driver": "VER", "gap": math.inf},
    {"driver": "VER", "clean": 1}, {"driver": "VER", "drivers": "VER"},
    {"driver": "VER", "drivers": [1]}, {"driver": "VER", "window": []},
    {"driver": "VER", "window": {}},
    {"driver": "VER", "window": {"start": "1"}},
    {"driver": "VER", "window": {"start": 1, "extra": 2}},
    [], None,
])
def test_rejects_invalid_arguments(arguments):
    with pytest.raises(ToolError):
        EchoTool().validate_input(arguments)


def test_accepts_valid_arguments_without_coercion():
    arguments = {"driver": "VER", "lap": 1, "gap": 1.5, "clean": True,
                 "drivers": ["VER", "PER"], "window": {"start": 1}}
    assert EchoTool().validate_input(arguments) == arguments


def test_empty_schema_rejects_unknown_keys():
    tool = EchoTool()
    tool.spec = ToolSpec("empty", "Empty", {"type": "object", "properties": {}},
                         {"type": "object"}, "test")
    with pytest.raises(ToolError):
        tool.validate_input({"unexpected": True})


def test_registry_rejects_before_execution():
    registry = ToolRegistry()
    registry.register(EchoTool())
    with pytest.raises(ToolError):
        registry.execute("echo", {"driver": 42})


def test_registry_rejects_invalid_output_before_hashing(monkeypatch):
    tool = EchoTool()
    tool.spec = ToolSpec("invalid", "Invalid output", {"type": "object"},
                         {"type": "object", "properties": {"count": {"type": "integer"}},
                          "required": ["count"]}, "test")
    monkeypatch.setattr(tool, "execute", lambda **kwargs: {"count": True})
    registry = ToolRegistry()
    registry.register(tool)
    with pytest.raises(ToolError) as caught:
        registry.execute("invalid", {})
    assert caught.value.code == "invalid_output"
    assert caught.value.field == "invalid.output.count"


def test_canonical_order_and_numeric_equivalence():
    assert canonical_hash({"b": 1.0, "a": [0.0]}) == canonical_hash({"a": [0], "b": 1})
    assert canonical_json({"b": 1.25, "a": True}) == '{"a":true,"b":1.25}'
    assert canonical_hash(-0.0) == canonical_hash(0)


@pytest.mark.parametrize("left,right", [
    (1.25, "1.25"), (True, 1), (None, "None"), ([1, 2], [2, 1]),
    ({"a": 1}, {"a": 2}), (0.1, 0.10000000000000002),
])
def test_semantically_different_values_have_different_hashes(left, right):
    assert canonical_hash(left) != canonical_hash(right)


@pytest.mark.parametrize("value", [
    math.nan, math.inf, -math.inf, {1: "value"}, (1, 2), {1, 2}, object(),
])
def test_canonical_rejects_unsupported_values(value):
    with pytest.raises(ValueError):
        canonical_hash(value)


def test_canonical_rejects_cycles():
    value = []
    value.append(value)
    with pytest.raises(ValueError):
        canonical_hash(value)


def test_tool_error_as_dict_preserves_missing_flag():
    error = ToolError("Driver 'XX' not found in session", missing=True, code="missing_data", field="driver")
    assert error.as_dict() == {
        "code": "missing_data",
        "message": "Driver 'XX' not found in session",
        "field": "driver",
        "missing": True,
    }


def test_tool_error_defaults_are_backward_compatible():
    error = ToolError("Something failed")
    assert error.missing is False
    assert error.code == "internal_error"
    assert error.field is None
    assert error.as_dict() == {
        "code": "internal_error",
        "message": "Something failed",
        "field": None,
        "missing": False,
    }


def test_validate_output_accepts_valid_and_rejects_invalid():
    tool = EchoTool()
    tool.spec = ToolSpec(
        "out", "Out", {"type": "object"},
        {
            "type": "object",
            "properties": {
                "driver": {"type": "string"},
                "gap": {"type": ["number", "null"]},
                "laps": {"type": "array", "items": {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]}},
            },
            "required": ["driver"],
        },
        "test",
    )
    tool.validate_output({"driver": "VER", "gap": None, "laps": [{"n": 1}]})
    with pytest.raises(ToolError):
        tool.validate_output({"gap": 1.0})
    with pytest.raises(ToolError):
        tool.validate_output({"driver": "VER", "laps": [{"n": "1"}]})
    with pytest.raises(ToolError):
        tool.validate_output({"driver": "VER", "unexpected": 1})
    with pytest.raises(ToolError):
        tool.validate_output([1, 2])
    with pytest.raises(ToolError):
        tool.validate_output({"driver": "VER", "gap": math.nan})


def test_registry_rejects_non_dict_output():
    tool = EchoTool()
    tool.spec = ToolSpec("badshape", "Bad shape", {"type": "object"}, {"type": "object"}, "test")
    registry = ToolRegistry()
    registry.register(tool)
    original_execute = tool.execute
    tool.execute = lambda **kwargs: "not a dict"
    with pytest.raises(ToolError):
        registry.execute("badshape", {})


def test_output_validation_happens_before_hash(monkeypatch):
    tool = EchoTool()
    tool.spec = ToolSpec(
        "prehash", "Prehash", {"type": "object"},
        {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
        "test",
    )
    calls = []
    original = canonical_hash

    def spy(payload):
        calls.append(payload)
        return original(payload)

    monkeypatch.setattr("racewise.tools.contract.canonical_hash", spy)
    monkeypatch.setattr(tool, "execute", lambda **kwargs: {"ok": "nope"})
    registry = ToolRegistry()
    registry.register(tool)
    with pytest.raises(ToolError):
        registry.execute("prehash", {})
    assert calls == []


def test_validate_output_rejects_nonfinite_and_unserializable():
    tool = EchoTool()
    tool.spec = ToolSpec("finite", "Finite", {"type": "object"}, {"type": "object"}, "test")
    with pytest.raises(ToolError):
        tool.validate_output({"x": float("inf")})
    with pytest.raises(ToolError):
        tool.validate_output({"x": object()})
    with pytest.raises(ToolError):
        tool.validate_output({"x": (1, 2)})


def test_input_size_is_bounded():
    tool = EchoTool()
    with pytest.raises(ToolError) as caught:
        tool.validate_input({"driver": "x" * (MAX_INPUT_BYTES + 1)})
    assert caught.value.code == "request_too_large"


def test_output_size_is_bounded():
    tool = EchoTool()
    tool.spec = ToolSpec("big", "Big", {"type": "object"}, {"type": "object"}, "test")
    with pytest.raises(ToolError) as caught:
        tool.validate_output({"blob": "x" * (MAX_OUTPUT_BYTES + 1)})
    assert caught.value.code == "invalid_output"


def test_depth_is_bounded():
    schema = {"type": "object", "properties": {}}
    schema["properties"]["child"] = schema
    deep = {}
    cursor = deep
    for _ in range(MAX_VALIDATION_DEPTH + 2):
        cursor["child"] = {}
        cursor = cursor["child"]
    with pytest.raises(ToolError) as caught:
        validate_payload(deep, schema, "echo", code="invalid_input")
    assert "maximum nesting depth" in str(caught.value)


def test_bool_is_not_numeric_even_in_output():
    tool = EchoTool()
    tool.spec = ToolSpec(
        "boolnum", "BoolNum", {"type": "object"},
        {"type": "object", "properties": {"gap": {"type": "number"}}, "required": ["gap"]},
        "test",
    )
    with pytest.raises(ToolError):
        tool.validate_output({"gap": True})
    with pytest.raises(ToolError):
        validate_payload(True, {"type": "number"}, "x", code="invalid_input")
    with pytest.raises(ToolError):
        validate_payload(True, {"type": "integer"}, "x", code="invalid_input")


def test_execute_safe_returns_structured_error_instead_of_raising():
    class FailingTool(Tool):
        spec = ToolSpec(
            "fail", "Fail", {"type": "object", "properties": {"driver": {"type": "string"}}, "required": ["driver"]},
            {"type": "object"}, "test",
        )

        def execute(self, **kwargs):
            raise ToolError("Driver 'XX' not found in session", missing=True, code="missing_data", field="driver")

    result = FailingTool().execute_safe(driver="XX")
    assert result["code"] == "missing_data"
    assert result["field"] == "driver"
    assert result["missing"] is True

    invalid = FailingTool().execute_safe(driver=123)
    assert invalid["code"] == "invalid_input"
    assert invalid["missing"] is False

    class CrashTool(Tool):
        spec = ToolSpec("crash", "Crash", {"type": "object"}, {"type": "object"}, "test")

        def execute(self, **kwargs):
            raise ValueError("boom")

    with pytest.raises(ValueError):
        CrashTool().execute_safe()


def test_execute_safe_returns_payload_on_success():
    class OkTool(Tool):
        spec = ToolSpec(
            "ok", "Ok", {"type": "object", "properties": {"driver": {"type": "string"}}, "required": ["driver"]},
            {"type": "object", "properties": {"driver": {"type": "string"}}, "required": ["driver"]},
            "test",
        )

        def execute(self, **kwargs):
            return {"driver": kwargs["driver"]}

    assert OkTool().execute_safe(driver="VER") == {"driver": "VER"}


def test_tool_error_as_dict_from_missing_driver():
    tool = EchoTool()
    with pytest.raises(ToolError) as caught:
        validate_payload({}, {"type": "object", "properties": {}, "required": ["driver"]}, "x", code="invalid_input")
    assert caught.value.field == "x.driver"


def test_mutation_safeguards_input_not_clobbered_and_specs_not_shared():
    tool = EchoTool()
    arguments = {"driver": "VER", "window": {"start": 1}}
    validated = tool.validate_input(arguments)
    validated["window"]["start"] = 999
    assert arguments["window"]["start"] == 1
    spec_json = canonical_json(tool.spec.input_schema)
    tool.validate_input({"driver": "VER", "lap": 3})
    assert canonical_json(tool.spec.input_schema) == spec_json
    output_schema_json = canonical_json(tool.spec.output_schema)
    open_tool = EchoTool()
    with pytest.raises(ToolError):
        open_tool.validate_output([1, 2])
    assert canonical_json(tool.spec.output_schema) == output_schema_json


def test_execute_safe_validates_output(monkeypatch):
    tool = EchoTool()
    monkeypatch.setattr(tool, "execute", lambda **kwargs: [])
    result = tool.execute_safe(driver="VER")
    assert result["code"] == "invalid_output"


def test_deep_input_returns_tool_error():
    value = []
    for _ in range(1500):
        value = [value]
    with pytest.raises(ToolError):
        EchoTool().validate_input({"drivers": value, "driver": "VER"})


@pytest.mark.parametrize("value", [[], [1], [1, 2, 3]])
def test_declared_array_lengths_are_enforced(value):
    with pytest.raises(ToolError):
        validate_payload(value, {"type": "array", "minItems": 2, "maxItems": 2}, "window", code="invalid_output")

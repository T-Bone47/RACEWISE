"""Model registry contract tests (Phase E)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from racewise.agent.model_registry import (
    ModelRecord,
    ModelCapability,
    RoutingPolicy,
    RoutingDecision,
    ModelRegistry,
)


class TestModelRecord:
    def test_capabilities_default(self):
        r = ModelRecord(
            provider="openai",
            model_id="gpt-4o",
            display_name="GPT-4o",
            supports_structured_output=True,
            supports_tool_calls=True,
        )
        caps = r.capabilities()
        assert ModelCapability.TEXT_GENERATION in caps
        assert ModelCapability.STRUCTURED_OUTPUT in caps
        assert ModelCapability.TOOL_CALLS in caps

    def test_capabilities_unknown(self):
        r = ModelRecord(
            provider="openai",
            model_id="gpt-4o",
            display_name="GPT-4o",
            supports_structured_output=None,
        )
        # Unknown -> not in capabilities
        assert ModelCapability.STRUCTURED_OUTPUT not in r.capabilities()

    def test_has_capability_true(self):
        r = ModelRecord(
            provider="openai", model_id="gpt-4o", display_name="GPT-4o",
            supports_tool_calls=True,
        )
        assert r.has_capability(ModelCapability.TOOL_CALLS) is True

    def test_has_capability_false(self):
        r = ModelRecord(
            provider="openai", model_id="gpt-4o", display_name="GPT-4o",
            supports_tool_calls=False,
        )
        assert r.has_capability(ModelCapability.TOOL_CALLS) is False

    def test_has_capability_unknown(self):
        r = ModelRecord(
            provider="openai", model_id="gpt-4o", display_name="GPT-4o",
            supports_tool_calls=None,
        )
        # Unknown capability is NOT claimed as supported
        assert r.has_capability(ModelCapability.TOOL_CALLS) is False

    def test_status_flags(self):
        r = ModelRecord(
            provider="openai", model_id="gpt-4o", display_name="GPT-4o",
            configured=True, supported=True, reachable=False,
            integration_tested=False,
        )
        assert r.configured is True
        assert r.supported is True
        assert r.reachable is False
        assert r.integration_tested is False


class TestModelRegistry:
    def _make_registry(self):
        reg = ModelRegistry()
        reg.register(ModelRecord(
            provider="openai", model_id="gpt-4o", display_name="GPT-4o",
            reachable=True, supports_structured_output=True,
            task_scores={"answer_synthesis": 0.9},
        ))
        reg.register(ModelRecord(
            provider="anthropic", model_id="claude-sonnet-4", display_name="Claude",
            reachable=True, supports_structured_output=True,
            task_scores={"answer_synthesis": 0.85},
            cost_per_1m_tokens=0.003,
        ))
        reg.set_default("openai/gpt-4o")
        return reg

    def test_register_and_get(self):
        reg = self._make_registry()
        r = reg.get("openai/gpt-4o")
        assert r is not None
        assert r.model_id == "gpt-4o"

    def test_set_default(self):
        reg = self._make_registry()
        reg.set_default("anthropic/claude-sonnet-4")
        # No error = pass

    def test_set_default_unknown_raises(self):
        reg = self._make_registry()
        with pytest.raises(ValueError):
            reg.set_default("unknown/model")

    def test_route_default_policy(self):
        reg = self._make_registry()
        d = reg.route("answer_synthesis", policy=RoutingPolicy.DEFAULT)
        assert d.selected_provider == "openai"
        assert d.policy == RoutingPolicy.DEFAULT

    def test_route_quality_first(self):
        reg = self._make_registry()
        d = reg.route("answer_synthesis", policy=RoutingPolicy.QUALITY_FIRST)
        # gpt-4o has 0.9 > claude 0.85
        assert d.selected_provider == "openai"

    def test_route_cost_conscious(self):
        reg = self._make_registry()
        d = reg.route("answer_synthesis", policy=RoutingPolicy.COST_CONSCIOUS)
        # claude is cheaper (0.003 vs None=unknown->inf)
        assert d.selected_provider == "anthropic"

    def test_route_user_selected(self):
        reg = self._make_registry()
        d = reg.route(
            "answer_synthesis",
            policy=RoutingPolicy.USER_SELECTED,
            user_selected="anthropic/claude-sonnet-4",
        )
        assert d.selected_provider == "anthropic"

    def test_route_user_selected_unknown_raises(self):
        reg = self._make_registry()
        with pytest.raises(ValueError):
            reg.route(
                "answer_synthesis",
                policy=RoutingPolicy.USER_SELECTED,
                user_selected="unknown/model",
            )

    def test_route_user_selected_missing_cap_raises(self):
        reg = self._make_registry()
        # gpt-4o doesn't support streaming
        with pytest.raises(ValueError):
            reg.route(
                "answer_synthesis",
                policy=RoutingPolicy.USER_SELECTED,
                user_selected="openai/gpt-4o",
                required_caps={ModelCapability.STREAMING},
            )

    def test_route_no_models_raises(self):
        reg = ModelRegistry()
        with pytest.raises(ValueError):
            reg.route("answer_synthesis")

    def test_route_no_reachable_falls_back(self):
        reg = ModelRegistry()
        reg.register(ModelRecord(
            provider="openai", model_id="gpt-4o", display_name="GPT-4o",
            reachable=False,
        ))
        with pytest.raises(ValueError):
            reg.route("answer_synthesis")

    def test_list_models_with_capability_filter(self):
        reg = self._make_registry()
        results = reg.list_models(required_caps={ModelCapability.STRUCTURED_OUTPUT})
        assert len(results) == 2  # both support structured output

    def test_list_models_strips_unsupported(self):
        reg = self._make_registry()
        results = reg.list_models(required_caps={ModelCapability.STREAMING})
        assert len(results) == 0  # neither supports streaming

    def test_routing_decision_as_dict(self):
        d = RoutingDecision(
            selected_model="gpt-4o",
            selected_provider="openai",
            policy=RoutingPolicy.DEFAULT,
            reason="test",
            latency_ms=123.0,
        )
        out = d.as_dict()
        assert out["selected_model"] == "gpt-4o"
        assert out["policy"] == "default"
        assert out["latency_ms"] == 123.0


class TestDefaultRegistry:
    def test_built_in_registry_has_union_alpha(self):
        from racewise.agent.model_registry import MODEL_REGISTRY
        r = MODEL_REGISTRY.get("union_alpha/stealth/union-alpha")
        assert r is not None
        assert r.configured is True

    def test_built_in_registry_has_openai(self):
        from racewise.agent.model_registry import MODEL_REGISTRY
        r = MODEL_REGISTRY.get("openai/gpt-4o")
        assert r is not None
        assert r.configured is False  # no adapter yet

    def test_built_in_registry_has_anthropic(self):
        from racewise.agent.model_registry import MODEL_REGISTRY
        r = MODEL_REGISTRY.get("anthropic/claude-sonnet-4-20250514")
        assert r is not None
        assert r.configured is False

    def test_built_in_registry_has_gemini(self):
        from racewise.agent.model_registry import MODEL_REGISTRY
        r = MODEL_REGISTRY.get("gemini/gemini-2.5-pro")
        assert r is not None
        assert r.configured is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

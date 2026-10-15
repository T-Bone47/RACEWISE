"""Selective multi-model critique tests (Phase F).

All tests use stub providers — no network access. Live-provider critique
requires explicit credentials and stays out of the unit suite.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from racewise.agent.critique import (
    ALLOWED_CHECKS,
    MAX_CRITIQUE_CALLS,
    CritiqueResult,
    run_critique,
    should_critique,
)
from racewise.agent.provider import ProviderUnavailable
from racewise.agent.testing import (
    FailingProvider,
    RecordingProvider,
    ScriptedResponse,
    StubProvider,
)


def _clean_answer() -> dict[str, Any]:
    return {
        "question": "Why did VER lose time on lap 6?",
        "status": "ANSWERABLE",
        "hypotheses": [{"hypothesis_id": "H1", "state": "SUPPORTED"}],
        "residuals": [{"value": 0.01}],
        "contradicting_evidence": [],
        "not_established": [],
        "evidence_ledger": [{"evidence_id": "evidence_001"}],
    }


def _messy_answer() -> dict[str, Any]:
    return {
        "question": "Why did VER lose time on lap 6?",
        "status": "PARTIALLY_ANSWERABLE",
        "hypotheses": [{"hypothesis_id": "H1", "state": "MIXED_EVIDENCE"}],
        "residuals": [{"value": 0.464}],
        "contradicting_evidence": [{"id": "e1"}],
        "not_established": [{"a": 1}],
        "evidence_ledger": [{"evidence_id": "evidence_001"}],
    }


class TestShouldCritiqueGate:
    def test_clean_answer_does_not_fire(self):
        fire, reason = should_critique(_clean_answer())
        assert fire is False
        assert reason

    def test_contradicting_evidence_fires(self):
        fire, reason = should_critique(_messy_answer())
        assert fire is True

    def test_large_residual_fires(self):
        ans = _clean_answer()
        ans["residuals"] = [{"value": 0.5}]
        fire, _ = should_critique(ans)
        assert fire is True

    def test_mixed_evidence_hypothesis_fires(self):
        ans = _clean_answer()
        ans["hypotheses"] = [{"hypothesis_id": "H2", "state": "CONTRADICTED"}]
        fire, _ = should_critique(ans)
        assert fire is True

    def test_multiple_unestablished_fires(self):
        ans = _clean_answer()
        ans["not_established"] = [{"a": 1}, {"b": 2}]
        fire, _ = should_critique(ans)
        assert fire is True

    def test_empty_answer_does_not_fire(self):
        fire, _ = should_critique({})
        assert fire is False


class TestRunCritique:
    def _upheld_payload(self) -> str:
        return json.dumps({"passed": True, "violations": [], "summary": "clean"})

    def test_upheld_on_clean_review(self):
        provider = StubProvider([ScriptedResponse(content=self._upheld_payload())])
        result = run_critique(provider, _messy_answer(), ["evidence_001"])
        assert isinstance(result, CritiqueResult)
        assert result.verdict == "UPHELD"
        assert result.findings == ()
        assert result.iterations == 1

    def test_challenged_on_valid_violation(self):
        payload = json.dumps({
            "passed": False,
            "violations": [{"check": "ungrounded_number", "detail": "value has no source"}],
            "summary": "one issue",
        })
        provider = StubProvider([ScriptedResponse(content=payload)])
        result = run_critique(provider, _messy_answer(), ["evidence_001"])
        assert result.verdict == "CHALLENGED"
        assert len(result.findings) == 1
        assert result.findings[0].check == "ungrounded_number"

    def test_out_of_contract_checks_dropped(self):
        payload = json.dumps({
            "passed": False,
            "violations": [
                {"check": "ungrounded_number", "detail": "real issue"},
                {"check": "invented_check", "detail": "not in contract"},
            ],
            "summary": "mixed",
        })
        provider = StubProvider([ScriptedResponse(content=payload)])
        result = run_critique(provider, _messy_answer(), ["evidence_001"])
        assert result.verdict == "CHALLENGED"
        assert len(result.findings) == 1
        assert result.findings[0].check == "ungrounded_number"

    def test_malformed_output_retried_then_inconclusive(self):
        provider = StubProvider([
            ScriptedResponse(content="not json{{"),
            ScriptedResponse(content="still not json"),
        ])
        result = run_critique(provider, _messy_answer(), ["evidence_001"])
        assert result.verdict == "INCONCLUSIVE"
        assert result.iterations == MAX_CRITIQUE_CALLS

    def test_malformed_then_valid_recovers(self):
        provider = StubProvider([
            ScriptedResponse(content="not json"),
            ScriptedResponse(content=self._upheld_payload()),
        ])
        result = run_critique(provider, _messy_answer(), ["evidence_001"])
        assert result.verdict == "UPHELD"
        assert result.iterations == 2

    def test_missing_passed_flag_is_invalid(self):
        provider = StubProvider([
            ScriptedResponse(content=json.dumps({"violations": []})),
            ScriptedResponse(content=json.dumps({"violations": []})),
        ])
        result = run_critique(provider, _messy_answer(), ["evidence_001"])
        assert result.verdict == "INCONCLUSIVE"

    def test_unknown_evidence_citation_dropped(self):
        payload = json.dumps({
            "passed": False,
            "violations": [{
                "check": "phantom_capability",
                "detail": "cites evidence_deadbeef which never ran",
            }],
            "summary": "invented",
        })
        provider = StubProvider([ScriptedResponse(content=payload)])
        result = run_critique(provider, _messy_answer(), ["evidence_001"])
        # A critic that invents evidence is itself compromised:
        # fail closed to INCONCLUSIVE, never trust the verdict.
        assert result.verdict == "INCONCLUSIVE"
        assert result.findings == ()

    def test_provider_failure_raises(self):
        provider = FailingProvider(ProviderUnavailable("down"))
        with pytest.raises(ProviderUnavailable):
            run_critique(provider, _messy_answer(), ["evidence_001"])

    def test_unexpected_error_yields_inconclusive(self):
        class Boom:
            name = "boom"
            def respond(self, *a, **k):
                raise RuntimeError("exploded")
        result = run_critique(Boom(), _messy_answer(), ["evidence_001"])  # type: ignore[arg-type]
        assert result.verdict == "INCONCLUSIVE"

    def test_latency_recorded(self):
        provider = RecordingProvider(
            StubProvider([ScriptedResponse(content=self._upheld_payload())])
        )
        result = run_critique(provider, _messy_answer(), ["evidence_001"])
        assert result.latency_ms is not None
        assert result.latency_ms >= 0.0
        assert len(provider.records) == 1

    def test_result_as_dict(self):
        provider = StubProvider([ScriptedResponse(content=self._upheld_payload())])
        result = run_critique(provider, _messy_answer(), ["evidence_001"])
        d = result.as_dict()
        assert d["verdict"] == "UPHELD"
        assert d["provider"] == "stub"
        assert "critique_version" in d


class TestCritiqueContractConstants:
    def test_max_calls_bounded(self):
        assert MAX_CRITIQUE_CALLS == 2

    def test_allowed_checks_closed(self):
        assert "ungrounded_number" in ALLOWED_CHECKS
        assert "invented_check" not in ALLOWED_CHECKS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

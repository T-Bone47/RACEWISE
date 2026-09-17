"""Falsification gate invariants: synthesis must be impossible without it."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from racewise.domain.schemas import EvidenceType, Hypothesis, HypothesisStatus, InvestigationState
from racewise.investigation.engine import InvestigationEngine
from racewise.tools.contract import ToolRegistry


class NullRegistry:
    def execute(self, name, kwargs):
        raise NotImplementedError


def make_engine() -> InvestigationEngine:
    return InvestigationEngine(NullRegistry(), provider=None, question="q")


def test_fresh_engine_cannot_finalize():
    engine = make_engine()
    assert not engine.can_finalize()
    reasons = engine.gate_failures()
    assert "hypotheses_present" in reasons
    assert "falsification_attempted" in reasons
    assert "falsification_recorded" in reasons


def test_hypotheses_alone_are_insufficient():
    engine = make_engine()
    engine.add_hypothesis(Hypothesis(id="H1", statement="s", status=HypothesisStatus.SUPPORTED))
    assert not engine.can_finalize()
    assert "evidence_collected" in engine.gate_failures()


def test_evidence_alone_is_insufficient():
    engine = make_engine()
    engine.add_hypothesis(Hypothesis(id="H1", statement="s"))
    engine.add_evidence("claim", EvidenceType.FACT, [], None, supports=["H1"], strength=0.5)
    assert not engine.can_finalize()


def test_falsification_requires_contradicting_evidence_on_leading():
    engine = make_engine()
    engine.add_hypothesis(Hypothesis(id="H1", statement="s"))
    engine.add_evidence("claim", EvidenceType.CALCULATION, [], None, supports=["H1"], strength=0.5)
    engine.add_evidence("unrelated", EvidenceType.CALCULATION, [], None, contradicts=["H9"], strength=0.5)
    assert not engine.can_finalize()
    observation = engine.observe("gap_s", 0.4, "s", "analyze_traffic", "1.0.0")
    engine.add_evidence("challenge", EvidenceType.INFERENCE, [observation.id], None, contradicts=["H1"], strength=0.3)
    assert engine.can_finalize()


def test_synthesis_requires_explicit_completion():
    engine = make_engine()
    engine.add_hypothesis(Hypothesis(id="H1", statement="s"))
    observation = engine.observe("metric", 1.0, None, "tool", "1.0.0")
    engine.add_evidence("claim", EvidenceType.CALCULATION, [observation.id], None, supports=["H1"], strength=0.5)
    engine.add_evidence("challenge", EvidenceType.INFERENCE, [observation.id], None, contradicts=["H1"], strength=0.3)
    engine._set_state(InvestigationState.SYNTHESIS)
    assert engine.can_finalize()
    engine.finalize()
    assert engine.state == InvestigationState.COMPLETED


def test_finalize_blocks_without_falsification():
    engine = make_engine()
    engine.add_hypothesis(Hypothesis(id="H1", statement="s", status=HypothesisStatus.SUPPORTED))
    engine.add_evidence("claim", EvidenceType.CALCULATION, [], None, supports=["H1"], strength=0.5)
    engine._set_state(InvestigationState.SYNTHESIS)
    engine.finalize()
    assert engine.state == InvestigationState.INSUFFICIENT_EVIDENCE
    assert any(entry.type == "INSUFFICIENT_EVIDENCE" for entry in engine.event_log)


def test_evidence_with_observation_or_tool_is_supported():
    engine = make_engine()
    engine.add_hypothesis(Hypothesis(id="H1", statement="s"))
    observation = engine.observe("metric", 1.0, None, "tool", "1.0.0")
    engine.add_evidence("claim", EvidenceType.CALCULATION, [observation.id], None, supports=["H1"], strength=0.5)
    assert not engine.unsupported_claims()


def test_unsupported_claim_is_detected():
    engine = make_engine()
    engine.add_hypothesis(Hypothesis(id="H1", statement="s"))
    engine.add_evidence("orphan claim", EvidenceType.INFERENCE, ["missing-obs"], None, supports=["H1"], strength=0.5)
    assert engine.unsupported_claims() == ["orphan claim"]


def test_insufficient_evidence_when_falsification_refused():
    engine = make_engine()
    engine.add_hypothesis(Hypothesis(id="H1", statement="s", status=HypothesisStatus.SUPPORTED))
    engine.add_evidence("claim", EvidenceType.CALCULATION, [], None, supports=["H1"], strength=0.5)
    engine._set_state(InvestigationState.SYNTHESIS)
    engine.finalize()
    assert engine.state == InvestigationState.INSUFFICIENT_EVIDENCE

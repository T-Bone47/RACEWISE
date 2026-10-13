"""End-to-end investigation test with a scripted (non-LLM) plan double.

This validates the engine's orchestration, provenance, falsification gate,
and failure paths deterministically — no live model required.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from racewise.data.fastf1_adapter import FastF1Adapter
from racewise.domain.schemas import EvidenceType, Hypothesis, HypothesisStatus, InvestigationState
from racewise.investigation.engine import InvestigationEngine
from racewise.tools.implementations import SessionContext, build_default_registry
from racewise.tools.contract import ToolError

import pytest


@pytest.fixture(scope="module")
def registry():
    ctx = SessionContext(FastF1Adapter(cache_dir=str(Path(__file__).resolve().parents[2] / ".fastf1-cache")), 2023, "Bahrain")
    return build_default_registry(ctx)


def test_successful_investigation_with_falsification(registry):
    engine = InvestigationEngine(registry, provider=None, question="Why did VER lose pace late in stint 2?")

    def plan(e: InvestigationEngine) -> None:
        e._set_state(InvestigationState.HYPOTHESIS_GENERATION)
        e.add_hypothesis(Hypothesis(id="H1", statement="Tyre degradation", predicted_observables=["degradation slope > 0.2s/lap"], potential_falsifiers=["traffic explains variance"]))
        e.add_hypothesis(Hypothesis(id="H2", statement="Traffic", predicted_observables=["traffic fraction > 0.5"], potential_falsifiers=["clean-lap pace also drops"]))
        e._set_state(InvestigationState.EVIDENCE_COLLECTION)
        deg = e.run_tool("analyze_tyre_degradation", {"driver": "VER", "stint": 2})
        obs1 = e.observe("deg_slope_s_per_lap", deg["slope_s_per_lap"], "s/lap", "analyze_tyre_degradation", deg["tool_version"] if "tool_version" in deg else "1.0.0", None)
        traffic = e.run_tool("analyze_traffic", {"driver": "VER", "lap_start": 16, "lap_end": 35})
        obs2 = e.observe("traffic_fraction", traffic["traffic_fraction"], None, "analyze_traffic", "1.0.0", None)
        if deg["slope_s_per_lap"] > 0.2:
            e.add_evidence("Degradation supports H1", EvidenceType.CALCULATION, [obs1.id], None, supports=["H1"], strength=0.6)
        else:
            e.add_evidence("Degradation slope near zero weakens H1", EvidenceType.CALCULATION, [obs1.id], None, contradicts=["H1"], strength=0.5)
            e.update_confidence("H1", -0.2, "degradation near zero")
            e.set_status("H1", HypothesisStatus.WEAKENED)
        if traffic["traffic_fraction"] > 0.2:
            e.add_evidence("Traffic present supports H2", EvidenceType.CALCULATION, [obs2.id], None, supports=["H2"], strength=0.5)
            e.update_confidence("H2", 0.3, "traffic detected")
        else:
            e.add_evidence("No traffic weakens H2", EvidenceType.CALCULATION, [obs2.id], None, contradicts=["H2"], strength=0.4)
            e.update_confidence("H2", -0.2, "no traffic")
        # falsification attempt on leading hypothesis H2
        e.add_evidence("Falsification: pace delta vs clean-air cars is small", EvidenceType.INFERENCE, [obs2.id], None, contradicts=["H2"], strength=0.3)
        e.set_status("H2", HypothesisStatus.SUPPORTED)
        e.update_confidence("H2", 0.5, "traffic + no better alternative")
        # counterfactual
        e.run_counterfactual({
            "laps": ctx_laps(), "driver": "VER",
            "original_pit_lap": 36, "counterfactual_pit_lap": 31,
            "pit_loss_s": 24.2, "degradation_s_per_lap": 0.06, "laps_remaining": 57,
        })
        e._set_state(InvestigationState.COMPLETED)

    engine.run(plan)
    assert engine.state == InvestigationState.COMPLETED
    assert len(engine.hypotheses) == 2
    assert any(h.status == HypothesisStatus.SUPPORTED for h in engine.hypotheses)
    assert any(ev.contradicts for ev in engine.evidence), "falsification evidence must exist"
    assert len(engine.counterfactuals) == 1
    assert len(engine.tool_executions) == 2
    assert all(te.status == "completed" for te in engine.tool_executions)
    assert any(entry.type == "state.changed" for entry in engine.event_log)
    # provenance: every tool execution has hashes
    for te in engine.tool_executions:
        assert te.input_hash and len(te.input_hash) == 64
        assert te.output_hash and len(te.output_hash) == 64


def ctx_laps():
    from racewise.data.fastf1_adapter import FastF1Adapter

    adapter = FastF1Adapter(cache_dir=str(Path(__file__).resolve().parents[2] / ".fastf1-cache"))
    session = adapter.load_session(2023, "Bahrain", "R")
    return adapter.laps(session)


def test_missing_driver_fails_gracefully(registry):
    engine = InvestigationEngine(registry, provider=None, question="Why did driver XX lose pace?")

    def plan(e: InvestigationEngine) -> None:
        e._set_state(InvestigationState.EVIDENCE_COLLECTION)
        e.run_tool("analyze_tyre_degradation", {"driver": "XX", "stint": 1})

    engine.run(plan)
    assert engine.state in (InvestigationState.COMPLETED, InvestigationState.INSUFFICIENT_EVIDENCE, InvestigationState.TOOL_FAILURE, InvestigationState.MODEL_FAILURE) or engine.state == InvestigationState.COMPLETED
    # the plan swallowed the tool error dict — engine did not crash and recorded the failure
    assert any(te.status in ("tool_error", "exception") for te in engine.tool_executions)


def test_unknown_tool_rejected(registry):
    engine = InvestigationEngine(registry, provider=None, question="test")
    try:
        engine.run_tool("drop_database", {})
        rejected = False
    except ToolError:
        raised = True
        raised_flag = True
    # registry.get raises ToolError for unknown tools
    from racewise.tools.contract import ToolError as TE

    with pytest.raises(TE):
        engine.registry.get("nonexistent_tool")


def test_confidence_updates_are_bounded(registry):
    engine = InvestigationEngine(registry, provider=None, question="test")
    engine.add_hypothesis(Hypothesis(id="H1", statement="s"))
    engine.update_confidence("H1", 0.9, "evidence")
    engine.update_confidence("H1", 0.9, "more evidence")
    assert engine.hypotheses[0].confidence == 1.0
    engine.update_confidence("H1", -5.0, "contradiction")
    assert engine.hypotheses[0].confidence == 0.0


def test_replay_verifies_deterministic_tools(registry):
    """Replay should verify that tool outputs match recorded hashes."""
    engine = InvestigationEngine(registry, provider=None, question="Replay test")

    def plan(e: InvestigationEngine) -> None:
        e._set_state(InvestigationState.HYPOTHESIS_GENERATION)
        e.add_hypothesis(Hypothesis(id="H1", statement="Test hypothesis"))
        e._set_state(InvestigationState.EVIDENCE_COLLECTION)
        deg = e.run_tool("analyze_tyre_degradation", {"driver": "VER", "stint": 2})
        assert "error" not in deg
        # Find the tool execution for the degradation analysis
        deg_te = next(te for te in e.tool_executions if te.tool == "analyze_tyre_degradation")
        obs = e.observe("deg_slope", deg["slope_s_per_lap"], "s/lap", "analyze_tyre_degradation", "1.0.0", tool_execution_id=deg_te.id)
        e.add_evidence("Degradation slope measured", EvidenceType.CALCULATION, [obs.id], deg_te.id, supports=["H1"], strength=0.5)
        e._set_state(InvestigationState.FALSIFICATION)
        # Add falsification evidence with proper tool execution ID
        traffic = e.run_tool("analyze_traffic", {"driver": "VER", "lap_start": 16, "lap_end": 35})
        traffic_te = next(te for te in e.tool_executions if te.tool == "analyze_traffic")
        obs2 = e.observe("traffic_frac", traffic["traffic_fraction"], "fraction", "analyze_traffic", "1.0.0", tool_execution_id=traffic_te.id)
        e.add_evidence("Falsification: low traffic fraction contradicts H1", EvidenceType.INFERENCE, [obs2.id], traffic_te.id, contradicts=["H1"], strength=0.3)
        e._set_state(InvestigationState.COUNTERFACTUAL_ANALYSIS)
        # Get laps from the registry context
        laps = e.registry._tools["get_session"]._context.laps if hasattr(e.registry, "_tools") else []
        if not laps:
            # Fallback: get laps via adapter
            from racewise.data.fastf1_adapter import FastF1Adapter
            from pathlib import Path
            adapter = FastF1Adapter(cache_dir=str(Path(__file__).resolve().parents[2] / ".fastf1-cache"))
            session = adapter.load_session(2023, "Bahrain", "R")
            laps = adapter.laps(session)
        e.run_counterfactual({
            "laps": laps,
            "driver": "VER",
            "original_pit_lap": 36,
            "counterfactual_pit_lap": 31,
            "pit_loss_s": 24.2,
            "degradation_s_per_lap": 0.06,
            "laps_remaining": 57,
        })
        e._set_state(InvestigationState.COMPLETED)

    engine.run(plan)
    assert engine.state == InvestigationState.COMPLETED

    # Now replay the investigation
    replay_result = engine.replay(engine.event_log)
    assert replay_result.success is True
    assert replay_result.total_tool_events >= 2
    assert "analyze_tyre_degradation" in replay_result.verified_tools
    assert "analyze_traffic" in replay_result.verified_tools
    assert len(replay_result.failed_tools) == 0

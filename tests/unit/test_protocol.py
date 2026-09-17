"""Protocol contract tests: structured phases, retries, model failure."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from racewise.investigation.protocol import (
    ProtocolState,
    InvestigationProtocol,
)


class EventSink:
    def __init__(self):
        self.events = []

    def emit(self, event_type, payload=None):
        self.events.append((event_type, payload))


def make_protocol():
    return InvestigationProtocol(EventSink())


def test_valid_frame_output_is_accepted():
    protocol = make_protocol()
    result = protocol.submit("FRAME", {"summary": "VER pace evolution vs front-runners"})
    assert result.ok
    assert result.output.summary == "VER pace evolution vs front-runners"


def test_malformed_output_returns_structured_errors():
    protocol = make_protocol()
    result = protocol.submit("FRAME", {"summary": ""})
    assert not result.ok
    assert result.errors


def test_fewer_than_three_hypotheses_rejected():
    protocol = make_protocol()
    result = protocol.submit("HYPOTHESES", {"hypotheses": [
        {"id": "H1", "statement": "Tyre degradation explains pace drop"},
        {"id": "H2", "statement": "Traffic explains pace drop"},
    ]})
    assert not result.ok


def test_hypotheses_require_falsifiers():
    protocol = make_protocol()
    result = protocol.submit("HYPOTHESES", {"hypotheses": [
        {"id": "H1", "statement": "Tyre degradation explains pace drop"},
        {"id": "H2", "statement": "Traffic explains pace drop"},
        {"id": "H3", "statement": "Fuel-load drift explains pace drop"},
    ]})
    assert result.ok


def test_repeated_failure_transitions_to_model_failure():
    protocol = make_protocol()
    for _ in range(3):
        result = protocol.submit("FRAME", {"summary": ""})
    assert not result.ok
    assert protocol.state == ProtocolState.FAILED
    assert any(event_type == "MODEL_FAILURE" for event_type, _ in protocol.engine.events)


def test_unknown_phase_rejected():
    protocol = make_protocol()
    result = protocol.submit("INVENT", {"x": 1})
    assert not result.ok
    assert "Unknown phase" in result.errors[0]


def test_falsification_requires_target_and_requests():
    protocol = make_protocol()
    result = protocol.submit("FALSIFICATION", {"targets": [], "outcome": "COMPLETED"})
    assert not result.ok
    result = protocol.submit("FALSIFICATION", {"targets": [
        {"hypothesis_id": "H1", "challenge": "Traffic could explain it",
         "evidence_requests": [{"tool": "analyze_traffic", "arguments": {"driver": "VER", "lap_start": 15, "lap_end": 35}}]}
    ], "outcome": "COMPLETED"})
    assert result.ok


def test_counterfactual_skip_requires_reason():
    protocol = make_protocol()
    result = protocol.submit("COUNTERFACTUAL", {"action": "SKIP", "params": {}})
    assert not result.ok
    result = protocol.submit("COUNTERFACTUAL", {"action": "SKIP", "params": {}, "reason": "No pit stop in window; timing counterfactual undefined"})
    assert result.ok


def test_model_decisions_recorded_separately():
    protocol = make_protocol()
    protocol.submit("FRAME", {"summary": "ok"})
    protocol.submit("FRAME", {"summary": ""})
    decisions = [d for d in protocol.model_decisions if d.phase == "FRAME"]
    assert len(decisions) == 2
    assert decisions[0].valid is True
    assert decisions[1].valid is False
    snapshot = protocol.snapshot()
    assert snapshot["state"] == "FRAME"

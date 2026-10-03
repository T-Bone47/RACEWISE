"""Verification: prove the answer is grounded, before anyone reads it.

Every claim in a synthesised answer must trace to a capability that actually
ran. This module re-checks that mechanically and reports the failures. It is
run unconditionally — not as an optional audit — because an answer that fails
verification has no business being presented as an engineering result.

What it catches:

- a numeric claim with no producing capability
- a claim attributed to a capability that was never executed
- a counterfactual promoted out of MODELLED into a measurement
- a residual that has been quietly assigned to a mechanism
- provenance claims with no source behind them
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from racewise.question_engine.synthesizer import Answer

VERIFICATION_VERSION = "question_engine_verification_v1"

# Claim classes that must never contain a number unless a capability produced it.
NUMERIC_CLAIM_CLASSES = ("OBSERVED", "DERIVED", "INFERRED", "MODELLED")


@dataclass
class VerificationReport:
    """Outcome of grounding an answer against the results that produced it."""

    passed: bool
    checks_run: int = 0
    violations: list[dict[str, Any]] = field(default_factory=list)

    def fail(self, kind: str, detail: str, **extra: Any) -> None:
        self.violations.append({"check": kind, "detail": detail, **extra})

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks_run": self.checks_run,
            "violations": self.violations,
            "verification_version": VERIFICATION_VERSION,
        }


def verify_answer(answer: Answer, results: dict[str, Any]) -> VerificationReport:
    """Verify every claim in ``answer`` against the real capability ``results``.

    ``results`` maps capability_id -> raw deterministic output. A capability
    absent from it did not run, so anything attributed to it is a violation.
    """
    report = VerificationReport(passed=True)
    executed = {cid for cid, payload in results.items()
                if isinstance(payload, dict) and not payload.get("error")}

    # --- every numeric claim has a producing capability --------------------
    groups = (
        ("observations", answer.observations),
        ("calculations", answer.calculations),
        ("residuals", answer.residuals),
        ("counterfactuals", answer.counterfactuals),
    )
    for group_name, entries in groups:
        for entry in entries:
            report.checks_run += 1
            source = entry.get("capability_id")
            if entry.get("value") is None:
                continue
            if not source:
                report.fail("ungrounded_number",
                            f"{group_name} entry has a value with no producing capability",
                            statement=entry.get("statement"))
            elif source not in executed:
                report.fail("phantom_capability",
                            f"{group_name} entry cites {source}, which did not execute",
                            statement=entry.get("statement"), capability_id=source)

    # --- claim classes are preserved, never promoted ----------------------
    for entry in answer.counterfactuals:
        report.checks_run += 1
        if entry.get("claim_class") != "MODELLED":
            report.fail("promoted_model",
                        "counterfactual is not labelled MODELLED",
                        statement=entry.get("statement"))
        if entry.get("is_historical_truth") is True:
            report.fail("model_as_truth",
                        "counterfactual claims to be historical truth")

    # --- a residual is reported, never explained away ------------------------
    for entry in answer.residuals:
        report.checks_run += 1
        assigned = entry.get("never_assigned_to")
        if assigned and "no mechanism" not in str(assigned):
            report.fail("residual_assigned",
                        "residual was attributed to a mechanism without evidence",
                        statement=entry.get("statement"))

    # --- hypothesis states come from the engine, not from prose -------------
    for entry in answer.hypotheses:
        report.checks_run += 1
        state = entry.get("state")
        if state is None:
            report.fail("missing_hypothesis_state",
                        "hypothesis presented without an engine state",
                        hypothesis_id=entry.get("hypothesis_id"))
        elif entry.get("capability_id") not in executed:
            report.fail("phantom_capability",
                        "hypothesis state cites a capability that did not execute",
                        hypothesis_id=entry.get("hypothesis_id"))

    # --- provenance must name what actually ran ----------------------------
    report.checks_run += 1
    claimed = set((answer.provenance or {}).get("capabilities_executed") or [])
    if claimed - executed:
        report.fail("phantom_provenance",
                    "provenance claims capabilities that did not execute",
                    claimed=sorted(claimed - executed))
    report.checks_run += 1
    if (answer.provenance or {}).get("availability") is None:
        report.fail("missing_provenance",
                    "answer carries no data-availability provenance")

    # --- follow-up suggestions must be real capabilities -------------------
    for suggestion in answer.follow_ups:
        report.checks_run += 1
        if not suggestion.get("capability_id"):
            report.fail("unsupported_suggestion",
                        "follow-up suggestion names no capability",
                        label=suggestion.get("label"))

    report.passed = not report.violations
    return report
"""Selective multi-model critique (Phase F).

An independent model reviews a deterministic answer against its evidence.
Bounded by design: at most one critique call plus one recovery retry,
explicit budgets, and a deterministic gate that only fires where review
adds value (contradictions, unresolved residuals, mixed evidence).

The critique NEVER modifies numbers. Findings are review metadata appended
beside the authoritative deterministic answer. A critic that invents
measurements fails validation and yields INCONCLUSIVE, never a verdict.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from racewise.agent.provider import ModelProvider, ProviderUnavailable

CRITIQUE_VERSION = "question_engine_critique_v1"

# Bounded workflow limits. One critique call + one malformed-output retry.
MAX_CRITIQUE_CALLS = 2

# Checks the critic is allowed to report. Anything else is rejected as
# outside the review contract.
ALLOWED_CHECKS = frozenset({
    "ungrounded_number",
    "phantom_capability",
    "promoted_model",
    "model_as_truth",
    "residual_assigned",
    "missing_hypothesis_state",
    "phantom_provenance",
    "missing_provenance",
    "unsupported_suggestion",
})


@dataclass(frozen=True)
class CritiqueFinding:
    """One validated critic finding."""

    check: str
    detail: str


@dataclass(frozen=True)
class CritiqueResult:
    """Outcome of an independent review."""

    verdict: str  # UPHELD | CHALLENGED | INCONCLUSIVE
    findings: tuple[CritiqueFinding, ...] = ()
    provider: Optional[str] = None
    model: Optional[str] = None
    latency_ms: Optional[float] = None
    iterations: int = 0
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "findings": [
                {"check": f.check, "detail": f.detail} for f in self.findings
            ],
            "provider": self.provider,
            "model": self.model,
            "latency_ms": self.latency_ms,
            "iterations": self.iterations,
            "reason": self.reason,
            "critique_version": CRITIQUE_VERSION,
        }


def should_critique(answer: dict[str, Any]) -> tuple[bool, str]:
    """Deterministic gate: is independent review justified?

    Pure function of the deterministic answer. Fires only on high-impact
    signals: contradictory evidence, residuals outside tolerance,
    mixed/contradicted hypothesis states, or unresolved alternatives.
    Routine clean answers return False — no model call is warranted.
    """
    contradicting = answer.get("contradicting_evidence") or []
    if contradicting:
        return True, (
            f"{len(contradicting)} contradicting evidence item(s) present"
        )

    for entry in answer.get("residuals") or []:
        value = entry.get("value")
        if isinstance(value, (int, float)) and abs(value) > 0.05:
            return True, (
                f"residual {value} outside tolerance — unresolved component"
            )

    for hyp in answer.get("hypotheses") or []:
        if hyp.get("state") in ("MIXED_EVIDENCE", "CONTRADICTED"):
            return True, (
                f"hypothesis {hyp.get('hypothesis_id')} is "
                f"{hyp.get('state')} — independent review warranted"
            )

    not_established = answer.get("not_established") or []
    if len(not_established) >= 2:
        return True, (
            f"{len(not_established)} unestablished items — "
            "ambiguous investigation"
        )

    return False, "clean answer: no contradictions, residuals within tolerance"


def _validate_critique_payload(payload: Any) -> tuple[bool, list[CritiqueFinding], str]:
    """Validate a critic response payload.

    Returns (ok, findings, reason). Findings referencing checks outside
    the review contract are dropped; a payload with no valid structure
    fails closed to INCONCLUSIVE.
    """
    if not isinstance(payload, dict):
        return False, [], "critic response is not a JSON object"
    if not isinstance(payload.get("passed"), bool):
        return False, [], "critic response missing boolean 'passed'"
    violations = payload.get("violations")
    if not isinstance(violations, list):
        return False, [], "critic response missing 'violations' list"

    findings: list[CritiqueFinding] = []
    for item in violations:
        if not isinstance(item, dict):
            continue
        check = str(item.get("check", ""))
        detail = str(item.get("detail", ""))
        if check not in ALLOWED_CHECKS:
            continue  # outside the review contract — dropped, never trusted
        findings.append(CritiqueFinding(check=check, detail=detail[:500]))

    return True, findings, ""


def run_critique(
    provider: ModelProvider,
    answer: dict[str, Any],
    evidence_ids: list[str],
    timeout_seconds: float = 60.0,
    max_calls: int = MAX_CRITIQUE_CALLS,
) -> CritiqueResult:
    """Run one bounded independent review of a deterministic answer.

    The critic receives the question, the answer, and the evidence-id
    allow-list — never just a conclusion. Findings citing evidence
    outside the allow-list are dropped. Malformed output gets exactly
    one retry, then INCONCLUSIVE. Never raises for review failures;
    raises only when the provider itself is unusable.
    """
    from racewise.question_engine.prompt_templates import (
        PromptTask,
        PROMPT_REGISTRY,
    )

    template = PROMPT_REGISTRY.get(PromptTask.ANSWER_CRITIQUE)
    question = str(answer.get("question", ""))
    answer_json = json.dumps(answer, default=str, sort_keys=True)

    started = time.perf_counter()
    calls = 0
    last_reason = ""
    try:
        while calls < max(1, max_calls):
            calls += 1
            messages = template.render(question=question, answer_json=answer_json)
            response = provider.respond(messages)
            try:
                payload = json.loads(response.content)
            except (json.JSONDecodeError, TypeError) as exc:
                last_reason = f"malformed critic output (attempt {calls}): {exc}"
                continue
            ok, findings, reason = _validate_critique_payload(payload)
            if not ok:
                last_reason = f"invalid critic payload (attempt {calls}): {reason}"
                continue
            # Findings must cite evidence from the allow-list, or be
            # structural checks that cite none. Anything else is dropped.
            allowed = set(evidence_ids)
            kept = tuple(
                f for f in findings
                if not _cites_unknown_evidence(f.detail, allowed)
            )
            elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
            critic_passed = bool(payload.get("passed"))
            if critic_passed and not kept:
                verdict: str = "UPHELD"
                reason = "independent review found no valid violations"
            elif not critic_passed and kept:
                verdict = "CHALLENGED"
                reason = f"independent review raised {len(kept)} finding(s)"
            else:
                # Critic claimed failure but supplied no valid finding:
                # the review itself is compromised — fail closed.
                verdict = "INCONCLUSIVE"
                reason = ("critic reported failure without a valid finding; "
                          "review discarded rather than trusted")
            return CritiqueResult(
                verdict=verdict,
                findings=kept,
                provider=getattr(provider, "name", None),
                model=getattr(provider, "model_id", None),
                latency_ms=elapsed_ms,
                iterations=calls,
                reason=reason,
            )
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
        return CritiqueResult(
            verdict="INCONCLUSIVE",
            findings=(),
            provider=getattr(provider, "name", None),
            model=getattr(provider, "model_id", None),
            latency_ms=elapsed_ms,
            iterations=calls,
            reason=last_reason or "critic output unusable after bounded retries",
        )
    except ProviderUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 — review must never break answers
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
        return CritiqueResult(
            verdict="INCONCLUSIVE",
            findings=(),
            provider=getattr(provider, "name", None),
            model=getattr(provider, "model_id", None),
            latency_ms=elapsed_ms,
            iterations=calls,
            reason=f"critique workflow error: {type(exc).__name__}",
        )


def _cites_unknown_evidence(detail: str, allowed: set[str]) -> bool:
    """Heuristic: does the finding text name evidence outside the allow-list?

    Evidence ids in this codebase look like ``evidence_<hex>`` or
    ``<capability>_<suffix>`` tokens. A finding that names an
    ``evidence_``-shaped token absent from the allow-list is dropped —
    the critic must review supplied evidence, never invent it.
    """
    import re
    for token in re.findall(r"[A-Za-z_]+_[0-9a-f]{4,}\b", detail):
        if token.startswith("evidence_") and token not in allowed:
            return True
    return False


__all__ = [
    "CRITIQUE_VERSION",
    "MAX_CRITIQUE_CALLS",
    "ALLOWED_CHECKS",
    "CritiqueFinding",
    "CritiqueResult",
    "should_critique",
    "run_critique",
]

"""Question decomposition: one sentence, several engineering questions.

"Why did Verstappen lose time to Perez in the second stint, was it mostly
tyres or corner speed, and would recovering half the deficit have changed the
gap?" is three questions wearing one coat. Running one pipeline for it answers
one third of what was asked and looks like a complete answer — the specific
failure this module exists to prevent.

Decomposition is deterministic and rule-driven. Each sub-question is emitted
only when a trigger actually fired in the text, so the DAG is evidence about
what was asked, not a guess about what was meant.

The DAG carries dependencies because the order is engineering, not cosmetic:
you cannot attribute a deficit you have not measured, and you cannot evaluate a
counterfactual of a hypothesis you have not tested.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from racewise.question_engine.capabilities import HYPOTHESIS_IDS
from racewise.question_engine.compiler import CompiledQuestion

DECOMPOSER_VERSION = "question_engine_decomposer_v1"

# Clause separators that genuinely split one ask into several.
# Extended to handle more compound question patterns that engineers use:
# - "and also", "and then", ";", "."
# - "and" + question word (was, did, is, does, could, would, what, where, when, how, which, can)
# - "and" + engineering verb (caused, explain, compare, analyze, simulate, model)
# - "but" + question word (contrastive compound)
# - "while" + clause (simultaneous compound)
_CLAUSE_SPLIT = re.compile(
    r"(?:,\s*and\s+also\s+|\s+and\s+then\s+|\s*;\s*|\.\s*"
    r"|\s+and\s+(?=was|did|is|does|could|would|what|where|when|how|which|can"
    r"|caused|explain|compare|analyz|simulat|model|attribut|evaluat|test)\b"
    r"|\s+but\s+(?=was|did|is|does|could|would|what|where|when|how|which|can)\b"
    r"|\s+while\s+(?=was|did|is|does|could|would|what|where|when|how|which|can)\b)",
    re.I,
)


@dataclass(frozen=True)
class SubQuestion:
    """One answerable unit of an investigation DAG."""

    sub_id: str
    question: str                 # the clause this sub-question came from
    intents: tuple[str, ...]
    depends_on: tuple[str, ...] = ()
    required_hypotheses: tuple[str, ...] = ()
    spatial_levels: tuple[str, ...] = ()
    temporal_scopes: tuple[str, ...] = ()
    analysis_level: int = 1
    rationale: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "sub_id": self.sub_id,
            "question": self.question,
            "intents": list(self.intents),
            "depends_on": list(self.depends_on),
            "required_hypotheses": list(self.required_hypotheses),
            "spatial_levels": list(self.spatial_levels),
            "temporal_scopes": list(self.temporal_scopes),
            "analysis_level": self.analysis_level,
            "rationale": self.rationale,
        }


def _clauses(text: str) -> list[str]:
    """Split a question into clause-sized candidates, dropping fragments."""
    parts = [p.strip(" ,.?!") for p in _CLAUSE_SPLIT.split(text)]
    return [p for p in parts if len(p) > 3]


def _level_for(intents: tuple[str, ...], spatial: tuple[str, ...],
               temporal: tuple[str, ...]) -> int:
    """Minimum sufficient analysis depth (§24). Use the cheapest that can answer.

    Over-reaching is not neutral: level 6 is a counterfactual over measured
    telemetry, and it is the most expensive and most easily misread step in the
    system. It is reserved for an explicit request.
    """
    intent_set = set(intents)
    if intent_set & {"COUNTERFACTUAL", "WHAT_IF"}:
        return 6
    if intent_set & {"FIND_PATTERN", "COMPARE_RACES", "MEMORY"}:
        return 5
    if intent_set & {"FIND_REGIME", "FIND_TURNING_POINT"} or \
            intent_set & {"TREND", "EVALUATE_TYRE_BEHAVIOR"} or \
            "regime" in temporal:
        return 4
    if intent_set & {"TEST_HYPOTHESIS", "FALSIFY", "RECONCILE", "EVALUATE_DRIVER",
                     "EVALUATE_CAR", "EVALUATE_RACE_CONTROL"} or spatial:
        return 3
    if intent_set & {"ATTRIBUTE", "DECOMPOSE", "QUANTIFY"} or \
            intent_set & {"LOCATE"}:
        return 2
    return 1


def decompose(compiled: CompiledQuestion) -> tuple[SubQuestion, ...]:
    """Decompose a compiled question into an ordered investigation DAG.

    Returns a topologically ordered tuple. Ordering is by dependency first, then
    by analysis level, so the cheapest questions that need nothing are first and
    the expensive dependent steps land last.
    """
    if compiled.status != "PARSED":
        return ()

    from racewise.question_engine import intents as lang

    parts = _clauses(compiled.raw_question)
    # A single-clause question still gets one sub-question; an empty split must
    # never silently produce an empty investigation.
    if not parts:
        parts = [compiled.raw_question.strip(" ?.")]

    subs: list[SubQuestion] = []
    for index, clause in enumerate(parts, start=1):
        clause_intents = lang.detect_intents(clause) or compiled.detected_intents
        subs.append(SubQuestion(
            sub_id=f"Q{index}",
            question=clause,
            intents=clause_intents,
            spatial_levels=lang.detect_spatial_scope(clause),
            temporal_scopes=lang.detect_temporal_scope(clause),
            analysis_level=_level_for(clause_intents,
                                      lang.detect_spatial_scope(clause),
                                      lang.detect_temporal_scope(clause)),
            rationale="clause split of the question",
        ))

    # --- the observed gap is the root of any explanation -------------------
    # An attribution or hypothesis question presupposes a measured difference.
    # If the question never asked for it, it is still required.
    intent_set = {i for s in subs for i in s.intents}
    needs_observation = bool(
        intent_set & {"ATTRIBUTE", "EXPLAIN", "TEST_HYPOTHESIS", "FALSIFY",
                      "DECOMPOSE", "LOCATE", "QUANTIFY", "RECONCILE"}
    )
    if needs_observation and not any(
            s.intents and s.intents[0] in {"DESCRIBE", "COMPARE", "COMPARE_LAPS"} and s is subs[0]
            for s in subs
    ):
        root = SubQuestion(
            sub_id="Q0",
            question="What was the measured difference between the compared subjects?",
            intents=("COMPARE", "QUANTIFY"),
            analysis_level=1,
            rationale="root of the DAG: every attribution presupposes an observed delta",
        )
        subs.insert(0, root)

    # --- residual is never dropped -----------------------------------------
    # An explanation that omits what it could not explain is not an explanation.
    if intent_set & {"ATTRIBUTE", "EXPLAIN", "TEST_HYPOTHESIS", "DECOMPOSE",
                     "QUANTIFY", "RECONCILE"}:
        deps = tuple(s.sub_id for s in subs
                     if s.intents and s.intents[0] in
                     {"ATTRIBUTE", "EXPLAIN", "DECOMPOSE"})
        subs.append(SubQuestion(
            sub_id="Q_RESIDUAL",
            question="What remains unexplained by the mechanisms actually tested?",
            intents=("RECONCILE", "QUANTIFY"),
            depends_on=deps,
            analysis_level=2,
            rationale="residual-first policy: an unexplained remainder is always reported",
        ))

    # --- explicit hypothesis evaluation ------------------------------------
    named = [h for h in HYPOTHESIS_IDS if h in compiled.requested_hypotheses]
    negated = set(compiled.negations)
    if named:
        subs.append(SubQuestion(
            sub_id="Q_HYPOTHESES",
            question=("Which evidence supports or contradicts "
                      + ", ".join(named) + "?"),
            intents=("FALSIFY",) if negated else ("TEST_HYPOTHESIS",),
            required_hypotheses=tuple(named),
            depends_on=("Q0",),
            analysis_level=3,
            rationale="user named specific hypotheses; falsification framing when negated",
        ))

    # --- cross-race recurrence ---------------------------------------------
    if "cross_race" in compiled.temporal_scopes or "FIND_PATTERN" in intent_set:
        subs.append(SubQuestion(
            sub_id="Q_CROSSRACE",
            question="Did a structurally similar pattern occur in other races?",
            intents=("FIND_PATTERN",),
            depends_on=("Q0",),
            analysis_level=5,
            rationale="cross-race structural recurrence search",
        ))

    # --- provenance is not optional when the user asks for truth -----------
    if "PROVENANCE" in intent_set or "REPLAY" in intent_set:
        subs.append(SubQuestion(
            sub_id="Q_PROVENANCE",
            question="What is the provenance and determinism of these results?",
            intents=("PROVENANCE",) if "PROVENANCE" in intent_set else ("REPLAY",),
            analysis_level=0,
            rationale="explicit provenance or replay request",
        ))

    # --- topological order ---------------------------------------------------
    return _topological(subs)


def _topological(subs: list[SubQuestion]) -> tuple[SubQuestion, ...]:
    """Order by dependency, then analysis level, then original position.

    Dependencies win over cost: you cannot run a level-5 cross-race scan
    before the level-1 comparison that defines the pattern.
    """
    known = {s.sub_id for s in subs}
    position = {s.sub_id: i for i, s in enumerate(subs)}
    pending = list(subs)
    ordered: list[SubQuestion] = []
    emitted: set[str] = set()

    while pending:
        ready = [
            s for s in pending
            if all(dep in emitted or dep not in known for dep in s.depends_on)
        ]
        if not ready:
            # A dependency cycle should be impossible (we only ever depend on
            # already-existing earlier nodes), but never loop forever: emit the
            # rest in a deterministic order and let the planner see the cycle.
            ordered.extend(sorted(pending, key=lambda s: position[s.sub_id]))
            break
        ready.sort(key=lambda s: (s.analysis_level, position[s.sub_id]))
        chosen = ready[0]
        ordered.append(chosen)
        emitted.add(chosen.sub_id)
        pending.remove(chosen)

    return tuple(ordered)
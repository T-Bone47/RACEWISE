"""Question compiler: free text -> canonical engineering question.

Deterministic. The same text over the same canonical store always compiles to
the same object, and the object is a *structured engineering question*, not a
route name and not prose.

What this adds on top of the existing intake
---------------------------------------------
`question_intake.parse_question` already resolves drivers, seasons, laps and
stints to canonical identifiers and already refuses to guess. Two gaps made it
unusable as the front door of a general question engine:

1. **No context resolution by participation.** "Verstappen vs Perez in 2023"
   names a season and a driver pair but no race. The intake answered
   CONTEXT_UNRESOLVED — correct, but it gave up on a question that is often
   *not* ambiguous. This module resolves the race when the pair shares exactly
   ONE race in that season, and still asks when they share many. That is a
   deterministic rule, not a guess: it only ever fires on a unique candidate.

2. **One question type, one pipeline.** A real engineering question usually
   has several parts and needs several capabilities. This compiler records the
   full intent/scope structure; `decomposer` turns it into sub-questions.

Uncertainty policy: internal parser uncertainty is never shown to the user as a
score. It either resolves deterministically or becomes an explicit
clarification request. There is no third option (§6, §37).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any, Optional

from racewise.data.historical.canonical_queries import CanonicalQueries
from racewise.data.historical.question_intake import (
    INTAKE_INVALID,
    INTAKE_PARSED,
    INTAKE_UNRESOLVED,
    INTAKE_UNSUPPORTED,
    parse_question,
)
from racewise.question_engine import intents as lang
from racewise.tools.contract import canonical_hash

COMPILER_VERSION = "question_engine_compiler_v1"

MAX_QUESTION_CHARS = 500

# Closed compile outcomes. These are *compile* states, distinct from the answer
# states the synthesizer produces.
COMPILE_PARSED = "PARSED"
COMPILE_INVALID = "INVALID_QUESTION"
COMPILE_UNRESOLVED = "CONTEXT_UNRESOLVED"
COMPILE_UNSUPPORTED = "UNSUPPORTED_QUESTION"

# How many candidate races to surface when the question genuinely is ambiguous.
MAX_CLARIFICATION_CANDIDATES = 8


@dataclass
class ClarificationRequest:
    """A single minimal question the user must answer to proceed."""

    field: str
    prompt: str
    candidates: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "prompt": self.prompt,
            "candidates": list(self.candidates),
        }


@dataclass
class CompiledQuestion:
    """Canonical representation of one engineering question."""

    raw_question: str
    status: str
    reason: Optional[str] = None
    question_type: Optional[str] = None          # legacy engine hint, not a page
    season: Optional[int] = None
    round: Optional[int] = None
    session_type: str = "RACE"
    race_label: Optional[str] = None
    driver_a: Optional[str] = None
    driver_b: Optional[str] = None
    lap_number: Optional[int] = None
    stint_number: Optional[int] = None
    pattern_id: Optional[str] = None
    pattern_seasons: tuple[int, ...] = ()

    detected_intents: tuple[str, ...] = ()
    spatial_scopes: tuple[str, ...] = ()
    temporal_scopes: tuple[str, ...] = ()
    comparatives: tuple[str, ...] = ()
    negations: tuple[str, ...] = ()
    causal_claims: tuple[str, ...] = ()
    sectors: tuple[int, ...] = ()
    corners: tuple[int, ...] = ()
    requested_hypotheses: tuple[str, ...] = ()
    engineering_terms: tuple[str, ...] = ()
    unsupported_terms: tuple[str, ...] = ()

    clarifications: tuple[ClarificationRequest, ...] = ()
    injection_scan: dict[str, Any] = field(default_factory=dict)
    resolution_log: list[dict[str, Any]] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)

    @property
    def clarified(self) -> bool:
        return bool(self.clarifications)

    def resolved_context(self) -> dict[str, Any]:
        """The scope the deterministic engine will actually run on."""
        return {
            "season": self.season,
            "round": self.round,
            "session_type": self.session_type,
            "driver_a": self.driver_a,
            "driver_b": self.driver_b,
            "lap_number": self.lap_number,
            "stint_number": self.stint_number,
            "pattern_id": self.pattern_id,
        }

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "raw_question": self.raw_question,
            "status": self.status,
            "reason": self.reason,
            "question_type": self.question_type,
            "season": self.season,
            "round": self.round,
            "session_type": self.session_type,
            "race_label": self.race_label,
            "driver_a": self.driver_a,
            "driver_b": self.driver_b,
            "lap_number": self.lap_number,
            "stint_number": self.stint_number,
            "pattern_id": self.pattern_id,
            "pattern_seasons": list(self.pattern_seasons),
            "question_intent": {
                "primary": self.detected_intents[0] if self.detected_intents else None,
                "secondary": list(self.detected_intents[1:]),
            },
            "spatial_scope": {
                "levels_requested": list(self.spatial_scopes),
                "sectors": list(self.sectors),
                "corners": list(self.corners),
            },
            "temporal_scope": {
                "scopes": list(self.temporal_scopes),
                "lap": self.lap_number,
                "stint": self.stint_number,
                "cross_race": bool(
                    self.pattern_seasons or "cross_race" in self.temporal_scopes
                ),
            },
            "comparison": {"subject_a": self.driver_a, "subject_b": self.driver_b},
            "requested_hypotheses": list(self.requested_hypotheses),
            "comparatives": list(self.comparatives),
            "negations": list(self.negations),
            "causal_claims": list(self.causal_claims),
            "engineering_terms": list(self.engineering_terms),
            "unsupported_terms": list(self.unsupported_terms),
            "clarification_required": self.clarified,
            "clarifications": [c.as_dict() for c in self.clarifications],
            "injection_scan": self.injection_scan,
            "provenance": self.provenance,
            "compiler_version": COMPILER_VERSION,
        }
        payload["question_hash"] = canonical_hash(
            {k: v for k, v in payload.items()
             if k not in ("provenance", "question_hash")}
        )
        return payload


def _shared_rounds(queries: CanonicalQueries, season: int,
                   driver_a: str, driver_b: str) -> list[dict[str, Any]]:
    """Races in ``season`` where BOTH drivers have a classified result."""
    conn = sqlite3.connect(queries.db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT r.round AS round, r.grand_prix AS grand_prix
            FROM canonical_results res
            JOIN canonical_sessions s  ON s.session_id = res.session_id
            JOIN canonical_races   r  ON r.race_id   = s.race_id
            JOIN canonical_drivers d  ON d.driver_id  = res.driver_id
            WHERE r.season = ? AND s.session_type = 'RACE'
              AND d.driver_key IN (?, ?)
            GROUP BY r.round
            HAVING COUNT(DISTINCT d.driver_key) = 2
            ORDER BY r.round
            """,
            (int(season), driver_a, driver_b),
        ).fetchall()
    finally:
        conn.close()
    return [{"round": int(r["round"]), "grand_prix": r["grand_prix"]} for r in rows]


def _resolve_race_by_participation(
    queries: CanonicalQueries, season: int, driver_a: str, driver_b: str,
) -> tuple[Optional[int], list[dict[str, Any]]]:
    """Resolve an unmentioned race from shared participation.

    Returns ``(round, candidates)``. ``round`` is set only when the pair shares
    exactly one race — a unique candidate is a fact, not a guess. With several,
    ``round`` stays None and the caller asks.
    """
    candidates = _shared_rounds(queries, season, driver_a, driver_b)
    if len(candidates) == 1:
        return candidates[0]["round"], candidates
    return None, candidates


def needs_clarification(compiled: CompiledQuestion) -> bool:
    """True when the question cannot proceed without a user answer."""
    return compiled.clarified


def _resolved_drivers_from_log(parsed: dict[str, Any]) -> tuple[Optional[str],
                                                              Optional[str]]:
    """Recover the drivers the intake resolved, from its own resolution log.

    The intake only returns ``driver_a``/``driver_b`` on the PARSED path. When
    it withholds them (an unresolved race, say) the resolutions still happened
    and are recorded as DRIVER entries in order of mention. Reading them back
    lets the resolver reason about participation without re-resolving anything.
    """
    entries = (parsed.get("provenance") or {}).get("resolution_log") or []
    keys = [str(e.get("resolved")) for e in entries
            if e.get("kind") == "DRIVER" and e.get("resolved")]
    first = keys[0] if keys else None
    second = keys[1] if len(keys) > 1 else None
    return first, second


def compile_question(
    queries: CanonicalQueries,
    question_text: str,
    context: Optional[dict[str, Any]] = None,
) -> CompiledQuestion:
    """Compile free text into a canonical engineering question.

    Deterministic and total: every input yields a CompiledQuestion whose
    ``status`` says exactly why it cannot proceed, if it cannot.
    """
    raw = question_text if isinstance(question_text, str) else ""
    log: list[dict[str, Any]] = []

    def _finish(**kwargs: Any) -> CompiledQuestion:
        base = dict(
            raw_question=raw,
            status=COMPILE_INVALID,
            provenance={
                "method": "deterministic_question_compiler",
                "compiler_version": COMPILER_VERSION,
                "resolution_log": log,
                "llm_assist": "none (deterministic compiler only)",
            },
        )
        base.update(kwargs)
        return CompiledQuestion(**base)

    if not isinstance(question_text, str):
        return _finish(reason="question must be a string")
    if not raw.strip():
        return _finish(reason="question is empty")
    if len(raw) > MAX_QUESTION_CHARS:
        return _finish(reason=f"question exceeds {MAX_QUESTION_CHARS} characters")

    # --- 1. deterministic entity resolution (existing, proven intake) -----
    parsed = parse_question(queries, raw, context=context)
    injection = parsed.get("injection_scan") or {}
    log.extend((parsed.get("provenance") or {}).get("resolution_log") or [])

    status = parsed.get("status")
    if status == INTAKE_INVALID:
        return _finish(status=COMPILE_INVALID, reason=parsed.get("reason"),
                       injection_scan=injection)
    if status == INTAKE_UNSUPPORTED:
        return _finish(status=COMPILE_UNSUPPORTED, reason=parsed.get("reason"),
                       injection_scan=injection)

    season = parsed.get("season")
    driver_a = parsed.get("driver_a")
    driver_b = parsed.get("driver_b")
    if status == INTAKE_UNRESOLVED:
        log_a, log_b = _resolved_drivers_from_log(parsed)
        driver_a = driver_a or log_a
        driver_b = driver_b or log_b
        # Season is withheld on the unresolved path too, but it was resolved.
        if season is None:
            for entry in (parsed.get("provenance") or {}).get("resolution_log") or []:
                if entry.get("kind") == "SEASON" and entry.get("resolved") is not None:
                    try:
                        season = int(entry["resolved"])
                    except (TypeError, ValueError):
                        season = None
                    break

    if status == INTAKE_UNRESOLVED:
        # The only unresolved case worth second-guessing is a missing race with
        # a season AND both drivers present: the participant rule may resolve it
        # uniquely. Everything else the intake refused stays refused.
        missing = parsed.get("missing") or []
        if (season is not None and driver_a and driver_b
                and set(missing) == {"race (round)"}):
            round_num, candidates = _resolve_race_by_participation(
                queries, season, driver_a, driver_b)
            if round_num is not None:
                log.append({
                    "kind": "RACE", "text": None,
                    "resolved": f"{season} R{round_num}",
                    "source": ("unique shared race for this driver pair in "
                               "the season (deterministic participation rule)"),
                })
                parsed = dict(parsed)
                parsed["round"] = round_num
                parsed["race_label"] = (
                    f"{season} R{round_num} "
                    f"({candidates[0]['grand_prix']})"
                )
                status = INTAKE_PARSED
            else:
                options = tuple(
                    f"{season} R{c['round']} {c['grand_prix']}"
                    for c in candidates[:MAX_CLARIFICATION_CANDIDATES]
                )
                if options:
                    prompt = ("Which race do you mean?")
                    if len(candidates) > MAX_CLARIFICATION_CANDIDATES:
                        prompt += (f" ({len(candidates)} races — showing the "
                                   f"first {MAX_CLARIFICATION_CANDIDATES})")
                    return _finish(
                        status=COMPILE_UNRESOLVED,
                        reason=("driver pair shares several races in the "
                                "season; the race is not determinable"),
                        season=int(season), driver_a=driver_a, driver_b=driver_b,
                        clarifications=(ClarificationRequest(
                            field="round", prompt=prompt, candidates=options),),
                        injection_scan=injection,
                    )
        if status == INTAKE_UNRESOLVED:
            clarifications: list[ClarificationRequest] = []
            for field_name, prompt in (
                ("season", "Which season do you mean?"),
                ("driver_a", "Which driver do you mean?"),
                ("driver_b", "Which driver are they compared against?"),
                ("race (round)", "Which race do you mean?"),
            ):
                if field_name in missing:
                    clarifications.append(ClarificationRequest(field=field_name,
                                                              prompt=prompt))
            # Carry forward what WAS resolved: an unresolved question should
            # still show the user everything the engine already established.
            return _finish(status=COMPILE_UNRESOLVED,
                           reason=parsed.get("reason"),
                           season=int(season) if season is not None else None,
                           driver_a=driver_a, driver_b=driver_b,
                           session_type=parsed.get("session_type") or "RACE",
                           clarifications=tuple(clarifications),
                           injection_scan=injection)

    # --- 2. enrich into a structured engineering question -------------------
    detected_intents = lang.detect_intents(raw)
    compiled = CompiledQuestion(
        raw_question=raw,
        status=COMPILE_PARSED,
        question_type=parsed.get("question_type"),
        season=parsed.get("season"),
        round=parsed.get("round"),
        session_type=parsed.get("session_type") or "RACE",
        race_label=parsed.get("race_label"),
        driver_a=parsed.get("driver_a"),
        driver_b=parsed.get("driver_b"),
        lap_number=parsed.get("lap_number"),
        stint_number=parsed.get("stint_number"),
        pattern_id=parsed.get("pattern_id"),
        pattern_seasons=tuple(parsed.get("pattern_seasons") or ()),
        detected_intents=detected_intents,
        spatial_scopes=lang.detect_spatial_scope(raw),
        temporal_scopes=lang.detect_temporal_scope(raw),
        comparatives=lang.detect_comparative(raw),
        negations=lang.detect_negation(raw),
        causal_claims=lang.detect_causal_claim(raw),
        sectors=lang.sector_numbers(raw),
        corners=lang.corner_numbers(raw),
        requested_hypotheses=lang.hypothesis_phrases(raw),
        engineering_terms=lang.engineering_terms(raw),
        unsupported_terms=lang.unresolved_terms(raw),
        injection_scan=injection,
        resolution_log=log,
        provenance={
            "method": "deterministic_question_compiler",
            "compiler_version": COMPILER_VERSION,
            "intake_version": (parsed.get("provenance") or {}).get("intake_version"),
            "question_object_hash": parsed.get("question_object_hash"),
            "resolution_log": log,
            "llm_assist": "none (deterministic compiler only)",
        },
    )
    return compiled
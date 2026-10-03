"""Race autopsy: the measurable events of a race, as a typed timeline.

This is a **curation layer**, not a new detector. Every event here is already
produced by the deterministic 6E-6S stack — ``performance_regimes`` emits
``change_points``, ``rejected_change_points``, ``context_transitions`` and a
merged ``race_timeline``; ``decompose_race_gap`` emits ``gap_events``. The
autopsy's job is to put those events in one timeline, label them, and record
where they came from.

That constraint is the whole design. A race autopsy that re-derives "important
moments" from raw laps would be a second, weaker, untested analyser producing
events nobody can trace. This one cannot invent a moment, because it only ever
relays what a registered capability already reported and records the producing
capability on each event.

Two honesty properties are load-bearing:

* **Rejected candidates are surfaced.** ``rejected_change_points`` are change
  candidates the engine examined and did not accept. They appear in the timeline
  as ``REJECTED_CANDIDATE`` events, so "we looked here and found nothing" is
  visible rather than absent.
* **Unmeasurable laps are declared.** ``unavailable_intervals`` become
  ``UNMEASURED_INTERVAL`` markers. A gap in the timeline is never rendered as an
  absence of events — it is rendered as an absence of measurement.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Optional

AUTOPSY_VERSION = "question_engine_autopsy_v1"

# Event vocabulary (§28). Closed: the autopsy may not invent an event type.
PERFORMANCE_SHIFT = "PERFORMANCE_SHIFT"
GAP_CHANGE = "GAP_CHANGE"
REGIME_CHANGE = "REGIME_CHANGE"
CONTEXT_TRANSITION = "CONTEXT_TRANSITION"
REJECTED_CANDIDATE = "REJECTED_CANDIDATE"
UNMEASURED_INTERVAL = "UNMEASURED_INTERVAL"
RESIDUAL_CHANGE = "RESIDUAL_CHANGE"
HYPOTHESIS_CHANGE = "HYPOTHESIS_CHANGE"

EVENT_TYPES = (
    PERFORMANCE_SHIFT, GAP_CHANGE, REGIME_CHANGE, CONTEXT_TRANSITION,
    REJECTED_CANDIDATE, UNMEASURED_INTERVAL, RESIDUAL_CHANGE, HYPOTHESIS_CHANGE,
)

# Materiality. A telemetry-availability change is a change in what we could
# *measure*, not a change in what the car did. Collapsing the two would let a
# measurement artefact masquerade as an engineering finding, which is exactly
# the failure this module exists to prevent.
ENGINEERING = "ENGINEERING"
MEASUREMENT = "MEASUREMENT"

# Context transitions that describe the world rather than our instrument.
# Anything not listed here (notably TELEMETRY_TRANSITION) is a measurement
# event: real, worth reporting, but not evidence about performance.
_MEASUREMENT_TRANSITIONS = frozenset({
    "TELEMETRY_TRANSITION", "TELEMETRY_EVIDENCE_CHANGE",
    "DATA_AVAILABILITY",
})


@dataclass
class EngineeringEvent:
    """One measurable event in a race, traceable to a producing capability."""

    event_id: str
    event_type: str
    lap_start: int
    lap_end: Optional[int]
    observed_change: str
    magnitude: Optional[float] = None
    unit: Optional[str] = None
    evidence_ids: tuple[str, ...] = ()
    hypotheses: tuple[str, ...] = ()
    context: dict[str, Any] = field(default_factory=dict)
    residual_s: Optional[float] = None
    source_capability: str = ""
    method: Optional[str] = None
    materiality: str = ENGINEERING
    limitations: tuple[str, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "lap_start": self.lap_start,
            "lap_end": self.lap_end,
            "observed_change": self.observed_change,
            "magnitude": self.magnitude,
            "unit": self.unit,
            "materiality": self.materiality,
            "evidence_ids": list(self.evidence_ids),
            "hypotheses": list(self.hypotheses),
            "context": self.context,
            "residual_s": self.residual_s,
            "source_capability": self.source_capability,
            "method": self.method,
            "limitations": list(self.limitations),
            "provenance": self.provenance,
        }


def _event_id(event_type: str, lap: int, salt: str) -> str:
    digest = hashlib.sha256(f"{event_type}|{lap}|{salt}".encode()).hexdigest()[:8]
    return f"EV-{lap:03d}-{digest}"


def _as_int(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def build_timeline(
    *,
    season: int,
    round_num: int,
    regimes: Optional[dict[str, Any]] = None,
    race_gap: Optional[dict[str, Any]] = None,
    residual_s: Optional[float] = None,
    residual_source: Optional[str] = None,
) -> dict[str, Any]:
    """Compose the autopsy timeline from real capability outputs.

    ``regimes`` is ``analyze_performance_regimes`` output; ``race_gap`` is
    ``decompose_race_gap`` output. Both are optional: a session missing one
    yields a timeline with fewer event types and says so, rather than failing.
    """
    events: list[EngineeringEvent] = []
    limitations: list[str] = []
    sources: list[str] = []
    unanchored: list[str] = []

    # ---- regime changes ---------------------------------------------------
    if isinstance(regimes, dict) and regimes.get("status") not in (
            "UNAVAILABLE", "INSUFFICIENT_EVIDENCE"):
        sources.append("analyze_performance_regimes")
        for point in regimes.get("change_points") or []:
            if not isinstance(point, dict):
                continue
            if str(point.get("detected", "")).upper() != "DETECTED":
                continue
            lap = _as_int(point.get("transition_lap") or
                          point.get("lap_number") or point.get("lap") or
                          point.get("at_lap"))
            if lap is None:
                continue
            previous = point.get("previous_pattern") or point.get("previous_state")
            new = point.get("new_pattern") or point.get("new_state")
            previous_slope = point.get("previous_slope_s_per_lap")
            new_slope = point.get("new_slope_s_per_lap")
            events.append(EngineeringEvent(
                event_id=_event_id(REGIME_CHANGE, lap, "regime"),
                event_type=REGIME_CHANGE,
                lap_start=lap,
                lap_end=None,
                observed_change=(
                    f"performance regime changed from {previous} to {new}"
                ),
                magnitude=(new_slope if isinstance(new_slope, (int, float))
                           else None),
                unit="s/lap",
                context={
                    "previous_pattern": previous,
                    "new_pattern": new,
                    "previous_slope_s_per_lap": previous_slope,
                    "new_slope_s_per_lap": new_slope,
                },
                source_capability="analyze_performance_regimes",
                method=point.get("trigger") or point.get("method"),
                hypotheses=_hypotheses_from_alignment(point.get("context_alignment")),
                provenance={"driver_scope": "analyze_performance_regimes",
                            "season": season, "round": round_num},
            ))

        # ---- rejected candidates: the autopsy's own falsification record ----
        for point in regimes.get("rejected_change_points") or []:
            if not isinstance(point, dict):
                continue
            lap = _as_int(point.get("transition_lap") or
                          point.get("lap_number") or point.get("lap"))
            if lap is None:
                continue
            events.append(EngineeringEvent(
                event_id=_event_id(REJECTED_CANDIDATE, lap, "rejected"),
                event_type=REJECTED_CANDIDATE,
                lap_start=lap,
                lap_end=None,
                observed_change=(
                    f"change candidate examined and not accepted: "
                    f"{point.get('reason') or point.get('reason_code') or 'below threshold'}"
                ),
                source_capability="analyze_performance_regimes",
                method=point.get("method"),
                provenance={"season": season, "round": round_num},
                limitations=("This candidate was rejected by the deterministic "
                             "gate; it is not an event.",),
            ))

        # ---- context transitions -------------------------------------------
        for transition in regimes.get("context_transitions") or []:
            if not isinstance(transition, dict):
                continue
            lap = _as_int(transition.get("lap_number"))
            if lap is None:
                continue
            kind = transition.get("type") or "CONTEXT_TRANSITION"
            is_measurement = str(kind).upper() in _MEASUREMENT_TRANSITIONS
            events.append(EngineeringEvent(
                event_id=_event_id(CONTEXT_TRANSITION, lap, str(kind)),
                event_type=CONTEXT_TRANSITION,
                lap_start=lap,
                lap_end=None,
                observed_change=(
                    f"{kind}: {transition.get('previous')} -> {transition.get('new')}"
                ),
                context={
                    "transition_type": kind,
                    "previous": transition.get("previous"),
                    "new": transition.get("new"),
                },
                materiality=MEASUREMENT if is_measurement else ENGINEERING,
                source_capability="analyze_performance_regimes",
                method=transition.get("methodology"),
                provenance={"season": season, "round": round_num},
                limitations=(
                    ("This is a change in measurement availability, not a "
                     "change in performance.",) if is_measurement else ()
                ),
            ))

        # ---- unmeasurable intervals ---------------------------------------
        for interval in regimes.get("unavailable_intervals") or []:
            if not isinstance(interval, dict):
                continue
            lap = _as_int(interval.get("lap_number") or
                          interval.get("transition_lap"))
            if lap is None:
                continue
            events.append(EngineeringEvent(
                event_id=_event_id(UNMEASURED_INTERVAL, lap, "unmeasured"),
                event_type=UNMEASURED_INTERVAL,
                lap_start=lap,
                lap_end=None,
                observed_change=(
                    f"lap not comparable: {interval.get('reason') or interval.get('status')}"
                ),
                context={"status": interval.get("status"),
                         "reason": interval.get("reason")},
                # A lap that could not be compared is a gap in our
                # measurement, not a change in the car. Leaving this on the
                # ENGINEERING default would let a pit lap read as a
                # performance event.
                materiality=MEASUREMENT,
                source_capability="analyze_performance_regimes",
                provenance={"season": season, "round": round_num},
                limitations=("No performance claim can be made about this lap; "
                             "its absence from the timeline is not evidence of "
                             "no change.",),
            ))
    else:
        limitations.append("regime analysis unavailable; no regime events reported")

    # ---- gap events -------------------------------------------------------
    if isinstance(race_gap, dict) and race_gap.get("status") not in (
            "UNAVAILABLE", "INSUFFICIENT_EVIDENCE"):
        sources.append("decompose_race_gap")
        for event in race_gap.get("gap_events") or []:
            if not isinstance(event, dict):
                continue
            kind = str(event.get("type") or "")
            lap = _as_int(event.get("at_lap") or event.get("lap_number"))
            if lap is None:
                # Not every gap event is lap-anchored (a session-wide telemetry
                # availability note has no lap). Recorded, never dropped.
                unanchored.append(kind)
                continue

            # Four real shapes: gap slope events carry state, a stint change
            # carries compound, a telemetry note carries only a detail string.
            if kind == "STINT_CHANGE":
                description = (
                    f"driver pit / compound change to stint "
                    f"{event.get('stint_number')} ({event.get('compound')})"
                )
                extra: dict[str, Any] = {
                    "stint_number": event.get("stint_number"),
                    "compound": event.get("compound"),
                }
                material = ENGINEERING
            elif kind == "TELEMETRY_EVIDENCE_CHANGE":
                description = f"telemetry evidence availability changed: {event.get('detail')}"
                extra = {"detail": event.get("detail")}
                material = MEASUREMENT
            else:
                description = (
                    f"gap rate change ({kind.replace('GAP_', '').replace('_', ' ').lower()}): "
                    f"{event.get('previous_state')} -> {event.get('new_state')}"
                )
                extra = {
                    "previous_state": event.get("previous_state"),
                    "new_state": event.get("new_state"),
                    "threshold_s_per_lap": event.get("threshold_s_per_lap"),
                }
                material = ENGINEERING

            events.append(EngineeringEvent(
                event_id=_event_id(GAP_CHANGE, lap, kind),
                event_type=GAP_CHANGE,
                lap_start=lap,
                lap_end=None,
                observed_change=description,
                magnitude=event.get("threshold_s_per_lap"),
                unit="s/lap",
                context={"gap_event_type": kind, **extra},
                materiality=material,
                source_capability="decompose_race_gap",
                method=event.get("method"),
                provenance={"season": season, "round": round_num},
                # The limitation must describe the event it sits on. A
                # telemetry-availability note labelled as a "gap slope change"
                # would misdescribe it to anyone reading the timeline.
                limitations=(
                    ("This is a change in measurement availability, not a "
                     "change in performance.",)
                    if material == MEASUREMENT else
                    ("A gap slope change is an observed rate change; it "
                     "is not attributed to any mechanism.",)
                ),
            ))
    else:
        limitations.append("race-gap decomposition unavailable; no gap events reported")

    # ---- residual as a first-class observation ---------------------------
    if isinstance(residual_s, (int, float)) and not isinstance(residual_s, bool):
        # A residual is a whole-race quantity. It is anchored to the first
        # regime's opening lap only so it has *a* position on an ordered
        # timeline; the event carries an explicit note saying it is not
        # attributable to that lap, because implying otherwise would invent
        # a location the calculation never established.
        first_regime = (regimes.get("regimes") or [{}])[0] \
            if isinstance(regimes, dict) else {}
        lap = _as_int(first_regime.get("lap_start")) or 1
        events.append(EngineeringEvent(
            event_id=_event_id(RESIDUAL_CHANGE, lap or 1, "residual"),
            event_type=RESIDUAL_CHANGE,
            lap_start=lap or 1,
            lap_end=None,
            observed_change=(
                f"{abs(residual_s):.3f} s of the observed difference remains "
                f"unexplained by the mechanisms tested"
            ),
            magnitude=abs(residual_s),
            unit="s",
            residual_s=residual_s,
            source_capability=residual_source or "attribute_lap_loss",
            provenance={"season": season, "round": round_num},
            limitations=("The residual is reported and never assigned to a "
                         "mechanism; it is not an error to be explained away.",
                         "This is a whole-race quantity shown from the first "
                         "regime's opening lap. It is not attributable to that "
                         "lap."),
        ))

    events.sort(key=lambda e: (e.lap_start, e.event_type, e.event_id))

    counted: dict[str, int] = {}
    material_count = 0
    for event in events:
        counted[event.event_type] = counted.get(event.event_type, 0) + 1
        if event.materiality == ENGINEERING:
            material_count += 1

    if unanchored:
        limitations.append(
            f"{len(unanchored)} gap event(s) carried no lap and are reported "
            f"without timeline position: {sorted(set(unanchored))}"
        )

    return {
        "analysis": "race_autopsy",
        "version": AUTOPSY_VERSION,
        "season": season,
        "round": round_num,
        "status": "COMPLETED" if events else "INSUFFICIENT_EVIDENCE",
        "events": [e.as_dict() for e in events],
        "event_count": len(events),
        "material_event_count": material_count,
        "events_by_type": dict(sorted(counted.items())),
        "source_capabilities": sorted(set(sources)),
        "unanchored_events": sorted(set(unanchored)),
        "limitations": limitations,
        "provenance": {
            "method": "curation over deterministic 6E-6S capability output",
            "no_event_is_invented": True,
            "materiality_rule": (
                "measurement-availability transitions are reported as "
                "MEASUREMENT, never as engineering events"
            ),
            "autopsy_version": AUTOPSY_VERSION,
        },
    }


def _hypotheses_from_alignment(alignment: Any) -> tuple[str, ...]:
    """Hypotheses an alignment mentions, if any."""
    if not isinstance(alignment, list):
        return ()
    found: list[str] = []
    for entry in alignment:
        if not isinstance(entry, dict):
            continue
        for key in ("hypotheses", "hypothesis_ids"):
            for hid in entry.get(key) or []:
                if isinstance(hid, str) and hid not in found:
                    found.append(hid)
    return tuple(found)
"""Engineering autopsy tests (§26).

The autopsy's entire value depends on one property: it curates events the
deterministic engine already reported and invents none. These tests assert that
property directly against real canonical data, plus the materiality split that
stops a telemetry-availability artefact from being read as an engineering
finding.

Tests here do two kinds of work:

* **Real-data tests** run the actual regime and gap analyses over a real race
  and assert the curation faithfully relays them. No event may appear that the
  engine did not produce, and no event may lack a source capability.
* **Fixture tests** drive :func:`build_timeline` with small hand-built engine
  payloads to pin edge behaviour (rejections, unavailable inputs, ordering)
  without needing a race that produces exactly that shape.
"""
from __future__ import annotations

import pytest

from racewise.data.historical.canonical_queries import CanonicalQueries
from racewise.question_engine.autopsy import (
    ENGINEERING,
    MEASUREMENT,
    build_timeline,
)

# A real race with real paired telemetry for both drivers.
REAL_SEASON = 2023
REAL_ROUND = 1
VER = "max-verstappen"
PER = "sergio-perez"


@pytest.fixture(scope="module")
def queries() -> CanonicalQueries:
    return CanonicalQueries()


@pytest.fixture(scope="module")
def real_sources(queries: CanonicalQueries) -> tuple[dict, dict]:
    """The two deterministic analyses the autopsy curates, on real data."""
    from racewise.data.historical.performance_regimes import (
        analyze_performance_regimes,
    )
    from racewise.data.historical.race_gap import decompose_race_gap

    regimes = analyze_performance_regimes(
        queries, REAL_SEASON, REAL_ROUND, VER, PER)
    gap = decompose_race_gap(queries, REAL_SEASON, REAL_ROUND, VER, PER)
    return regimes, gap


@pytest.fixture(scope="module")
def real_timeline(real_sources) -> dict:
    regimes, gap = real_sources
    return build_timeline(
        season=REAL_SEASON, round_num=REAL_ROUND,
        regimes=regimes, race_gap=gap,
    )


# ---------------------------------------------------------------------------
# nothing is invented
# ---------------------------------------------------------------------------

def test_timeline_produces_events_from_real_race(real_timeline):
    """A real race with real change points must yield a populated timeline."""
    assert real_timeline["event_count"] > 0
    assert len(real_timeline["events"]) == real_timeline["event_count"]


def test_every_event_carries_a_source_capability(real_timeline):
    """No event may exist without naming the capability that produced it."""
    for event in real_timeline["events"]:
        assert event.get("source_capability"), (
            f"event {event.get('event_id')} has no source_capability"
        )


def test_no_event_beyond_what_the_engine_reported(real_timeline, real_sources):
    """Event count is bounded by the engine's own output. Nothing is added.

    This is the anti-fabrication test. The autopsy may merge or reorder, but
    it may not manufacture an event that no source analysis contained.
    """
    regimes, gap = real_sources
    engine_supplied = (
        len(regimes.get("change_points") or [])
        + len(regimes.get("context_transitions") or [])
        + len(regimes.get("unavailable_intervals") or [])
        + len(gap.get("gap_events") or [])
    )
    assert engine_supplied > 0, "fixture race produced no engine events"
    assert real_timeline["event_count"] <= engine_supplied


def test_empty_input_yields_no_events():
    """An engine that reported nothing produces an empty timeline, not filler."""
    timeline = build_timeline(season=2023, round_num=1, regimes={}, race_gap={})
    assert timeline["event_count"] == 0
    assert timeline["events"] == []


def test_absent_sources_do_not_crash():
    """None for either source is a legitimate state, not an error."""
    timeline = build_timeline(season=2023, round_num=1,
                              regimes=None, race_gap=None)
    assert timeline["event_count"] == 0


def test_events_are_chronologically_ordered(real_timeline):
    """A timeline out of order is not a timeline."""
    laps = [e["lap_start"] for e in real_timeline["events"]]
    assert laps == sorted(laps)


def test_deterministic_across_calls(real_timeline, real_sources):
    """Same inputs, same events. No clocks, no randomness."""
    regimes, gap = real_sources
    again = build_timeline(season=REAL_SEASON, round_num=REAL_ROUND,
                           regimes=regimes, race_gap=gap)
    assert [e["event_id"] for e in again["events"]] == \
           [e["event_id"] for e in real_timeline["events"]]


# ---------------------------------------------------------------------------
# materiality: measurement noise must not masquerade as engineering (§26)
# ---------------------------------------------------------------------------

def test_telemetry_transitions_are_measurement_not_engineering(real_timeline):
    """The regression this module exists to prevent.

    A telemetry availability flip changes what we can *measure*, not what the
    car did. Presenting those as engineering events would inflate every
    race-wide summary with non-findings.
    """
    telemetry = [e for e in real_timeline["events"]
                 if e["event_type"] == "CONTEXT_TRANSITION"
                 and e["context"].get("transition_type") == "TELEMETRY_TRANSITION"]
    assert telemetry, "expected telemetry transitions in the fixture race"
    assert all(e["materiality"] == MEASUREMENT for e in telemetry), (
        "a telemetry transition was classified as an engineering event"
    )
    assert all("not a change in performance" in " ".join(e["limitations"])
               for e in telemetry)


def test_world_changing_context_transitions_stay_engineering(real_timeline):
    """A pit stop or compound change IS an engineering event.

    The materiality split is not "context is noise". A tyre change altered how
    the car behaved and must survive into the engineering timeline.
    """
    world = [e for e in real_timeline["events"]
             if e["event_type"] == "CONTEXT_TRANSITION"
             and e["context"].get("transition_type") in
             ("PIT_TRANSITION", "STINT_TRANSITION", "COMPOUND_CHANGE",
              "RACE_CONTROL_TRANSITION")]
    assert world, "expected pit/stint/compound transitions in the fixture race"
    assert all(e["materiality"] == ENGINEERING for e in world)


def test_unmeasured_intervals_are_measurement_not_engineering(real_timeline):
    """A lap that could not be compared is a gap, not a performance event.

    Classifying these as ENGINEERING would put a pit lap on the same footing
    as a real regime change and inflate the material-event count.
    """
    unmeasured = [e for e in real_timeline["events"]
                  if e["event_type"] == "UNMEASURED_INTERVAL"]
    assert unmeasured, "expected unmeasured intervals in the fixture race"
    assert all(e["materiality"] == MEASUREMENT for e in unmeasured)


def test_regime_and_gap_events_are_engineering(real_timeline):
    """Real performance changes are engineering events."""
    material = [e for e in real_timeline["events"]
                if e["event_type"] in ("REGIME_CHANGE", "GAP_CHANGE")]
    assert material, "expected regime/gap events in the fixture race"
    assert all(e["materiality"] == ENGINEERING for e in material)


def test_materiality_counts_reconcile(real_timeline):
    """The reported material count matches the events actually marked."""
    expected = sum(1 for e in real_timeline["events"]
                   if e["materiality"] == ENGINEERING)
    assert real_timeline["material_event_count"] == expected


def test_materiality_is_never_empty(real_timeline):
    for event in real_timeline["events"]:
        assert event["materiality"] in (ENGINEERING, MEASUREMENT)


# ---------------------------------------------------------------------------
# rejected candidates are reported, never silently dropped
# ---------------------------------------------------------------------------

def _change_point(lap: int) -> dict:
    return {
        "change_point_type": "GAP_TREND_CHANGE",
        "transition_lap": lap,
        # The engine marks an accepted candidate DETECTED. Without this the
        # point is a candidate that never cleared the gate, which the autopsy
        # correctly refuses to treat as a change.
        "detected": "DETECTED",
        "previous_regime": 1,
        "new_regime": 2,
        "previous_pattern": "NARROWING",
        "new_pattern": "STABLE",
    }


def test_rejected_candidates_are_surfaced():
    """A change point the engine rejected is a real negative result.

    The engine tested for it and decided it was not one. Reporting it keeps
    the investigation honest about what was ruled out.
    """
    timeline = build_timeline(
        season=2023, round_num=1,
        regimes={
            "status": "COMPLETED",
            "change_points": [_change_point(10)],
            "rejected_change_points": [
                {"transition_lap": 7, "detected": "REJECTED",
                 "reason": "below significance gate"},
            ],
        },
        race_gap={},
    )
    rejected = [e for e in timeline["events"]
                if e["event_type"] == "REJECTED_CANDIDATE"]
    assert len(rejected) == 1
    assert rejected[0]["lap_start"] == 7
    assert rejected[0]["observed_change"]


def test_regime_laps_use_transition_lap_not_lap_number():
    """Guards the field-name trap that silently zeroed every regime lap.

    The regime analysis anchors on ``transition_lap``. Reading ``lap_number``
    yields None, which quietly dropped every change point from the timeline.
    """
    timeline = build_timeline(
        season=2023, round_num=1,
        regimes={"status": "COMPLETED",
                 "change_points": [_change_point(23)]},
        race_gap={},
    )
    changes = [e for e in timeline["events"] if e["event_type"] == "REGIME_CHANGE"]
    assert len(changes) == 1
    assert changes[0]["lap_start"] == 23


# ---------------------------------------------------------------------------
# residuals are quoted, never computed
# ---------------------------------------------------------------------------

def test_residual_is_reported_not_derived():
    """A supplied residual appears with its source; none supplied means none."""
    with_residual = build_timeline(
        season=2023, round_num=1,
        regimes={"status": "COMPLETED", "change_points": [_change_point(5)]},
        race_gap={}, residual_s=0.128, residual_source="attribute_lap_loss")
    assert any(e["residual_s"] == 0.128 for e in with_residual["events"])

    without = build_timeline(
        season=2023, round_num=1,
        regimes={"status": "COMPLETED", "change_points": [_change_point(5)]},
        race_gap={})
    assert not any(e.get("residual_s") is not None for e in without["events"])


# ---------------------------------------------------------------------------
# provenance
# ---------------------------------------------------------------------------

def test_provenance_declares_no_invention(real_timeline):
    prov = real_timeline["provenance"]
    assert prov["no_event_is_invented"] is True
    assert prov["autopsy_version"]
    assert prov["materiality_rule"]


def test_limitations_are_lists_of_sentences_not_characters(real_timeline):
    """Regression: grouping parens made ``limitations`` a bare string.

    ``as_dict`` calls ``list(self.limitations)``, so a str field serialised as
    one character per element -- a limitation list arriving at the UI as 76
    single-character strings. Assert on shape, not on content.
    """
    for event in real_timeline["events"]:
        limits = event["limitations"]
        assert isinstance(limits, list), (
            f"{event['event_id']}: limitations is "
            f"{type(limits).__name__}, not a list"
        )
        for item in limits:
            assert isinstance(item, str)
            assert len(item) > 8, f"limitation split into a fragment: {item!r}"


def test_source_capabilities_are_real_function_names(real_timeline):
    """Sources must name actual deterministic analyses, not UI concepts."""
    for name in real_timeline["source_capabilities"]:
        assert name in (
            "analyze_performance_regimes", "decompose_race_gap",
        ), f"unknown source capability {name}"
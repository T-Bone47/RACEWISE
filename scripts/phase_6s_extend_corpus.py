"""Extend the Phase 6R benchmark corpus with 18 Phase 6S cases (EQ-L/M/N/O).

Run once; the corpus file is the durable artifact. Structural expectations
only - no numeric answer keys (asset-guarded).
"""
import json

PATH = "tests/benchmarks/engineering_questions.json"
data = json.load(open(PATH, encoding="utf-8"))
cases = data["cases"]
existing = {c["benchmark_id"] for c in cases}


def base(bid, cat, catname, q, **kw):
    c = {
        "benchmark_id": bid, "category": cat, "category_name": catname,
        "question": q,
        "question_type": kw.get("question_type", "LAP_PERFORMANCE"),
        "season": kw["season"], "round": kw["round"],
        "session_type": kw.get("session_type", "RACE"),
        "driver_a": kw["driver_a"], "driver_b": kw["driver_b"],
        "expected_status": kw.get("expected_status", ["VALID"]),
        "expected_conclusion_states": kw.get(
            "expected_conclusion_states",
            ["MIXED_EVIDENCE", "SUPPORTED_BY_AVAILABLE_EVIDENCE",
             "INSUFFICIENT_EVIDENCE"]),
        "evidence_rich": kw.get("evidence_rich", True),
        "required_provenance": ["provider", "source_tables", "method",
                                "analytical_chain", "investigation_version"],
        "counterfactual_expected": kw.get("counterfactual_expected",
                                          "INELIGIBLE_EXPLAINED"),
        "replay_expected": kw.get("replay_expected", True),
        "graph_trace_expected": kw.get("graph_trace_expected", False),
        "data_availability_expectation": kw.get(
            "data_availability_expectation", "FULL_TELEMETRY"),
        "limitation_case": kw.get("limitation_case", False),
        "validation_notes": kw["notes"],
    }
    if kw.get("lap_number"):
        c["lap_number"] = kw["lap_number"]
    if kw.get("stint_number"):
        c["stint_number"] = kw["stint_number"]
    if kw.get("memory_probe"):
        c["memory_probe"] = kw["memory_probe"]
    if kw.get("invalid_input"):
        c["invalid_input"] = kw["invalid_input"]
    return c


new = []

# ---- GAP 1: investigation-id-addressed graph (EQ-L, 4 cases) ----
new.append(base(
    "EQ-L01", "L", "GRAPH_BY_ID",
    "Address the lap-6 2023 Bahrain graph by its investigation id and "
    "verify it equals the scope-addressed graph.",
    season=2023, round=1, driver_a="max-verstappen",
    driver_b="sergio-perez", lap_number=6,
    memory_probe={"kind": "graph_by_id"},
    counterfactual_expected="NOT_REQUESTED",
    notes="GAP 1 positive: id-addressed graph must be identical (graph_id, "
          "node/edge ids) to the scope-addressed graph of the same "
          "investigation; addressing marker reported."))
new.append(base(
    "EQ-L02", "L", "GRAPH_BY_ID",
    "Attempt to address the lap-6 2023 Bahrain graph with a wrong "
    "investigation id.",
    season=2023, round=1, driver_a="max-verstappen",
    driver_b="sergio-perez", lap_number=6,
    memory_probe={"kind": "graph_by_id", "expect": "mismatch"},
    counterfactual_expected="NOT_REQUESTED",
    notes="GAP 1 negative: a wrong investigation id must 404 with an "
          "explicit reason and never fall back to a different "
          "investigation."))
l03 = base(
    "EQ-L03", "L", "GRAPH_BY_ID",
    "Request an investigation with an unknown question type (invalid-input "
    "control for the graph-addressing family).",
    season=2023, round=1, driver_a="max-verstappen",
    driver_b="sergio-perez", lap_number=6,
    question_type="FREE_FORM",
    memory_probe={"kind": "graph_by_id"},
    counterfactual_expected="NOT_REQUESTED",
    evidence_rich=False, replay_expected=False,
    notes="GAP 1 invalid-input control: an unknown question type is "
          "rejected by the engine with an explicit reason (INVALID; API "
          "422). The API-level id-without-scope rejection (422) is covered "
          "by the graph-by-id-without-scope API probe.")
l03["invalid_input"] = {"expect_status": "INVALID",
                        "reason": "question_type must be one of"}
new.append(l03)
new.append(base(
    "EQ-L04", "L", "GRAPH_BY_ID",
    "Replay the lap-6 2023 Bahrain investigation and trace its id-addressed "
    "graph through snapshot verification.",
    season=2023, round=1, driver_a="max-verstappen",
    driver_b="sergio-perez", lap_number=6,
    memory_probe={"kind": "graph_by_id"},
    graph_trace_expected=True,
    counterfactual_expected="ELIGIBLE_OR_EXPLAINED",
    notes="GAP 1 provenance/replay: the same investigation supports replay "
          "IDENTICAL, graph snapshot verify and graph replay IDENTICAL "
          "while being addressed by id."))

# ---- GAP 2: qualifying investigations (EQ-M, 5 cases) ----
new.append(base(
    "EQ-M01", "M", "QUALIFYING_LAP",
    "Where did Verstappen gain time over Perez on qualifying lap 2 of the "
    "2022 Emilia-Romagna GP, and which sectors explain it?",
    season=2022, round=4, session_type="QUALIFYING",
    driver_a="max-verstappen", driver_b="sergio-perez", lap_number=2,
    memory_probe={"kind": "qualifying_honesty"},
    notes="GAP 2 positive: qualifying single-lap comparison measured on "
          "canonical lap times and complete sector splits; "
          "telemetry-dependent hypotheses must remain honest at fusion "
          "level, fusion tool must be fuse_qualifying_lap_evidence, and "
          "attribute_lap_loss must NOT appear in the ledger."))
new.append(base(
    "EQ-M02", "M", "QUALIFYING_LAP",
    "Compare Verstappen and Perez on qualifying lap 3 of the 2023 Bahrain "
    "GP.",
    season=2023, round=1, session_type="QUALIFYING",
    driver_a="max-verstappen", driver_b="sergio-perez", lap_number=3,
    memory_probe={"kind": "qualifying_honesty"},
    notes="GAP 2 positive, second era: qualifying investigation with honest "
          "telemetry-hypothesis states; conclusion must be evidence-bound."))
m03 = base(
    "EQ-M03", "M", "QUALIFYING_LAP",
    "Compare Fagioli and Fangio in qualifying at the 1950 British GP.",
    season=1950, round=1, session_type="QUALIFYING",
    driver_a="luigi-fagioli", driver_b="juan-manuel-fangio", lap_number=1,
    expected_status=["UNAVAILABLE"],
    evidence_rich=False, replay_expected=False,
    data_availability_expectation="UNAVAILABLE",
    limitation_case=True,
    notes="GAP 2 limitation: canonical qualifying lap times begin in 2018; "
          "pre-2018 qualifying must report honest UNAVAILABLE with the "
          "coverage reason, never fabricated lap evidence.")
m03["expected_conclusion_states"] = ["UNAVAILABLE"]
new.append(m03)
m04 = base(
    "EQ-M04", "M", "QUALIFYING_LAP",
    "Request a stint-scoped investigation for a qualifying session.",
    season=2022, round=4, session_type="QUALIFYING",
    driver_a="max-verstappen", driver_b="sergio-perez",
    question_type="STINT_PERFORMANCE",
    expected_status=["INVALID"],
    evidence_rich=False, replay_expected=False,
    data_availability_expectation="UNAVAILABLE",
    notes="GAP 2 negative: stint numbers have no qualifying comparability "
          "semantics; the engine must reject with an explicit reason "
          "(INVALID; API 422).")
m04["expected_conclusion_states"] = ["UNAVAILABLE"]
m04["invalid_input"] = {"session_type": "QUALIFYING", "stint_number": 1,
                        "question_type": "STINT_PERFORMANCE",
                        "expect": "INVALID"}
new.append(m04)
new.append(base(
    "EQ-M05", "M", "QUALIFYING_LAP",
    "Replay the qualifying lap-2 2022 Emilia-Romagna investigation from its "
    "snapshot.",
    season=2022, round=4, session_type="QUALIFYING",
    driver_a="max-verstappen", driver_b="sergio-perez", lap_number=2,
    counterfactual_expected="ELIGIBLE_OR_EXPLAINED",
    notes="GAP 2 provenance/replay: a qualifying investigation snapshots "
          "and replays IDENTICAL through the same 6O machinery as race "
          "investigations."))

# ---- GAP 3: wider fused-lap coverage (EQ-N, 4 cases) ----
new.append(base(
    "EQ-N01", "N", "FUSED_LAP_COVERAGE",
    "Where did Verstappen lose time to Perez on lap 8 of the 2023 Bahrain "
    "GP?",
    season=2023, round=1, driver_a="max-verstappen",
    driver_b="sergio-perez", lap_number=8,
    counterfactual_expected="ELIGIBLE_OR_EXPLAINED",
    data_availability_expectation="PARTIAL",
    notes="GAP 3 positive: lap 8 was outside the 12-lap 6D probe set and "
          "must now reach a measured fused outcome (or remain honestly "
          "INSUFFICIENT if the lap is genuinely not comparable); any "
          "change is EXPECTED_CAPABILITY_EXTENSION."))
n02 = base(
    "EQ-N02", "N", "FUSED_LAP_COVERAGE",
    "Where did Verstappen lose time to Perez on lap 44 of the 2023 Bahrain "
    "GP?",
    season=2023, round=1, driver_a="max-verstappen",
    driver_b="sergio-perez", lap_number=44,
    expected_status=["VALID"],
    expected_conclusion_states=["INSUFFICIENT_EVIDENCE"],
    evidence_rich=False, replay_expected=False,
    data_availability_expectation="PARTIAL",
    limitation_case=True,
    notes="GAP 3 limitation: the 24-lap bound still leaves gaps (lap 44 is "
          "uncovered for both drivers even after the union of both "
          "drivers' picks); uncovered laps must keep reporting honest "
          "INSUFFICIENT_EVIDENCE with zero fabricated evidence and a "
          "TELEMETRY_UNAVAILABLE counterfactual candidate (the limitation "
          "shrinks, it does not disappear).")
new.append(n02)
new.append(base(
    "EQ-N03", "N", "FUSED_LAP_COVERAGE",
    "Assess counterfactual availability for a newly covered lap versus an "
    "uncovered lap.",
    season=2023, round=1, driver_a="max-verstappen",
    driver_b="sergio-perez", lap_number=8,
    counterfactual_expected="ELIGIBLE",
    data_availability_expectation="PARTIAL",
    notes="GAP 3 measured delta: the lap-8 counterfactual candidate must be "
          "ELIGIBLE (previously TELEMETRY_UNAVAILABLE under the 12-lap "
          "policy); candidates on still-uncovered laps (lap 44, EQ-N02) "
          "must report TELEMETRY_UNAVAILABLE."))
new.append(base(
    "EQ-N04", "N", "FUSED_LAP_COVERAGE",
    "Confirm additive identity: the previously covered lap-6 fused output "
    "is unchanged after the probe expansion.",
    season=2023, round=1, driver_a="max-verstappen",
    driver_b="sergio-perez", lap_number=6,
    counterfactual_expected="ELIGIBLE_OR_EXPLAINED",
    notes="GAP 3 additive regression: the 6R golden lap must remain "
          "byte-identical after the 12-to-24 expansion (upsert identity, "
          "no deletes)."))

# ---- GAP 4: related-memory retrieval (EQ-O, 5 cases) ----
new.append(base(
    "EQ-O01", "O", "RELATED_MEMORY",
    "Retrieve engineering memory for the lap-6 2023 Bahrain investigation "
    "with the default exact-scope contract.",
    season=2023, round=1, driver_a="max-verstappen",
    driver_b="sergio-perez", lap_number=6,
    memory_probe={"kind": "related_memory_api"},
    notes="GAP 4 default-identity regression: without include_related the "
          "response must be byte-identical to the Phase 6R contract (no "
          "related keys present)."))
new.append(base(
    "EQ-O02", "O", "RELATED_MEMORY",
    "Ask which structurally related prior investigations exist for the "
    "lap-6 2023 Bahrain scope.",
    season=2023, round=1, driver_a="max-verstappen",
    driver_b="sergio-perez", lap_number=6,
    memory_probe={"kind": "related_memory_api"},
    notes="GAP 4 positive: include_related must return structural matches "
          "with complete provenance, explicit match_reasons and the "
          "non-transfer policy; neighbor seasons contribute only VALID "
          "investigations."))
new.append(base(
    "EQ-O03", "O", "RELATED_MEMORY",
    "Verify zero structural leakage: a scope with no structural neighbors "
    "returns no related items.",
    season=2023, round=1, driver_a="max-verstappen",
    driver_b="sergio-perez", lap_number=6,
    memory_probe={"kind": "related_memory_probes",
                  "related_probe_pair": ["charles-leclerc",
                                         "carlos-sainz-jr"],
                  "expect_zero_related": True},
    notes="GAP 4 negative: structural matching against a disjoint driver "
          "pair must return zero related items (no leakage, no semantic "
          "drift)."))
new.append(base(
    "EQ-O04", "O", "RELATED_MEMORY",
    "Confirm invalidated memory items are excluded from structural "
    "retrieval unless explicitly included.",
    season=2023, round=1, driver_a="max-verstappen",
    driver_b="sergio-perez", lap_number=6,
    memory_probe={"kind": "related_memory_probes",
                  "related_invalidation_check": True},
    notes="GAP 4 invalidation: an item invalidated with REPLAY_MISMATCH "
          "must disappear from related results and reappear only with "
          "include_invalidated, mirroring the exact layer."))
new.append(base(
    "EQ-O05", "O", "RELATED_MEMORY",
    "Trace provenance on every structurally related memory item returned "
    "for the 2023 Bahrain lap-6 scope (2024 neighbor season in pool).",
    season=2023, round=1, driver_a="max-verstappen",
    driver_b="sergio-perez", lap_number=6,
    memory_probe={"kind": "related_memory_probes"},
    notes="GAP 4 provenance: every related pointer carries source "
          "investigation ids, evidence ids, source hashes, declared scope, "
          "match_class STRUCTURAL and match_reasons from the closed "
          "vocabulary; neighbor seasons contribute only VALID "
          "investigations' items."))

# Phase 6S measured-outcome updates to original 6R cases: gap 3's approved
# telemetry expansion converts some honest INSUFFICIENT_EVIDENCE lap cases
# into measured outcomes. Classified EXPECTED_CAPABILITY_EXTENSION (the
# structural checks still pass; only the conclusion-state expectation was
# coverage-bound).
MEASURED_UPDATES = {
    "EQ-A04": {
        "expected_conclusion_states": [
            "MIXED_EVIDENCE", "SUPPORTED_BY_AVAILABLE_EVIDENCE",
            "INSUFFICIENT_EVIDENCE"],
        "limitation_case": False,
        "data_availability_expectation": "PARTIAL",
        "validation_notes": (
            "Phase 6R measured INSUFFICIENT_EVIDENCE on this lap under the "
            "12-lap 6D probe policy. Phase 6S GAP 3 widened the coverage "
            "(12->24 laps/driver, 93 sessions re-ingested additively); this "
            "lap now reaches a measured fused outcome. Classified "
            "EXPECTED_CAPABILITY_EXTENSION: the improvement is exactly the "
            "capability the gap document promised, all structural checks "
            "still pass, and no numeric value is asserted."),
    },
}
for c in cases:
    if c["benchmark_id"] in MEASURED_UPDATES:
        c.update(MEASURED_UPDATES[c["benchmark_id"]])

added = [c for c in new if c["benchmark_id"] not in existing]
if added:
    cases.extend(added)
else:
    # idempotent re-run: refresh the EQ-N cases in place (measured lap
    # choices were finalized after the telemetry expansion completed)
    by_id = {c["benchmark_id"]: c for c in new}
    for c in cases:
        if c["benchmark_id"] in by_id:
            c.update(by_id[c["benchmark_id"]])
json.dump(data, open(PATH, "w", encoding="utf-8"), indent=2,
          ensure_ascii=False)
print("added:", len(added), "total:", len(cases))

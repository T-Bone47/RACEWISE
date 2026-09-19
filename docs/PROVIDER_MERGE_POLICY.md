# Provider Merge Policy

F1DB and FastF1 coexist in the same canonical store, distinguished by `source_provider` on every row. Nothing is silently overwritten.

## Precedence by domain

| Domain | Primary | Rationale |
|---|---|---|
| Race/session/results/qualifying identity & classification (all eras) | **F1DB** | Historical foundation of record; deterministic ids anchor every session |
| Pit stops 1994–present | **F1DB** (recorded stops) | Curated list with durations; FastF1 pit-in laps are a superset incl. non-timed entries |
| Per-lap engineering rows (2018+) | **FastF1** | F1DB has no lap-by-lap data; FastF1 lap rows carry compound/tyre-life/sectors |
| Tyre stints & compounds (2018+) | **FastF1** | Only provider with compound data |
| Weather (2018+) | **FastF1** | Only provider |
| Race control (2018+) | **FastF1** | Only provider |
| Channel telemetry | *deferred* | See FASTF1_MODERN_DATA.md |

## Coexistence rules

1. **Distinct identity.** Row ids are prefixed by provider inside the hash (`f1db:fastestlap:...` vs `fastf1:lap:...`), so both providers can describe the same lap without collision.
2. **No overwrites across providers.** FastF1 writes never UPDATE F1DB rows and vice versa; the `ON CONFLICT` targets are provider-scoped ids.
3. **F1DB never fabricates; FastF1 never backfills.** A 1950 session gets no weather row "estimated" from 2023 patterns; a 2023 session keeps F1DB classification even where FastF1's running order differs.
4. **Session identity is F1DB-only.** FastF1 rows attach to pre-existing canonical sessions or are skipped with a warning — FastF1 never creates sessions.

## Disagreement handling (verified examples)

Disagreements are surfaced by `CrossProviderValidator` / `FastF1CrossValidator` with both values preserved:

- **Finishing order vs running order** (2023 Australia): F1DB classification differs from FastF1's final running position under red-flag chaos (e.g. SAI 12 vs 4). Both preserved; classification remains authoritative for results, running order for on-track analysis.
- **Pit-stop counts**: FastF1 counts every pit-in lap (incl. non-timed entries like OCON's nose change, 2023 Bahrain); F1DB lists recorded timed stops only. Notes in the validator output state the semantic difference explicitly.
- **Lap counts**: FastF1 lap numbering can count extra laps differently (e.g. LEC, 2023 Bahrain). Preserved, never reconciled silently.

## Provenance columns (all modern rows)

`source_provider` (`fastf1`), `source_id` (event+entity reference), `source_version` (FastF1 library version), `created_at`/`updated_at`. F1DB rows carry the equivalent (`f1db`, source file row id, release version).

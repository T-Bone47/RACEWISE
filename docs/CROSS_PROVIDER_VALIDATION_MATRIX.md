# Cross-Provider Validation Matrix

Aggregate statistics across eras (measured 2026-09-19/20, Phase 6B). Comparisons use `CrossProviderValidator` (F1DB vs Jolpica cached responses) and `FastF1CrossValidator` (F1DB vs ingested FastF1 rows in the canonical store). Classification per field: MATCH / MISMATCH / NOT_AVAILABLE. **No winner is declared** — the goal is provenance and transparency; both values are preserved on every mismatch.

## Measured matrix

| Era | Race | Provider A | Provider B | MATCH | MISMATCH | NOT_AVAILABLE |
|---|---|---|---|---|---|---|
| 1950s | 1950 British GP | f1db | jolpica | 41 | 2 | 51 |
| 2010s | 2018 Australian GP | f1db | fastf1 | 8 | 0 | 0 |
| 2020s | 2020 Styrian GP | f1db | fastf1 | 1 | 6 | 1 |
| 2020s | 2021 British GP | f1db | fastf1 | 7 | 1 | 0 |
| 2020s | 2022 Bahrain GP | f1db | fastf1 | 6 | 2 | 0 |
| 2020s | 2023 Bahrain GP | f1db | fastf1 | 6 | 2 | 0 |
| 2020s | 2023 Saudi Arabian GP | f1db | fastf1 | 7 | 1 | 0 |
| 2020s | 2023 Australian GP | f1db | fastf1 | 4 | 4 | 0 |
| 2020s | 2024 Bahrain GP | f1db | fastf1 | 8 | 0 | 0 |
| 2020s | 2025 Australian GP | f1db | fastf1 | 6 | 2 | 0 |

Era-coverage note: Jolpica comparisons are bounded by cached responses (currently 1950 British GP); FastF1 comparisons are bounded by ingested sessions (2018–2025 canonical data now supports any modern round; the matrix above samples one race per season). Eras without a provider overlap (e.g. 1970s, 1990s vs Jolpica/FastF1) have no validator rows yet and are listed as future coverage, not as matches.

## Field-level mismatches preserved (both values retained in validator output)

| Race | Field | f1db | fastf1/jolpica | Semantic explanation (observed, not assumed) |
|---|---|---|---|---|
| 1950 British | circuit | `silverstone` | `Silverstone Circuit` | Identifier scheme vs display name; identity resolved via round/date |
| 1950 British | laps[18] | 24 | 26 | Real source disagreement about a historical classification detail |
| 2023 Bahrain | pit_stop_counts (OCON) | 3 | 4 | FastF1 counts every pit-in lap (incl. non-timed entries); F1DB lists recorded timed stops |
| 2023 Bahrain | laps[LEC] | 57 | 58 | Lap-numbering of extra laps differs between sources |
| 2023 Saudi Arabia | pit_stop_counts (ALB) | 1 | 2 | Same pit-in-lap vs recorded-stop semantics |
| 2023 Australia | finishing_positions (12 drivers) | classification order | final running order | Red-flag classification vs on-track running order |
| 2020 Styria | laps (all classified drivers) | N | N−4 (systematic) | FastF1 2020 lap numbering runs 4 lower than F1DB for every driver — systematic provider difference in this season, not per-driver noise. Hypothesis (unverified): differing treatment of formation/restart laps. Both values retained. |
| 2021 Britain | pit_stop_counts | divergent | divergent | Recorded stops vs pit-in-lap counting across multiple drivers |
| 2022 Bahrain | finishing_positions | classification | running order | Two drivers differ between classification and final running order |
| 2025 Australia | laps[Sainz] | 0 | 1 | DNS treatment differs between sources |
| 2025 Australia | laps[Alonso] | 32 | 33 | Off-by-one lap-count convention on classified laps |

## Resolution policy

F1DB is the historical foundation of record for identity and classification. FastF1 is primary for engineering signals (compounds, stints, weather, race control). Jolpica is a second opinion. Disagreements are surfaced with both values and a note; the canonical store is never auto-patched from a secondary provider.

## Aggregate statistics

- Total comparisons measured: 94 (Jolpica 1950) + FastF1 modern matrix (2018–2025, one race per season + 2023 full triples)
- FastF1 modern totals (6 sampled rounds this refresh): MATCH 36 · MISMATCH 11 · NOT_AVAILABLE 1
- Jolpica 1950: MATCH 41 · MISMATCH 2 · NOT_AVAILABLE 51
- NOT_AVAILABLE is dominated by fields one provider simply does not carry (e.g. Jolpica has no tyre/compound data)
- MISMATCH rate on overlapping modern fields ≈ 23%; every mismatch preserves both provider values

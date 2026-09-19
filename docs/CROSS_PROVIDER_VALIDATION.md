# Cross-Provider Validation

Verified result for Phase 5.5B (2026-09-19).

## Scope

Providers compared: **F1DB** (canonical store, v2026.14.0) vs **Jolpica** (cached responses under `data/raw/jolpica/`). Overlapping cached coverage currently includes the 1950 British GP.

## Method

`src/racewise/data/historical/cross_provider.py` compares overlapping fields (race identity, circuit, date, per-driver finishing order, laps) and classifies each comparison as `MATCH`, `MISMATCH`, or `NOT_AVAILABLE`. Nothing is forced to agree.

## 1950 British GP — actual result

- Total field comparisons: **94**
- MATCH: **41**
- NOT_AVAILABLE: **51** (fields one provider simply does not carry)
- MISMATCH: **2**

### Mismatches (both values preserved)

1. **circuit** — F1DB `silverstone` (identifier scheme) vs Jolpica `Silverstone Circuit` (display name). Identity is resolved via round/date; this is a scheme difference, not a factual conflict.
2. **laps[18]** — F1DB records 24 laps for one driver; Jolpica records 26. This is a real source disagreement about a historical classification detail.

## Resolution policy

F1DB is the historical foundation of record. Discrepancies are **surfaced, never silently merged or overwritten**; both provider values are retained in the validation output (`mismatches` list includes both values and a note). A future human/agent review can adjudicate; the canonical store itself is not auto-patched from secondary providers.

## Extending coverage

Jolpica ingestion (`jolpica_ingest.py`, with rate-limit/backoff hardening) can populate more cached seasons; the validator then compares any race where both providers have data. FastF1 is compared separately through golden investigation 2023 (session load + lap/pit context), because its data model is telemetry-shaped rather than classification-shaped.

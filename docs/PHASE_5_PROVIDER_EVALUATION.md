# RACEWISE Phase 5 Provider Evaluation Report

**Date:** September 18, 2026  
**Scope:** Multi-source F1 data provider evaluation  
**Providers Evaluated:** FastF1 (Primary), API-Sports F1, F1 API (f1api.dev), F1 Live Pulse (RapidAPI)

---

## Executive Summary

Evaluated 4 F1 data providers against the 2023 Bahrain Grand Prix reference session. **FastF1 remains the primary historical provider** with the most comprehensive data coverage. **F1 API (f1api.dev) provides supplementary metadata** (circuits, teams, drivers, basic race results) but lacks detailed timing data. **API-Sports Formula 1** and **F1 Live Pulse** endpoints are unavailable with current subscriptions.

| Provider | Status | Historical Data | Live Data | Verdict |
|----------|--------|-----------------|-----------|---------|
| FastF1 | ✅ PRIMARY | Complete (laps, pits, stints, weather, RC) | ❌ | Keep |
| F1 API (f1api.dev) | ✅ SECONDARY | Metadata + basic results | ❌ | Keep |
| API-Sports F1 | ❌ NOT_USEFUL | Unavailable (wrong subscription) | ❌ | Drop |
| F1 Live Pulse | ❌ NOT_USEFUL | Unavailable (endpoint mismatch) | ❌ | Drop |

---

## Provider Architecture

```
Union Alpha (Host Agent)
         ↓
RACEWISE MCP Server
         ↓
    Tool Registry
         ↓
┌───────┴───────┐
▼               ▼
FastF1      Provider Adapters
             ├─ API-Sports F1
             ├─ F1 API (f1api.dev)
             └─ F1 Live Pulse
```

All providers implement the same canonical interface, normalizing to RACEWISE domain schemas before data reaches the analytics layer.

---

## Provider Evaluations

### 1. FastF1 (PRIMARY) ✅
**Status:** Fully operational, primary historical provider

**Capabilities Verified (2023 Bahrain GP):**
- ✅ Session metadata (event, circuit, date, 20 drivers)
- ✅ 1056 total laps, 57 VER laps with full timing
- ✅ 2 VER pit stops (Lap 14: SOFT→SOFT, Lap 36: SOFT→HARD)
- ✅ 3 VER stints (SOFT 1-14, SOFT 15-36, HARD 37-57)
- ✅ 161 weather records, 73 race control events
- ✅ Complete stint/tire/lap/timing data

**Coverage:** 2018-present, all sessions
**Latency:** ~30s cold, ~5s cached
**Reliability:** High (local cache)

---

### 2. F1 API / f1api.dev (SECONDARY) ✅
**Status:** Connected, metadata + basic results only

**Capabilities Verified (2023 Bahrain GP):**
- ✅ 30 seasons (2018-2026)
- ✅ 30 circuits with metadata (length, corners, records)
- ✅ 30 teams (historical + current)
- ✅ 30 drivers (historical + current)
- ✅ Race results: 20 finishers with positions, points, grid, times
- ❌ Qualifying results (not in race response)
- ❌ Lap timing data (404)
- ❌ Pit stops (404)
- ❌ Weather (404)
- ❌ Starting grid (404)
- ❌ Fastest laps (404)
- ❌ Race control (404)
- ❌ Track status (404)

**Data Structure:** Results embedded in race response (`/api/{year}/{round}/race` → `races.results`)
**Latency:** ~500ms per request
**Authentication:** None required
**Rate Limits:** Unknown

**Value Add:** Supplementary metadata (circuits, teams, drivers) + basic race results for cross-validation

---

### 3. API-Sports Formula 1 (NOT_USEFUL) ❌
**Status:** Endpoint unavailable with current subscription

**Tested Endpoint:** `https://v1.formula-1.api-sports.io`
**Authentication:** Valid API key (`x-apisports-key`)
**Error:** `{"endpoint": "This endpoint do not exist."}` for all F1 endpoints

**Root Cause:** Current API-Sports subscription is for Football/Soccer only. Formula 1 is a separate product requiring separate subscription.

**Endpoints Tested (all unavailable):**
- `/seasons` → endpoint error
- `/races` → endpoint error  
- `/results` → endpoint error
- `/qualifying` → endpoint error
- `/pitstops` → endpoint error
- `/laps` → endpoint error
- `/weather` → endpoint error
- `/standings` → endpoint error

**DNS:** `v3.football.api-sports.io` works (football), `v1.formula-1.api-sports.io` resolves but requires F1 subscription

**Recommendation:** Drop unless F1 subscription acquired

---

### 4. F1 Live Pulse / RapidAPI (NOT_USEFUL) ❌
**Status:** Endpoint unavailable with current subscription

**Tested Host:** `f1-live-pulse.p.rapidapi.com`
**Base URL:** `https://f1-live-pulse.p.rapidapi.com`
**Authentication:** RapidAPI key + host headers

**Endpoints Tested (all 404):**
- `/schedule`, `/schedule/2023`
- `/drivers/2023`, `/teams/2023`, `/standings/2023`
- `/results/2023/1`, `/qualifying/2023/1`
- `/pit-stops/2023/1`, `/laps/2023/1`
- `/weather/2023/1`
- Various API version patterns (`/api/`, `/v1/`, etc.)

**Root Cause:** Endpoint paths don't match RapidAPI listing, or subscription doesn't include F1 data

**Recommendation:** Drop unless correct endpoints/keys verified

---

## Cross-Provider Comparison (2023 Bahrain GP)

| Data Point | FastF1 | F1 API | Agreement |
|------------|--------|--------|-----------|
| Event Name | Bahrain Grand Prix | Bahrain Grand Prix | ✅ MATCH |
| Date | 2023-03-05 | 2023-03-05 | ✅ MATCH |
| Circuit | Sakhir | Bahrain International Circuit | ✅ MATCH (same) |
| Total Laps | 57 | 57 | ✅ MATCH |
| Winner | VER | VER (position 1) | ✅ MATCH |
| Podium | VER, PER, ALO | VER, PER, ALO | ✅ MATCH |
| VER Laps | 57 | 1 (result only) | N/A |
| VER Pit Stops | 2 (L14, L36) | N/A | N/A |
| Weather Records | 161 | N/A | N/A |
| Race Control | 73 events | N/A | N/A |

**No discrepancies found** in overlapping data fields.

---

## Provider Capability Matrix

| Capability | FastF1 | F1 API | API-Sports | F1 Live Pulse |
|------------|--------|--------|------------|---------------|
| Session metadata | ✅ | ✅ | ❌ | ❌ |
| Drivers list | ✅ | ✅ | ❌ | ❌ |
| Teams list | ✅ | ✅ | ❌ | ❌ |
| Circuits list | ✅ | ✅ | ❌ | ❌ |
| Race results | ✅ | ✅ | ❌ | ❌ |
| Qualifying results | ✅ | ❌ | ❌ | ❌ |
| Lap times | ✅ | ❌ | ❌ | ❌ |
| Sector times | ✅ | ❌ | ❌ | ❌ |
| Pit stops | ✅ | ❌ | ❌ | ❌ |
| Tyre/stint data | ✅ | ❌ | ❌ | ❌ |
| Weather | ✅ | ❌ | ❌ | ❌ |
| Race control | ✅ | ❌ | ❌ | ❌ |
| Track status | ✅ | ❌ | ❌ | ❌ |
| Starting grid | ✅ | ❌ | ❌ | ❌ |
| Fastest laps | ✅ | ❌ | ❌ | ❌ |
| Lap timing detail | ✅ | ❌ | ❌ | ❌ |
| Sector detail | ✅ | ❌ | ❌ | ❌ |
| Telemetry | ❌ | ❌ | ❌ | ❌ |
| Historical seasons | 2018+ | 2018+ | ❌ | ❌ |
| Live/real-time | ❌ | ❌ | ❌ | ? |
| Latency (cached) | ~5s | ~500ms | N/A | N/A |
| Rate limits | None | Unknown | N/A | N/A |
| Authentication | None | None | API Key | RapidAPI Key |

---

## Bahrain 2023 Cross-Provider Data Comparison

| Field | FastF1 | F1 API | Classification |
|-------|--------|--------|----------------|
| Event name | Bahrain Grand Prix | Bahrain Grand Prix | MATCH |
| Session type | Race | Race | MATCH |
| Date | 2023-03-05 15:00:00 | 2023-03-05 | MATCH |
| Circuit | Sakhir | Bahrain International Circuit | MATCH |
| Total laps | 57 | 57 | MATCH |
| Drivers count | 20 | 20 (results) | MATCH |
| Winner | VER | VER (pos 1) | MATCH |
| VER position | 1 | 1 | MATCH |
| VER team | Red Bull Racing | Red Bull Racing | MATCH |
| VER time | 1:33:56.736 | 1:33:56.736 | MATCH |
| PER position | 2 | 2 | MATCH |
| ALO position | 3 | 3 | MATCH |

**No discrepancies found** in any overlapping fields.

---

## Provider Dispositions

| Provider | Disposition | Rationale |
|----------|-------------|-----------|
| FastF1 | **PRIMARY** | Complete historical data, reliable, cached, free |
| F1 API (f1api.dev) | **SECONDARY** | Metadata + results for cross-validation, free, no key needed |
| API-Sports F1 | **NOT_USEFUL** | F1 endpoint not in current subscription (football only) |
| F1 Live Pulse | **NOT_USEFUL** | Endpoints not found with current RapidAPI key |

---

## Provenance Tracking

All provider adapters implement canonical provenance fields:

```python
{
    "provider": "fastf1|f1api|api_sports|f1livepulse",
    "provider_version": "...",
    "endpoint": "/api/2023/1/race",
    "request_parameters": {"year": 2023, "round": 1},
    "retrieval_timestamp": "2026-09-18T...",
    "source_identifier": "race_2023_1",
    "normalization_version": "1.0.0",
    "raw_response_hash": "sha256:...",
    "canonical_record_hash": "sha256:..."
}
```

**No secrets in provenance.** API keys never logged or stored in event log.

---

## Security Assessment

| Aspect | Status | Notes |
|--------|--------|-------|
| API key exposure | ✅ None | Keys only in env, never logged |
| Secret in logs | ✅ None | Sanitized in all adapters |
| Git commits | ✅ Clean | Keys only in .env (gitignored) |
| Frontend exposure | ✅ None | Backend-only provider calls |
| Rate limiting | ⚠️ Unknown | F1 API limits unknown |
| Failover | ✅ Graceful | Unavailable providers return clear errors |

---

## Test Results

```
101 tests passed (86 unit + 14 integration + 1 benchmark)
Frontend lint: 0 warnings, 0 errors
Frontend build: SUCCESS
Backend: All integration tests pass
```

---

## Final Recommendations

### Immediate Actions
1. **Keep FastF1 as PRIMARY** - No changes needed
2. **Keep F1 API as SECONDARY** - Use for metadata cross-validation
3. **Remove API-Sports F1** - Wrong subscription, not usable for F1
4. **Remove F1 Live Pulse** - Endpoints not accessible with current key

### Future Enhancements (If Needed)
- Acquire API-Sports Formula 1 subscription if pit stop/lap data needed
- Evaluate F1 Live Pulse with correct RapidAPI subscription
- Implement capability-based provider selection in registry

---

## Conclusion

**Phase 5 multi-provider evaluation complete.** FastF1 remains the undisputed primary provider for historical F1 data. F1 API (f1api.dev) adds value as a free, keyless secondary source for metadata and basic race results cross-validation. The other two experimental providers are not usable with current subscriptions.

**RACEWISE remains a single-source-of-truth system** with FastF1 as the authoritative source, augmented by optional cross-validation from F1 API where both provide data.

---

*Report generated: 2026-09-18*  
*Phase 5 Provider Expansion Evaluation Complete*
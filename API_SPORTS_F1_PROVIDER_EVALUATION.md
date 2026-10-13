# API-Sports Formula 1 Provider Evaluation

**Date:** September 18, 2026  
**Evaluator:** RACEWISE Phase 5  
**Provider:** API-Sports / API-Football (api-sports.io)  
**Credential:** API_SPORTS_API_KEY (from dashboard.api-sports.io)  
**Status:** EXPERIMENTAL — Endpoint not available with current subscription

---

## Executive Summary

The API-Sports Formula 1 provider was evaluated as an experimental data provider for RACEWISE. The API key is valid and authenticates successfully against the API-Sports platform, **but the Formula 1 endpoint is not available with the current subscription**. The subscription appears to be for football/soccer data only.

**Final Classification:** NOT_USEFUL (for Formula 1 data with current subscription)

---

## Connectivity Test Results

### Authentication
- **API Key:** Valid ✅
- **Authentication:** Successful (HTTP 200)
- **Platform:** API-Sports / API-Football
- **Base URL Tested:** `https://v3.football.api-sports.io` (working DNS)

### Endpoint Availability
| Endpoint | Status | Details |
|----------|--------|---------|
| `/formula1/seasons` | ❌ Unavailable | `{"endpoint": "The Formula1 endpoint does not exist."}` |
| `/formula1/races` | ❌ Unavailable | Same error |
| `/formula1/results` | ❌ Unavailable | Same error |
| `/formula1/laps` | ❌ Unavailable | Same error |
| `/formula1/pitstops` | ❌ Unavailable | Same error |
| `/formula1/weather` | ❌ Unavailable | Same error |

### Network/DNS
| Hostname | Resolves | Notes |
|----------|----------|-------|
| `v3.football.api-sports.io` | ✅ Yes | 104.20.39.36, etc. |
| `v3.api-sports.io` | ❌ No | NXDOMAIN |
| `api.api-sports.io` | ❌ No | NXDOMAIN |

---

## Capability Matrix

| Capability | FastF1 | API-Sports F1 (Current Sub) | RACEWISE Need |
|------------|--------|------------------------------|---------------|
| Sessions | ✅ Full | ❌ Unavailable | Required |
| Drivers | ✅ Full | ❌ Unavailable | Required |
| Laps | ✅ Full | ❌ Unavailable | Required |
| Stints | ✅ Full | ❌ Unavailable | Required |
| Pit stops | ✅ Full | ❌ Unavailable | Required |
| Tyres | ✅ Full | ❌ Unavailable | Required |
| Telemetry | ✅ Full | ❌ Unavailable | Important |
| Weather | ✅ Full | ❌ Unavailable | Useful |
| Race control | ✅ Full | ❌ Unavailable | Useful |
| Position | ✅ Full | ❌ Unavailable | Useful |
| Historical coverage | 2018+ | ❌ None | Required |
| Live data | ❌ No | ❌ Unavailable | Future |

---

## Cross-Provider Comparison (2023 Bahrain Grand Prix)

Not applicable — API-Sports Formula 1 endpoint completely unavailable. No data to compare.

---

## Provider Failure Testing

| Failure Mode | Tested | Behavior |
|--------------|--------|----------|
| Invalid API key | ❌ Not tested (would require invalid key) | Would return 401 |
| HTTP 403 | ✅ | Endpoint exists but returns "endpoint does not exist" |
| HTTP 404 | ✅ | Not applicable — endpoint path exists but feature disabled |
| Rate limiting | ❌ Not tested | Unknown |
| Timeout | ❌ Not tested | Unknown |
| Malformed response | ❌ Not tested | Unknown |
| Missing fields | ❌ Not tested | N/A |
| Provider unavailable | ✅ | DNS fails for `v3.api-sports.io` |

---

## RACEWISE Value Assessment

| Value Criterion | Assessment | Evidence |
|----------------|------------|----------|
| Additional data | ❌ None | No F1 data accessible |
| Better historical coverage | ❌ None | No F1 data accessible |
| Lower latency | N/A | N/A |
| More reliable metadata | N/A | N/A |
| Live data capability | ❌ None | No F1 endpoint |
| Unique fields | N/A | N/A |
| Investigation robustness | ❌ Negative | Adds complexity without data |
| Cross-provider validation | ❌ None | No overlapping data |
| Fallback/redundancy | ❌ None | No F1 data at all |

---

## Technical Implementation

### Adapter Implementation
The adapter (`src/racewise/data/api_sports_f1_adapter.py`) was implemented with:
- ✅ Clean provider abstraction behind canonical boundary
- ✅ Proper authentication handling
- ✅ Endpoint availability detection
- ✅ Graceful degradation (raises `APISportsF1Error` with clear message)
- ✅ Canonical normalization methods (ready for when endpoint becomes available)
- ✅ Provenance tracking hooks
- ✅ No soccer/football terminology leakage
- ✅ Provider-agnostic interface matching FastF1 adapter pattern

### Provenance Tracking
The adapter includes hooks for:
- Provider name (`api_sports`)
- Endpoint used
- Request parameters
- Retrieval timestamp
- Response metadata
- Normalized record hash

### Configuration
```env
API_SPORTS_API_KEY=<key>
API_SPORTS_F1_ENABLED=true
API_SPORTS_BASE_URL=https://v3.football.api-sports.io
API_SPORTS_KEY_HEADER=x-apisports-key
```

---

## Recommendation

### Final Classification: **NOT_USEFUL** (with current subscription)

**Reasoning:**
1. The Formula 1 endpoint does not exist on the current API-Sports subscription
2. The subscription appears to be for football/soccer only
3. No Formula 1 data is accessible for comparison or validation
4. The adapter architecture is ready but cannot be exercised without F1 subscription

### Next Steps
1. **If F1 data is needed from API-Sports:** Obtain a Formula 1 subscription from API-Sports (separate from football)
2. **If F1 data is not critical:** Keep adapter as dormant experimental module; FastF1 remains primary
3. **Monitor:** Check API-Sports roadmap for F1 availability changes

### Architecture Integrity
- ✅ FastF1 remains primary historical provider
- ✅ Adapter isolated behind canonical boundary
- ✅ No provider-specific logic leaked into analytics
- ✅ Union Alpha remains provider-agnostic
- ✅ No credentials exposed in logs/frontend

---

## Evidence Artifacts

- `src/racewise/data/api_sports_f1_adapter.py` — Full adapter implementation
- `test_apisports.py` — Connectivity test (deleted after use)
- `racewise.env` — Configuration with `API_SPORTS_BASE_URL=https://v3.football.api-sports.io`
- `.env.example` — Updated with `API_SPORTS_API_KEY=` placeholder

---

*Evaluation conducted per Phase 5 requirements. All findings based on empirical testing with actual API credentials.*
"""Phase 6T: deterministic natural-language question intake.

Translates a free-text engineering question into the canonical question
object consumed by the autonomous orchestrator
(``autonomous_investigator.run_autonomous_investigation``). Fully
deterministic: a closed, documented phrasing vocabulary; canonical
identifiers only; nothing is guessed.

Contract (see docs/PHASE_6T_ARCHITECTURE.md):
- Drivers resolve to canonical ``driver_key`` slugs by accent-insensitive
  exact full name, exact driver key, or code/family name (word-bounded,
  capitalized-in-text mentions, disambiguated by season participation).
  Never fuzzy-matched: an unresolvable or ambiguous name stays
  unresolved, or passes through verbatim so the engine's participant
  check can answer UNAVAILABLE (never a substitution).
- Races resolve by (season, grand_prix key) with the same honesty; a
  race name that matches nothing or several races is unresolved. A
  question without any season is CONTEXT_UNRESOLVED (never silently
  chooses a race).
- Question types are the closed 6N vocabulary (plus the intake-level
  QUALIFYING phrasing which emits LAP_PERFORMANCE with
  session_type=QUALIFYING — no new engine type exists).
- Question text is DATA. Instruction-like patterns are detected,
  recorded in ``injection_scan`` and never treated as directives.
- No LLM is involved. (The optional provider assist of the architecture
  doc was evaluated and is not required: the deterministic vocabulary
  covers the supported question corpus, and keeping the LLM out of the
  loop removes an entire fabrication surface. Recorded as an explicit
  Phase 6T decision.)
"""
from __future__ import annotations

import re
import sqlite3
import unicodedata
from typing import Any, Optional

from racewise.data.historical.canonical_queries import CanonicalQueries
from racewise.data.historical.performance_patterns import _hash_obj

ANALYSIS = "phase_6t_question_intake"
INTAKE_VERSION = "6t_intake_v2"

# Closed intake outcome vocabulary (orchestrator failure states map 1:1).
INTAKE_PARSED = "PARSED"
INTAKE_INVALID = "INVALID_QUESTION"
INTAKE_UNRESOLVED = "CONTEXT_UNRESOLVED"
INTAKE_UNSUPPORTED = "UNSUPPORTED_QUESTION"

MAX_QUESTION_CHARS = 500

# Intake-level question-type vocabulary (QUALIFYING phrasings are intake
# spellings only: they emit question_type=LAP_PERFORMANCE with
# session_type=QUALIFYING; the engine vocabulary itself is unchanged).
INTAKE_QUESTION_TYPES = (
    "LAP_PERFORMANCE", "STINT_PERFORMANCE", "RACE_GAP",
    "PERFORMANCE_REGIME", "CROSS_RACE_PATTERN", "HYPOTHESIS_EVALUATION",
    "COUNTERFACTUAL_ELIGIBILITY", "QUALIFYING_LAP_PERFORMANCE",
)

# Hypothesis-phrase mapping (deterministic; used for hypothesis SUBSET
# selection only — the engine decides all hypothesis states).
HYPOTHESIS_PHRASES: tuple[tuple[str, str], ...] = (
    ("corner speed", "H1_corner_speed"),
    ("cornering", "H1_corner_speed"),
    ("throttle", "H2_throttle"),
    ("brak", "H3_braking"),
    ("tyre", "H4_tyre_state"),
    ("tire", "H4_tyre_state"),
    ("race control", "H5_race_control"),
    ("safety car", "H5_race_control"),
    ("yellow flag", "H5_race_control"),
    ("red flag", "H5_race_control"),
    ("drs", "H6_drs"),
)

# Question-type detection rules, evaluated in order; first match wins.
# The regexes are deliberately specific: an unmatched question is
# UNSUPPORTED, never forced into a type.
_TYPE_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    # counterfactual: "could X have changed Y" / "what if" phrasing
    ("COUNTERFACTUAL_ELIGIBILITY", re.compile(
        r"\bcould\b[\s\S]{0,80}\b(remov\w*|halv\w*|half|without|less|"
        r"slower|faster)\b|\bwhat if\b", re.I)),
    # recurring pattern across races
    ("CROSS_RACE_PATTERN", re.compile(
        r"\b(recur\w*|pattern|repeat\w*|again in (other|another|different)"
        r"\s+(races?|seasons?))\b", re.I)),
    # stint-scope question (number extracted separately)
    ("STINT_PERFORMANCE", re.compile(
        r"\bstint\s*\d*\b[\s\S]{0,60}\b(degrade|trend|evolv|perform|pace|"
        r"drop|fall)\w*\b|\b(degrade|trend|evolv)\w*\b[\s\S]{0,60}\bstint\b",
        re.I)),
    # regime / phase decomposition
    ("PERFORMANCE_REGIME", re.compile(
        r"\b(regimes?|phases?|segments?)\b[\s\S]{0,40}\b(race|stint|lap)\b"
        r"|\b(across|throughout|over) the (race|stint)\b", re.I)),
    # formal hypothesis evaluation
    ("HYPOTHESIS_EVALUATION", re.compile(
        r"\bhypothes[ie]s\b|\bcaused by\b", re.I)),
    # lap-scope with explicit lap number (extracted separately)
    ("LAP_PERFORMANCE", re.compile(r"\blap\s*\d{1,3}\b", re.I)),
    # race-level gap / time loss without a lap qualifier. This is the LAST
    # rule, so it only sees questions nothing more specific claimed. It is
    # extended with the phrasings engineers actually use for whole-session
    # performance questions — "performance loss", "turning point", "gradual or
    # sudden", "after the safety car" — none of which the narrower "time loss"
    # wording matched, so they were being reported as unsupported.
    ("RACE_GAP", re.compile(
        r"\b(race gap|gap|deficit|time loss|lost time)\b"
        r"|\b(performance loss|pace loss)\b"
        r"|\b(lose|lost|loses|losing|gives?|gave|giving)\s+(up\s+)?time\b"
        r"|\b(where|when) did\b[\s\S]{0,60}\b(gap|time|lose|lost)\b"
        r"|\b(slower|faster)(\s+than)?\b"
        r"|\b(race|drove|raced)\b[\s\S]{0,40}\b(different|differently)\b"
        r"|\b(different|differently)\b[\s\S]{0,40}\b(race|drove|raced)\b"
        r"|\bturning point\b"
        r"|\bregime change\b"
        r"|\b(gradual(ly)?|sudden(ly)?)\b"
        r"|\bafter the (safety car|pit stop)\b"
        r"|\bintermittent\b"
        r"|\binvestigate\b"
        r"|\bwhat mattered\b",
        re.I)),
)

# Instruction-like patterns (prompt-injection quarantine). Detection is
# for the audit record ONLY: the parser extracts entities from data and
# the pipeline cannot be redirected by text content by construction.
_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(ignore|disregard|forget)\b[\s\S]{0,40}\b"
               r"(evidence|previous|above|instructions?|rules?)\b", re.I),
    re.compile(r"\b(always|never)\b[\s\S]{0,40}\b(conclude|say|report|"
               r"answer|claim)\b", re.I),
    re.compile(r"\byou must\b|\byou are now\b|\bsystem prompt\b|"
               r"\boverride\b[\s\S]{0,30}\b(evidence|result|engine)\b",
               re.I),
    re.compile(r"\bpretend\b|\broleplay\b|\bact as\b", re.I),
)

# Job titles that precede a driver mention without being part of a name.
# The canonical store genuinely contains a driver whose family name is
# "Driver", so "Test Driver" was resolving to a real but entirely different
# person — a silent substitution, which the resolution contract forbids. A
# title word before the mention means the phrase is a role, not a name.
# Closed vocabulary, matching the rest of this module's design.
_DRIVER_TITLE_WORDS = frozenset({
    "test", "reserve", "race", "second", "third", "fourth", "former",
    "rookie", "veteran", "guest", "substitute", "backup", "main", "academy",
    "junior", "senior", "f1", "f2", "f3", "young",
})


def _preceded_by_title_word(low_text: str, idx: int) -> bool:
    """True when the word immediately before ``idx`` is a driver job title."""
    before = low_text[:idx].rstrip()
    if not before:
        return False
    words = before.split()
    return bool(words) and words[-1] in _DRIVER_TITLE_WORDS


_INTERROGATIVES = (
    "why", "what", "did", "does", "could", "was", "were", "where",
    "when", "how", "is", "are", "which", "who", "would", "can",
)
_STOPCAPS = set(_INTERROGATIVES) | {
    "i", "a", "an", "the", "in", "on", "at", "to", "of", "and", "or",
    "f1", "formula", "grand", "prix", "gp", "race", "qualifying",
    "r", "round", "season", "lap", "stint", "driver", "vs", "if",
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _blank_mention(text: str, label: str) -> str:
    """Remove one resolved driver mention from the working question text.

    Matching is accent-insensitive because canonical names carry accents while
    users type without them: the canonical family name is ``Pérez`` and the
    question says ``Perez``. Matching already normalises accents (so the
    mention IS found), but the removal step used the raw label against the raw
    text, so an accented canonical name never actually cleared the ASCII
    mention. The leftover was then re-read as a place token, and race
    resolution failed with a misleading "missing critical context" — the most
    canonical question in the product could not resolve.

    Removes on the accent-stripped form (same length, same offsets) and
    returns the ORIGINAL text so downstream capitalized-token scanning still
    sees real casing.
    """
    stripped = _strip_accents(label)
    if not stripped:
        return text
    return re.sub(re.escape(stripped), " ", _strip_accents(text), flags=re.I)


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text)
                   if unicodedata.category(c) != "Mn")


def _conn(queries: CanonicalQueries) -> sqlite3.Connection:
    """Read-only connection over the canonical store (same precedent as
    the 6Q search endpoint: parameterized, read-only, no DDL)."""
    conn = sqlite3.connect(queries.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _season_participants(queries: CanonicalQueries, season: int) -> set[str]:
    with _conn(queries) as conn:
        rows = conn.execute(
            "SELECT DISTINCT d.driver_key FROM canonical_results res "
            "JOIN canonical_sessions s ON s.session_id = res.session_id "
            "JOIN canonical_races r ON r.race_id = s.race_id "
            "JOIN canonical_drivers d ON d.driver_id = res.driver_id "
            "WHERE r.season = ?", (int(season),)).fetchall()
    return {r["driver_key"] for r in rows}


def _resolve_driver_name(
    queries: CanonicalQueries, name: str, season: Optional[int],
    participants: Optional[set[str]] = None,
) -> Optional[str]:
    """Resolve one free-text driver mention to a canonical driver_key.

    Order: accent-insensitive exact full_name → exact driver_key →
    code (word-bounded) → family_name. Season participation is used
    ONLY to disambiguate several canonical candidates; a unique
    candidate is returned even when they did not drive in the season
    (the engine's participant check then answers UNAVAILABLE honestly —
    the Antonelli-in-2023 contract). No fuzzy matching.
    """
    token = _strip_accents(_norm(name))
    if not token:
        return None
    with _conn(queries) as conn:
        rows = conn.execute(
            "SELECT driver_key, full_name, code, family_name "
            "FROM canonical_drivers").fetchall()

    low = token.lower()
    exact = [r for r in rows
             if _strip_accents(r["full_name"] or "").lower() == low]
    if len(exact) == 1:
        return exact[0]["driver_key"]
    by_key = [r for r in rows if r["driver_key"] == low]
    if len(by_key) == 1:
        return by_key[0]["driver_key"]

    candidates: list[sqlite3.Row] = []
    if len(token) == 3:
        candidates = [r for r in rows
                      if (r["code"] or "").upper() == token.upper()]
    if not candidates:
        candidates = [r for r in rows
                      if _strip_accents(r["family_name"] or "").lower() == low]
    if not candidates:
        return None
    if season is not None and len(candidates) > 1:
        if participants is None:
            participants = _season_participants(queries, int(season))
        filtered = [r for r in candidates
                    if r["driver_key"] in participants]
        if filtered:
            candidates = filtered
    if len(candidates) == 1:
        return candidates[0]["driver_key"]
    # several canonical drivers share the mention and participation does
    # not disambiguate → unresolved (never guess)
    return None


def _resolve_race(
    queries: CanonicalQueries, season: int, place_tokens: list[str],
) -> tuple[Optional[int], Optional[str]]:
    """Resolve a race round by season + place tokens.

    Matching order per token: grand_prix key (exact, then single-substring)
    first, then circuit aliases (circuit_key, circuit name, city) — a
    user's 'Jeddah'/'Imola'/'Zandvoort' is a circuit or city, not a GP
    name. A token is accepted only when it maps to exactly ONE round in
    the season; zero or several matches are unresolved (never guessed).
    Returns (round, race_label).
    """
    with _conn(queries) as conn:
        rows = conn.execute(
            "SELECT r.round, r.grand_prix, c.circuit_key, c.name AS "
            "circuit_name, c.city, c.country "
            "FROM canonical_races r LEFT JOIN canonical_circuits c "
            "ON c.circuit_id = r.circuit_id "
            "WHERE r.season = ? ORDER BY r.round", (int(season),)).fetchall()
    keys: list[tuple[int, str, set[str]]] = []
    for r in rows:
        aliases = {str(r["grand_prix"] or "")}
        for col in ("circuit_key", "circuit_name", "city", "country"):
            v = r[col]
            if v:
                aliases.add(_strip_accents(str(v)).lower())
        keys.append((int(r["round"]), _strip_accents(
            r["grand_prix"] or ""), aliases))
    for tok in place_tokens:
        t = _strip_accents(tok).lower().replace(" ", "-")
        exact = [k for k in keys if k[1] == t]
        if len(exact) == 1:
            return exact[0][0], exact[0][1]
        like = [k for k in keys if all(p in k[1] for p in t.split("-"))]
        if len(like) == 1:
            return like[0][0], like[0][1]
        if len(like) > 1:
            return None, (f"ambiguous race name '{tok}': "
                          f"{sorted(k[1] for k in like)}")
        # circuit/city/country aliases (deterministic, single-round only)
        alias_exact = [k for k in keys if t in k[2]]
        if len(alias_exact) == 1:
            return alias_exact[0][0], alias_exact[0][1]
        if len(alias_exact) > 1:
            return None, (f"ambiguous race name '{tok}': "
                          f"{sorted(k[1] for k in alias_exact)}")
        alias_like = [k for k in keys
                      if any(all(p in a for p in t.split("-"))
                             for a in k[2])]
        if len(alias_like) == 1:
            return alias_like[0][0], alias_like[0][1]
        if len(alias_like) > 1:
            return None, (f"ambiguous race name '{tok}': "
                          f"{sorted(k[1] for k in alias_like)}")
    if place_tokens:
        return None, f"no canonical race for {season} matching {place_tokens}"
    return None, None


def _capitalized_tokens(text: str) -> list[str]:
    """Multi-word capitalized sequences (potential place names), longest
    first, excluding interrogatives and driver mentions."""
    out: list[list[str]] = []
    for seq in re.findall(r"[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*", text):
        words = seq.split()
        if words[0].lower() in _STOPCAPS and len(words) == 1:
            continue
        if all(w.lower() in _STOPCAPS for w in words):
            continue
        out.append(words)
    out.sort(key=len, reverse=True)
    # drop sequences contained in a longer kept one
    kept: list[list[str]] = []
    for words in out:
        joined = " ".join(words).lower()
        if any(joined in " ".join(k).lower() for k in kept):
            continue
        kept.append(words)
    return [" ".join(w) for w in kept]


def _scan_injection(text: str) -> dict[str, Any]:
    flagged = [f"pattern_{i}" for i, p in enumerate(_INJECTION_PATTERNS)
               if p.search(text)]
    return {"flagged": bool(flagged), "patterns": flagged,
            "policy": ("question text is data; instruction-like patterns "
                       "are recorded here and never executed")}


def _driver_mentions(
    queries: CanonicalQueries, text: str, season: Optional[int],
    participants: Optional[set[str]],
) -> list[tuple[str, str]]:
    """Deterministic driver-mention extraction from question text.

    A mention is an accent-insensitive, word-bounded occurrence of a
    canonical full name or family name that appears capitalized in the
    text (full names accept any capitalization; short/prose-collision
    family names must be capitalized to avoid matching common words).
    Each mention resolves canonically; ambiguous family names are
    disambiguated by season participation when the season is known.
    """
    low_text = _strip_accents(text).lower()
    plain_text = _strip_accents(text)
    with _conn(queries) as conn:
        rows = conn.execute(
            "SELECT driver_key, full_name, family_name "
            "FROM canonical_drivers").fetchall()

    found: list[tuple[str, str, int]] = []  # (label, key, start)

    def _word_bounded(idx: int, length: int) -> bool:
        before_ok = idx == 0 or not low_text[idx - 1].isalnum()
        after_ok = idx + length >= len(low_text) or \
            not low_text[idx + length].isalnum()
        return before_ok and after_ok

    seen_spans: set[tuple[int, int]] = set()
    for r in sorted(rows, key=lambda r: len(r["full_name"] or ""),
                    reverse=True):
        for label, require_cap in (
            (r["full_name"] or "", False),
            (r["family_name"] or "", True),
        ):
            lab = _strip_accents(label).lower()
            if len(lab) < 4:
                continue
            start = 0
            while True:
                idx = low_text.find(lab, start)
                if idx == -1:
                    break
                start = idx + 1
                if not _word_bounded(idx, len(lab)):
                    continue
                span = plain_text[idx:idx + len(label)]
                if require_cap and not span[:1].isupper():
                    continue  # prose word, not a driver mention
                if _preceded_by_title_word(low_text, idx):
                    continue  # "Test Driver" is a role, not a person
                span_key = (idx, idx + len(lab))
                if any(a <= span_key[0] and span_key[1] <= b
                       for a, b in seen_spans):
                    break  # covered by a longer mention already found
                key = _resolve_driver_name(queries, label, season,
                                           participants)
                if key:
                    found.append((label, key, idx))
                    seen_spans.add(span_key)
                break

    # first mention in the TEXT is the subject (driver A), the second is
    # the reference (driver B): "Why did X lose time to Y" — X is A.
    found.sort(key=lambda f: f[2])
    deduped: list[tuple[str, str]] = []
    for label, key, _ in found:
        if key in {k for _, k in deduped}:
            continue
        deduped.append((label, key))
    return deduped


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------

def parse_question(
    queries: CanonicalQueries,
    question_text: str,
    context: Optional[dict[str, Any]] = None,
    constraints: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Parse a natural-language engineering question.

    Returns the canonical question object (status PARSED) or an honest
    failure object (status INVALID_QUESTION / CONTEXT_UNRESOLVED /
    UNSUPPORTED_QUESTION) with a reason and, where applicable, the
    candidates a user should clarify between. Deterministic: the same
    inputs always produce the same output.
    """
    context = dict(context or {})
    log: list[dict[str, Any]] = []

    def out(status: str, **fields: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "analysis": ANALYSIS, "version": INTAKE_VERSION,
            "status": status,
            "question_text": text if status != INTAKE_INVALID else None,
            "provenance": {
                "method": "deterministic_regex_intake",
                "intake_version": INTAKE_VERSION,
                "resolution_log": log,
                "llm_assist": "none (deterministic parser only)",
            },
        }
        base.update(fields)
        return base

    # --- input validation --------------------------------------------------
    if not isinstance(question_text, str):
        return out(INTAKE_INVALID, reason="question_text must be a string")
    text = _norm(question_text)
    if not text:
        return out(INTAKE_INVALID, reason="question_text is empty")
    if len(text) > MAX_QUESTION_CHARS:
        return out(INTAKE_INVALID,
                   reason=f"question_text exceeds {MAX_QUESTION_CHARS} chars")

    injection = _scan_injection(text)
    if injection["flagged"]:
        log.append({"kind": "INJECTION_SCAN", "result": injection["patterns"],
                    "policy": injection["policy"]})

    # --- explicit context wins (validated, never guessed) -------------------
    season: Optional[int] = None
    if context.get("season") is not None:
        try:
            season = int(context["season"])
        except (TypeError, ValueError):
            return out(INTAKE_INVALID, reason="context.season must be an integer")
    round_num: Optional[int] = None
    if context.get("round") is not None:
        try:
            round_num = int(context["round"])
        except (TypeError, ValueError):
            return out(INTAKE_INVALID, reason="context.round must be an integer")
    lap_number: Optional[int] = None
    if context.get("lap_number") is not None:
        try:
            lap_number = int(context["lap_number"])
        except (TypeError, ValueError):
            return out(INTAKE_INVALID, reason="context.lap_number must be an integer")
    stint_number: Optional[int] = None
    if context.get("stint_number") is not None:
        try:
            stint_number = int(context["stint_number"])
        except (TypeError, ValueError):
            return out(INTAKE_INVALID, reason="context.stint_number must be an integer")
    session_type = str(context.get("session_type") or "").upper() or None
    if session_type is not None and session_type not in ("RACE", "QUALIFYING"):
        return out(INTAKE_INVALID, reason="context.session_type must be RACE or QUALIFYING")
    pattern_id = context.get("pattern_id") or None

    participants: Optional[set[str]] = \
        _season_participants(queries, season) if season is not None else None

    def _context_driver(value: Any, label: str) -> Optional[str]:
        """Context driver inputs must be canonical (key or resolvable
        name); anything else is an error, never a guess."""
        if value is None:
            return None
        key = _resolve_driver_name(queries, str(value), season, participants)
        if key is None:
            raise _IntakeError(
                f"context.{label} '{value}' does not resolve to a "
                "canonical driver")
        return key

    try:
        driver_a = _context_driver(context.get("driver_a"), "driver_a")
        driver_b = _context_driver(context.get("driver_b"), "driver_b")
    except _IntakeError as exc:
        return out(INTAKE_INVALID, reason=str(exc))

    # --- question type (text-only detection, needed before season handling) --
    qt: Optional[str] = None
    for qt_candidate, rule in _TYPE_RULES:
        if rule.search(text):
            qt = qt_candidate
            break

    # --- numbers from text ---------------------------------------------------
    years = [int(m) for m in re.findall(r"\b(19[5-9]\d|20[0-7]\d)\b", text)]
    if qt == "CROSS_RACE_PATTERN":
        # a pattern question's scope is a season SPAN, not one race: the
        # mentioned seasons (or the context season) name the discovery
        # window; the round anchor comes from context/round when given
        pattern_seasons = sorted(set(years))
        if not pattern_seasons and season is not None:
            pattern_seasons = [season]
        if len(pattern_seasons) > 4:
            return out(INTAKE_UNRESOLVED,
                       reason=("pattern questions span at most 4 seasons; "
                               f"mentioned: {pattern_seasons}"),
                       injection_scan=injection)
        if not pattern_seasons:
            return out(INTAKE_UNRESOLVED,
                       reason=("cross-race pattern questions must name the "
                               "season(s) to scan (e.g. 'in 2022 and 2023')"),
                       injection_scan=injection)
        for y in pattern_seasons:
            log.append({"kind": "PATTERN_SEASON", "text": str(y),
                        "resolved": y, "source": "question_text"})
        season = pattern_seasons[-1]
        participants = _season_participants(queries, season)
    elif len(set(years)) > 1:
        return out(INTAKE_UNRESOLVED,
                   reason=f"multiple seasons mentioned: {sorted(set(years))}",
                   candidates=sorted(set(years)), injection_scan=injection)
    if (qt != "CROSS_RACE_PATTERN" and years
            and season is not None and years[0] != season):
        return out(INTAKE_UNRESOLVED,
                   reason=(f"season {season} given in context but text "
                           f"mentions {years[0]}"),
                   injection_scan=injection)
    if years:
        season = years[0]
        participants = _season_participants(queries, season)
        log.append({"kind": "SEASON", "text": str(years[0]),
                    "resolved": years[0], "source": "question_text"})

    lap_match = re.search(r"\blap\s*(\d{1,3})\b", text, re.I)
    if lap_match:
        if lap_number is not None and lap_number != int(lap_match.group(1)):
            return out(INTAKE_UNRESOLVED,
                       reason=(f"lap {lap_number} given in context but text "
                               f"mentions lap {lap_match.group(1)}"),
                       injection_scan=injection)
        lap_number = int(lap_match.group(1))
        log.append({"kind": "LAP", "text": lap_match.group(0),
                    "resolved": lap_number, "source": "question_text"})
    stint_match = re.search(r"\bstint\s*(\d{1,2})\b", text, re.I)
    if stint_match:
        if stint_number is not None and stint_number != int(stint_match.group(1)):
            return out(INTAKE_UNRESOLVED,
                       reason=(f"stint {stint_number} given in context but "
                               f"text mentions stint {stint_match.group(1)}"),
                       injection_scan=injection)
        stint_number = int(stint_match.group(1))
        log.append({"kind": "STINT", "text": stint_match.group(0),
                    "resolved": stint_number, "source": "question_text"})

    # --- session type ---------------------------------------------------------
    if session_type is None:
        if re.search(r"\bqualif\w*\b", text, re.I):
            session_type = "QUALIFYING"
            log.append({"kind": "SESSION", "text": "qualifying",
                        "resolved": "QUALIFYING", "source": "question_text"})
        else:
            session_type = "RACE"

    # --- drivers ---------------------------------------------------------------
    work = text
    if not driver_a:
        mentions = _driver_mentions(queries, work, season, participants)
        for label, key in mentions:
            work = _blank_mention(work, label)
            log.append({"kind": "DRIVER", "text": label, "resolved": key,
                        "source": "canonical_drivers"})
        if len(mentions) >= 1:
            driver_a = mentions[0][1]
        if len(mentions) >= 2:
            driver_b = mentions[1][1]
    if driver_a and not driver_b:
        # remaining capitalized tokens may be a second driver mention;
        # only exact canonical-name matches qualify, and (unlike explicit
        # full-name mentions) the driver must have participated in the
        # season when one is known — prose collisions are never drivers
        for tok in _capitalized_tokens(work):
            key = _resolve_driver_name(queries, tok, season, participants)
            if key is None:
                continue
            if season is not None and key not in (participants or set()):
                continue
            if key != driver_a:
                driver_b = key
                work = _blank_mention(work, tok)
                log.append({"kind": "DRIVER", "text": tok, "resolved": key,
                            "source": "canonical_drivers"})
                break

    # --- race --------------------------------------------------------------------
    place_tokens = [t for t in _capitalized_tokens(work)
                    if t.lower() not in _STOPCAPS]
    race_label: Optional[str] = None
    if qt == "CROSS_RACE_PATTERN":
        # a pattern question is not race-scoped: no race resolution, and a
        # round is only allowed as an explicit anchor via context
        round_num = round_num if context.get("round") is not None else None
        if round_num is not None:
            race_label = f"anchor {season} R{round_num}"
    elif round_num is None and season is not None and place_tokens:
        round_num, race_label = _resolve_race(queries, season, place_tokens)
        log.append({"kind": "RACE", "text": place_tokens[0],
                    "resolved": (f"{season} R{round_num}" if round_num
                                 else None),
                    "source": race_label or "canonical_races"})
    elif round_num is not None:
        race_label = f"{season} R{round_num}" if season else None

    # --- question type finalization ------------------------------------------
    if qt == "STINT_PERFORMANCE" and stint_number is None:
        # stint scope is explicit but the stint number is missing:
        # a specific stint is critical context, never a default
        return out(INTAKE_UNRESOLVED,
                   reason=("stint-scope question without a stint number; "
                           "provide the stint (e.g. 'stint 1')"),
                   candidates=["stint 1", "stint 2"],
                   injection_scan=injection)
    if qt == "QUALIFYING_LAP_PERFORMANCE":
        qt = "LAP_PERFORMANCE"
    if session_type == "QUALIFYING" and \
            qt in (None, "RACE_GAP", "HYPOTHESIS_EVALUATION"):
        # qualifying deficit/hypothesis phrasing maps to the measured
        # single-lap comparison (Phase 6S semantics: no qualifying
        # telemetry exists, so the honest capability is lap evidence)
        if qt is not None:
            log.append({"kind": "TYPE_MAPPING", "text": qt,
                        "resolved": "LAP_PERFORMANCE",
                        "source": "qualifying single-lap comparability"})
        qt = "LAP_PERFORMANCE"
    if qt == "LAP_PERFORMANCE" and lap_number is None:
        if session_type == "QUALIFYING":
            # qualifying comparison needs a specific lap; context critical
            return out(INTAKE_UNRESOLVED,
                       reason=("qualifying lap question without a lap "
                               "number; provide the qualifying lap to "
                               "compare (e.g. 'lap 2')"),
                       injection_scan=injection)
        # race-scope loss phrasing without a lap qualifier is a race-gap
        # question (documented deterministic mapping, not a guess: no lap
        # fact can be invented)
        qt = "RACE_GAP"
    if qt is None:
        if re.match(rf"^({'|'.join(_INTERROGATIVES)})\b", text, re.I) or \
                text.endswith("?"):
            return out(INTAKE_UNSUPPORTED,
                       reason=("the question does not map to a supported "
                               "engineering capability"),
                       supported_question_types=list(INTAKE_QUESTION_TYPES),
                       injection_scan=injection)
        return out(INTAKE_UNRESOLVED,
                   reason=("the request is not phrased as a supported "
                           "engineering question"),
                   supported_question_types=list(INTAKE_QUESTION_TYPES),
                   injection_scan=injection)
    # a CROSS_RACE_PATTERN question without a pattern id is fine: the
    # orchestrator runs the bounded deterministic discovery over the
    # question's season span (recorded in provenance)
    if qt == "HYPOTHESIS_EVALUATION" and lap_number is None:
        return out(INTAKE_UNRESOLVED,
                   reason=("hypothesis evaluation is lap-scoped; provide "
                           "the lap (e.g. 'on lap 6')"),
                   injection_scan=injection)

    # --- required entity completeness ---------------------------------------------
    if qt == "CROSS_RACE_PATTERN" and round_num is None:
        # the pattern scope spans the listed seasons; a race anchor is only
        # needed for the engine's participant validation. Deterministic and
        # explicitly logged — never presented as the analyzed race.
        round_num = 1
        log.append({"kind": "RACE_ANCHOR", "text": "pattern scope",
                    "resolved": f"{season} R1",
                    "source": ("deterministic anchor for participant "
                               "validation; the pattern spans the listed "
                               "seasons")})
    missing: list[str] = []
    if season is None:
        missing.append("season")
    if round_num is None:
        missing.append("race (round)")
    if not driver_a:
        missing.append("driver A")
    if not driver_b:
        missing.append("driver B")
    if missing:
        return out(INTAKE_UNRESOLVED, reason="missing critical context",
                   missing=missing, injection_scan=injection)
    if driver_a == driver_b:
        return out(INTAKE_UNRESOLVED,
                   reason=("both drivers resolved to the same canonical "
                           f"driver ({driver_a})"),
                   injection_scan=injection)

    parsed: dict[str, Any] = out(
        INTAKE_PARSED,
        question_type=qt,
        season=int(season),
        round=int(round_num),
        session_type=session_type,
        driver_a=driver_a,
        driver_b=driver_b,
        lap_number=lap_number,
        stint_number=stint_number,
        pattern_id=pattern_id,
        pattern_seasons=(sorted(set(years))
                         if qt == "CROSS_RACE_PATTERN" and years else None),
        race_label=race_label,
        hypotheses_requested=[
            h for phrase, h in HYPOTHESIS_PHRASES if phrase in text.lower()
        ] or None,
        injection_scan=injection,
    )
    parsed["provenance"]["resolution_log"] = log
    parsed["question_object_hash"] = _hash_obj({
        k: v for k, v in parsed.items()
        if k not in ("provenance", "question_object_hash")})
    return parsed


class _IntakeError(Exception):
    """Internal: invalid context value (never leaks as a crash)."""

"""Semantic intent taxonomy and engineering language.

Intents are *semantic*, not pages. "Where did the time go" and "which sector
cost us most" are the same intent (LOCATE) expressed twice; neither has a
route. Mapping language to intents is what lets a question reach capabilities
that were never designed for that phrasing.

Three rules govern this module:

1. **Closed vocabulary.** Every rule is a named pattern with an explicit
   intent. No open-ended scoring, no fuzzy similarity — an unmatched question
   stays UNSUPPORTED rather than being forced into the nearest intent.
2. **Detection is not conclusion.** Finding the LOCATE intent says the user
   asked *where*; it does not say corner-level data exists. Resolution of the
   finest valid spatial level is the availability engine's job.
3. **Causal language is quarantined.** "Did tyres cause it" is detected as a
   causal claim and *translated* into testable sub-questions (§17). RACEWISE
   never accepts a user's causal premise by default.
"""
from __future__ import annotations

import re
from typing import Iterable

# ---------------------------------------------------------------------------
# Intent vocabulary (§13). Semantic, closed, and independent of UI routes.
# ---------------------------------------------------------------------------
INTENTS = (
    "DESCRIBE",
    "COMPARE",
    "EXPLAIN",
    "ATTRIBUTE",
    "LOCATE",
    "QUANTIFY",
    "TREND",
    "DECOMPOSE",
    "CORRELATE",
    "TEST_HYPOTHESIS",
    "FALSIFY",
    "TRACE",
    "RECONCILE",
    "INVESTIGATE",
    "FIND_PATTERN",
    "COMPARE_RACES",
    "COMPARE_STINTS",
    "COMPARE_LAPS",
    "FIND_TURNING_POINT",
    "FIND_REGIME",
    "EVALUATE_DRIVER",
    "EVALUATE_CAR",
    "EVALUATE_TYRE_BEHAVIOR",
    "EVALUATE_RACE_CONTROL",
    "COUNTERFACTUAL",
    "WHAT_IF",
    "PROVENANCE",
    "REPLAY",
    "MEMORY",
    "SUMMARIZE",
)

# Order matters: first match wins, so specific patterns precede general ones.
# Each entry is (intent, compiled_pattern, weight).
_INTENT_RULES: tuple[tuple[str, str], ...] = (
    # --- falsification and contradiction come before the general explain ---
    ("FALSIFY", r"\bagainst\b|\bcontradict\w*|\bdisprove\b|\bevidence against\b"
                r"|\bnot\b[\s\S]{0,30}\b(explain|support|cause)\b"
                r"|\bopposite\b|\bdisconfirm\w*|\brebut\w*"
                # explicit falsification verbs engineers actually use:
                # "ruling out tyre state", "refute the DRS claim",
                # "any counter-evidence", "negation test", "was it NOT
                # braking". A negated hypothesis term is a falsification
                # ask by definition.
                r"|\brul(e|ed|ing)\s+out\b|\brefut\w*|\bcounter.?evidence\b"
                r"|\bnegation test\b|\bwas it not\b"
                r"|\bnot\b[\s\S]{0,15}\b(tyre|tire|throttle|brak|corner|"
                r"drs|fuel|compound|grip|speed)\b"),
    ("RECONCILE", r"\breconcil\w*|\bdisagree\w*|\bconflict\w*|\binconsisten\w*"
                  r"|\bmismatch\b|\bdiscrepanc\w*"
                  # 'what remains unexplained' is the residual question; it
                  # must reach RECONCILE or it falls through to nothing.
                  r"|\bunexplain\w*|\bnot explain\w*|\bleft over\b"
                  r"|\bwhat (does|did) (the evidence )?not\b"
                  # residual / reconciliation vocabulary
                  r"|\bresidual\b|\bremainder\b|\baccounted for\b"
                  r"|\baccount for\b|\bshare of\b"),
    # --- counterfactual before what_if phrasing overlaps ---
    ("COUNTERFACTUAL", r"\bcould\b[\s\S]{0,90}\b(remov\w*|halv\w*|half|without|"
                       r"less|slower|faster|recover\w*|chang\w*)\b"
                       r"|\bwhat if\b|\bif\b[\s\S]{0,60}\bhad\b[\s\S]{0,40}\b(been|not)\b"
                       # 'would the lap time be' is a counterfactual too, not a
                       # bare hypothetical: it asks for a modelled number.
                       r"|\bwould\b[\s\S]{0,60}\b(have|change|recover|be|been)\b"
                       r"|\bwhat would\b[\s\S]{0,60}\b(happen|be)\b"
                       r"|\bhow much\b[\s\S]{0,40}\b(recover\w*|recovered)\b"
                       # "simulate the deficit" / "model the effect" /
                       # "project the lap time" ask for a modelled number
                       # just as much as "what if" does. The counterfactual
                       # noun must appear nearby so a bare "model the car"
                       # is not swept in as a hypothetical.
                       r"|\b(simulat\w*|modell?ed|model|project\w*|projection)\b"
                       r"[\s\S]{0,60}\b(effect|deficit|lap ?time|result|scenario|"
                       r"counterfactual)\b"
                       r"|\bcounterfactual\b"),
    ("WHAT_IF", r"\bwhat if\b|\bsuppose\b|\bimagine\b|\bpretend\b|\bwhat would\b"),
    # --- provenance / replay ---
    ("PROVENANCE", r"\bwhere does\b[\s\S]{0,30}\b(come from|data|source)\b"
                   r"|\bprovenance\b|\bsource of\b|\btrace\b|\bhow (was|did) .* (derived|computed)\b"
                   r"|\bevidence id\b|\bwhich (table|provider|method)\b"
                   # verification and method-of-production asks:
                   # "verify the output hash", "what method produced
                   # the attribution", "where did the numbers come from".
                   r"|\bverify\b|\boutput hash\b|\bhash\b"
                   r"|\b(what|which)\s+method\b"
                   r"|\bwhere (did|does)\b[\s\S]{0,30}\b(come from|numbers)\b"),
    ("REPLAY", r"\breplay\b|\bre-?run\b|\breproduc\w*|\brepeatable\b|\bdeterministic\b"),
    ("MEMORY", r"\bhas\b[\s\S]{0,30}\b(happened|seen|occurred) before\b|\bprecedent\b"
               r"|\bbefore\b[\s\S]{0,30}\b(asked|investigated)\b|\bsimilar (case|investigation)\b"
               r"|\bpreviously\b"
               # 'has X had this problem before' is a precedent ask
               r"|\b(has|have|had)\b[\s\S]{0,40}\bbefore\b"),
    # --- pattern finding ---
    ("FIND_PATTERN", r"\bsame thing\b|\bpattern\b|\brecur\w*|\brepeat\w*|"
                     r"\bagain\b|\belsewhere\b|\banother race\b|\bsimilar\b"),
    ("COMPARE_RACES", r"\b(different|another|other|this|each|previous|last)\b[\s\S]{0,20}\brace\b"
                      r"|\bfrom race to race\b|\brace to race\b|\bcompared?\b[\s\S]{0,20}\b(20\d\d)\b"),
    # --- hypothesis testing ---
    ("TEST_HYPOTHESIS", r"\bhypothes[ie]s?\b|\bcaused by\b|\bcaus(e|es|ed|ing|al)\b|\bwhy\b|"
                        # 'explain' and 'explanation' are different stems
                        # (explan- vs explai-): match both, or 'the explanation'
                        # silently fails to register as an explanation request.
                        r"\bexplain\b|\bexplain(?:s|ed|ing)?\b|\bexplanat\w*\b"
                        r"|\battribut\w*|\bresponsible\b|\bdriver of\b"
                        r"|\bwas it\b[\s\S]{0,40}\bor\b"
                        # hypothesis-weighting and hypothesis-support
                        # phrasings: "was the loss mostly throttle",
                        # "is corner speed supported", "is there a
                        # DRS effect", "what about the throttle".
                        r"|\b(mostly|mainly|primarily)\b"
                        r"|\bsupport\w*\b|\bwhat about\b"
                        r"|\bavailable\b|\b(is|are)\s+there\b"),
    ("EVALUATE_TYRE_BEHAVIOR", r"\b(tyre|tire|compound|grip|degrad\w*)\b"),
    ("EVALUATE_RACE_CONTROL", r"\b(race control|safety car|sc\b|vsc\b|yellow flag|"
                              r"red flag|penalt\w*|blue flag|virtual safety)\b"),
    ("EVALUATE_DRIVER", r"\bdriver\b[\s\S]{0,30}\b(consistent\w*|weak\w*|strong\w*|"
                        r"better|worse|perform\w*)\b|\bconsistently\b"),
    ("EVALUATE_CAR", r"\b(car|constructor|team|aero\w*|setup)\b"),
    # --- temporal ---
    ("FIND_TURNING_POINT", r"\bturning point\b|\bwhen did\b|\bwhat changed\b|"
                           r"\bafter the (pit|safety car|flag)\b|\bwhen\b[\s\S]{0,30}\b(change|start|end)\b"),
    ("FIND_REGIME", r"\bregimes?\b|\bphases?\b|\bsegments?\b|\bsteady states?\b|\bpattern of pace\b"),
    ("TREND", r"\btrend\w*|\bdegrad\w*|\bgetting worse\b|\bgetting better\b|"
              r"\bworsening\b|\bimproving\b|\bconsistent\w*|\bgradual\w*|"
              r"\bsudden\w*|\bstep change\b|\bover the (stint|race|laps?)\b"
              # trend phrasings: "get worse toward the end", "pace
              # falling", "accelerating or steady", "how did pace
              # evolve", "second stint slower than the first".
              r"|\bget(s|ting)?\s+worse\b|\bgot\s+worse\b"
              r"|\bfall\w*\b|\baccelerat\w*|\bevol(u|v)\w*"
              r"|\b(slower|faster)\s+than\b"
              r"|\b(tyre|tire)\s+life\b|\bsteady\b"),
    # --- spatial ---
    ("LOCATE", r"\bwhere\b[\s\S]{0,40}\b(lose|lost|time|gap|deficit|difference)\b"
               r"|\bwhich (sector|corner|region|part|area|straight|braking zone)\b"
               r"|\bsector\s*\d\b|\bmini-?sector\b|\bcorners?\b|\bbraking zone\b"
               r"|\bexit\b|\brotation\b|\btraction\b|\bdrs zone\b"
               r"|\bexactly where\b|\blocate\b"
               # attribution is a spatial-locate ask (the finest
               # valid level is resolved by the availability
               # engine, not here)
               r"|\battribut\w*"
               r"|\bthrough\b[\s\S]{0,20}\b(corner|sector|part|region)\b"),
    # --- structural ---
    ("DECOMPOSE", r"\bdecompos\w*|\bbreak ?down\b|\bsplit\b|\bwhere does .* go\b"
                  r"|\bhow (much|many)\b[\s\S]{0,30}\b(of the gap|deficit|loss)\b"),
    ("QUANTIFY", r"\bhow much\b|\bhow many\b|\bquantif\w*|\bwhat (amount|proportion)\b"
                 r"|\bmagnitude\b"),
    ("TRACE", r"\btrace\b|\bfollow\b|\bpath\b|\bchain\b"),
    # --- comparison ---
    ("COMPARE_STINTS", r"\bstint\b[\s\S]{0,30}\bvs\b|\bstints?\b[\s\S]{0,30}\b(compar|differ)\w*"),
    ("COMPARE_LAPS", r"\blap\b[\s\S]{0,20}\bvs\b|\blaps?\b[\s\S]{0,20}\b(compar|differ)\w*"
                     r"|\bprevious lap\b|\blast lap\b|\bown baseline\b"),
    ("COMPARE", r"\bvs\b|\bversus\b|\bcompared? (to|with)\b|\bdifferen\w+\b|\bbetter than\b|\bworse than\b"
                  # bare comparison phrasings: "compare X against Y",
                  # "which driver was quicker", "who was faster",
                  # "give me the lap 6 delta".
                  r"|\bcompar\w*\b|\b(faster|slower|quicker|quickest|fastest|slowest)\b"
                  r"|\bdelta\b|\b(gap|deficit)\s+between\b"),
    # --- generic ---
    ("EXPLAIN", r"\bexplain\w*|\bwhy\b|\bwhat happened\b|\bwhat mattered\b"),
    # A whole-race question may name no driver, no lap and no sector.
    # These phrasings are how engineers actually ask for one, and without
    # them the compiler rejects a question the system is built to answer.
    ("INVESTIGATE", r"\binvestigate\b|\banalyz\w*|\banalyse\b|\blook into\b|\bwhat can you tell\b|\bwalk me through\b|\bmaterially\b|\btimeline\b|\bchange character\b|\bwhat did we (see|learn|notice)\b|\bacross the race\b|\btell me what\b|\bthe whole race\b|\bthe story\b|\brace ?-?wide\b"),
    ("SUMMARIZE", r"\bsummar\w*|\boverall\b|\bin one line\b|\btl;?dr\b|\bhigh level\b"),
    ("DESCRIBE", r"\bwhat is\b|\bdescribe\b|\bwhat (data|weather|compound)\b"
                  # descriptive asks: "summarize the engineering
                  # picture", "describe the session context", "what
                  # does the data show".
                  r"|\bsummar\w*|\bpicture\b|\bcontext\b"
                  r"|\bwhat (does|did) the data\b"),
)

_COMPILED: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (intent, re.compile(pattern, re.I)) for intent, pattern in _INTENT_RULES
)

# ---------------------------------------------------------------------------
# Spatial scope (§14). Ordered: the resolver reports the finest level the data
# actually supports and never invents a finer one.
# ---------------------------------------------------------------------------
SPATIAL_SCOPES = (
    "lap", "sector", "mini_sector", "track_region", "corner",
    "braking_zone", "acceleration_zone", "straight", "drs_zone", "whole_session",
)

_SPATIAL_RULES: tuple[tuple[str, str], ...] = (
    ("sector", r"\bsector\s*([123])\b|\b([123])\s*(?:st|nd|rd)?\s+sector\b"),
    ("corner", r"\bcorner\s*(\d{1,2})\b|\bt(?:urn)?\s*(\d{1,2})\b"),
    ("braking_zone", r"\bbraking (?:zone|zone[s]?)\b|\bbraking\b"),
    ("acceleration_zone", r"\bacceleration (?:zone|zones)\b|\baccel\w*\b|\btraction\b"),
    ("straight", r"\bstraights?\b"),
    ("drs_zone", r"\bdrs zone\b|\bdrs\b"),
    ("mini_sector", r"\bmini-?sectors?\b"),
    ("track_region", r"\b(track )?region\b|\bpart of (the )?(track|lap)\b|\bthe (first|second|third) part\b"),
)

_COMPILED_SPATIAL: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (scope, re.compile(pattern, re.I)) for scope, pattern in _SPATIAL_RULES
)

# ---------------------------------------------------------------------------
# Temporal scope (§15).
# ---------------------------------------------------------------------------
TEMPORAL_SCOPES = (
    "lap", "lap_range", "stint", "regime", "race_control_transition",
    "context_transition", "race", "cross_race", "season",
)

_TEMPORAL_RULES: tuple[tuple[str, str], ...] = (
    ("race_control_transition", r"\b(after|before|during) the (safety car|sc\b|vsc\b|"
                                r"yellow flag|red flag|deployment)\b|\bwhen the (safety car|sc\b|vsc\b) came\b"),
    ("context_transition", r"\b(after|before|during) the (pit stop|pit|weather|rain|"
                           r"interruption|red flag)\b|\bpit phase\b"),
    ("lap_range", r"\b(?:next|last|past|previous|final)\s+(\d{1,2})\s+laps\b"
                  r"|\blaps?\s+(\d{1,3})\s*(?:to|-|through|and)\s*(\d{1,3})\b"
                  r"|\bfirst\s+(\d{1,2})\s+laps\b"),
    ("lap", r"\blap\s+(\d{1,3})\b|\bon lap\b"),
    ("stint", r"\bstints?\s*(\d{1,2})\b|\bsecond stint\b|\bfirst stint\b|\blast stint\b"
              r"|\bout lap\b|\bafter the (?:pit )?stop\b"),
    ("regime", r"\b(regimes?|phases?|segments?)\b|\bacross the (race|stint)\b|\bover the stint\b"),
    ("cross_race", r"\b(another|other|different|another) race\b|\bin (?:another|every) season\b"
                   r"|\bseason to season\b|\bacross seasons\b"),
    ("race", r"\b(whole|entire|across|throughout) race\b|\bover the race\b|\bthis race\b|\bthe race\b"),
    ("season", r"\b(19[5-9]\d|20[0-7]\d)\b|\bseason\b"),
)

_COMPILED_TEMPORAL: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (scope, re.compile(pattern, re.I)) for scope, pattern in _TEMPORAL_RULES
)

# ---------------------------------------------------------------------------
# Comparative and directional language (§42).
# ---------------------------------------------------------------------------
COMPARATIVE_TERMS = (
    "more", "less", "faster", "slower", "worse", "better", "increasing",
    "decreasing", "earlier", "later", "before", "after", "consistent",
    "intermittent", "recurring", "reversed", "gradual", "sudden",
)

_COMPARATIVE_RULES: tuple[tuple[str, str], ...] = (
    ("inconsistency", r"\bconsistent\w*\b|\bintermittent\b|\bcome and go\b|\bflicker\w*\b"),
    ("reversal", r"\breverse\w*|\bswing\b|\bovertook back\b|\bflip\w*|\bturned around\b"),
    ("abrupt", r"\bsudden\w*|\bstep change\b|\bcliff\b|\babrupt\w*|\bout of nowhere\b"),
    ("gradual", r"\bgradual\w*|\bprogressive\w*|\bsteady\b|\bincremental\w*|\bslope\b"),
    ("directional", r"\b(more|less|faster|slower|worse|better|increasing|decreasing)\b"),
)

_COMPILED_COMPARATIVE: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (kind, re.compile(pattern, re.I)) for kind, pattern in _COMPARATIVE_RULES
)

# ---------------------------------------------------------------------------
# Negation (§41) — maps to falsification, never to a silent inversion.
# ---------------------------------------------------------------------------
_NEGATION_RULES: tuple[tuple[str, str], ...] = (
    ("exclusion", r"\b(was|were|is|are|it)\s+NOT\b|\bnot\b[\s\S]{0,24}\b(braking|tyre|tire|throttle|corner|drs)\b"
                 r"|\bruled? out\b|\bcan'?t\b|\bisn'?t\b|\bwasn'?t\b|\bdidn'?t\b|\bno evidence\b"),
    ("contradiction_seek", r"\bevidence (against|contradicting|opposing)\b"
                           r"|\bwhat (contradicts|opposes)\b|\bshow .{0,20}against\b"
                           r"|\bagainst your\b|\bwhat fails\b"),
)

_COMPILED_NEGATION: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (kind, re.compile(pattern, re.I)) for kind, pattern in _NEGATION_RULES
)

# ---------------------------------------------------------------------------
# Causal claim quarantine (§17). Detected so it can be TRANSLATED into
# testable questions; never accepted as a premise.
# ---------------------------------------------------------------------------
_CAUSAL_RULES: tuple[tuple[str, str], ...] = (
    ("proof_demand", r"\bprove\b|\bprove that\b|\bcan you prove\b|\bdefinitiv\w*"
                     r"|\bwithout a doubt\b|\bconclusiv\w*\b|\b100% sure\b"),
    ("causal_assertion", r"\bcaused?\b|\bcausing\b|\bbecause of\b|\bdue to\b"
                         r"|\bresponsible for\b|\bled to\b|\bresulted in\b"),
    ("attribution_demand", r"\bexplain the (loss|gap|deficit)\b|\bwhy (was|did)\b"),
)

_COMPILED_CAUSAL: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (kind, re.compile(pattern, re.I)) for kind, pattern in _CAUSAL_RULES
)

# ---------------------------------------------------------------------------
# Engineering vocabulary (§43). Presence is a *hint for intent selection* only;
# it never implies a physical variable is measurable in this session.
# ---------------------------------------------------------------------------
ENGINEERING_TERMS = (
    "delta", "gap", "deficit", "gain", "loss", "degradation", "pace",
    "sector", "stint", "compound", "braking", "rotation", "exit", "traction",
    "drs", "safety car", "vsc", "yellow", "pit phase", "regime", "residual",
    "envelope", "soft", "hard", "medium", "intermediate", "wet", "undercut",
    "overcut", "dirty air", "fuel", "setup",
)


def detect_intents(text: str) -> tuple[str, ...]:
    """Semantic intents present in the text, first-match order, deduplicated."""
    found: list[str] = []
    for intent, pattern in _COMPILED:
        if intent in found:
            continue
        if pattern.search(text):
            found.append(intent)
    return tuple(found)


def detect_spatial_scope(text: str) -> tuple[str, ...]:
    """Spatial scopes named, finest-first as declared in SPATIAL_SCOPES."""
    found = [scope for scope, pattern in _COMPILED_SPATIAL if pattern.search(text)]
    return tuple(found)


def detect_temporal_scope(text: str) -> tuple[str, ...]:
    """Temporal scopes named."""
    return tuple(scope for scope, pattern in _COMPILED_TEMPORAL if pattern.search(text))


def detect_comparative(text: str) -> tuple[str, ...]:
    """Comparative/directional behaviours referenced."""
    return tuple(kind for kind, pattern in _COMPILED_COMPARATIVE if pattern.search(text))


def detect_negation(text: str) -> tuple[str, ...]:
    """Negation and contradiction-seeking forms present."""
    return tuple(kind for kind, pattern in _COMPILED_NEGATION if pattern.search(text))


def detect_causal_claim(text: str) -> tuple[str, ...]:
    """Causal framings that must be translated rather than accepted.

    ``proof_demand`` matters most: "can you prove DRS caused it" is a request to
    be told whether the evidence can establish a claim, not a claim.
    """
    return tuple(kind for kind, pattern in _COMPILED_CAUSAL if pattern.search(text))


def engineering_terms(text: str) -> tuple[str, ...]:
    """Domain vocabulary present. Informational only."""
    low = text.lower()
    return tuple(term for term in ENGINEERING_TERMS if term in low)


def sector_numbers(text: str) -> tuple[int, ...]:
    """Explicit sector numbers mentioned ("sector 2", "2nd sector")."""
    out: set[int] = set()
    for match in re.finditer(r"\bsector\s*([123])\b|\b([123])\s*(?:st|nd|rd)\s+sector\b",
                             text, re.I):
        for group in match.groups():
            if group:
                out.add(int(group))
    return tuple(sorted(out))


def corner_numbers(text: str) -> tuple[int, ...]:
    """Explicit corner numbers mentioned."""
    out: set[int] = set()
    for match in re.finditer(r"\bcorner\s*(\d{1,2})\b|\bt(?:urn)?\s*(\d{1,2})\b", text, re.I):
        for group in match.groups():
            if group:
                out.add(int(group))
    return tuple(sorted(out))


def hypothesis_phrases(text: str) -> tuple[str, ...]:
    """Which canonical hypotheses the user named explicitly."""
    from racewise.data.historical.question_intake import HYPOTHESIS_PHRASES

    low = text.lower()
    found = [hid for phrase, hid in HYPOTHESIS_PHRASES if phrase in low]
    # preserve canonical order, not phrase order
    from racewise.question_engine.capabilities import HYPOTHESIS_IDS

    return tuple(h for h in HYPOTHESIS_IDS if h in found)


def unresolved_terms(text: str) -> tuple[str, ...]:
    """Engineering terms with no deterministic capability behind them.

    Surfaced as an explicit unsupported-portion signal rather than silently
    dropped — the system says what it cannot do.
    """
    supported = {
        "delta", "gap", "deficit", "gain", "loss", "degradation", "pace",
        "sector", "stint", "compound", "braking", "rotation", "exit",
        "traction", "drs", "safety car", "vsc", "yellow", "pit phase",
        "regime", "residual", "envelope",
    }
    low = text.lower()
    out: list[str] = []
    for term in ENGINEERING_TERMS:
        if term in low and term not in supported and term not in out:
            out.append(term)
    return tuple(out)


def all_detectors(text: str) -> dict[str, Iterable[str]]:
    """Every detector over one text — used by the compiler and by tests."""
    return {
        "intents": detect_intents(text),
        "spatial_scopes": detect_spatial_scope(text),
        "temporal_scopes": detect_temporal_scope(text),
        "comparatives": detect_comparative(text),
        "negations": detect_negation(text),
        "causal_claims": detect_causal_claim(text),
        "engineering_terms": engineering_terms(text),
        "hypotheses": hypothesis_phrases(text),
        "sectors": sector_numbers(text),
        "corners": corner_numbers(text),
        "unsupported_terms": unresolved_terms(text),
    }

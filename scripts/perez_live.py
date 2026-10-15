"""Perez case against the LIVE NVIDIA model (no hardcoded answer).

1. Builds the deterministic answer via engine.ask().
2. Runs the independent critique workflow against the live model.
3. Asks the model one direct evidence-grounded question with the measured
   evidence pasted in, and checks it addresses sector 2, grounds numbers
   in the supplied evidence, and acknowledges uncertainty.

Never prints credentials. Exit 0 only if all live checks pass.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def load_env():
    with open(ROOT / ".env") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


def main():
    load_env()
    from racewise.agent.provider import NvidiaNimProvider, ProviderUnavailable
    from racewise.data.historical.canonical_queries import get_canonical_queries
    from racewise.question_engine.engine import ask
    from racewise.agent.critique import run_critique, should_critique

    provider = NvidiaNimProvider(
        model_id="openai/gpt-oss-20b",
        api_key=os.environ["NVIDIA_API_KEY"],
        base_url=os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        temperature=0.2,
        max_tokens=4096,
        timeout_seconds=90.0,
    )

    # 1. Deterministic answer (no model involved)
    out = ask(
        get_canonical_queries(), "why did perez lose time in sector 2",
        context={"driver_a": "max-verstappen", "driver_b": "sergio-perez",
                 "season": 2023, "round": 1, "lap_number": 6, "sector": 2},
    )
    answer = out.get("answer") or {}
    print(f"deterministic status: {out.get('status')}")

    # 2. Live independent critique
    fire, reason = should_critique(answer)
    print(f"critique gate: {fire} ({reason})")
    if fire:
        evidence_ids = [str(e.get("evidence_id") or e.get("id") or "")
                        for e in (answer.get("evidence_ledger") or [])]
        result = run_critique(provider, answer, evidence_ids)
        print(f"critique verdict: {result.verdict} "
              f"({len(result.findings)} findings, {result.iterations} call(s), "
              f"{result.latency_ms}ms)")
        print(f"critique reason: {result.reason[:160]}")
    else:
        print("critique not justified; skipping live critique call")

    # 3. Direct evidence-grounded question
    evidence_block = (
        "Measured lap delta (B minus A): +0.732 s. "
        "Sector deltas: S1 -0.065 s, S2 +0.411 s, S3 +0.386 s. "
        "Telemetry-window gross slower-phase exposure: 4.049 s (non-additive). "
        "Signed net telemetry estimate: 3.08 s. "
        "Unexplained residual: 0.464 s. "
        "Worst window: speed deficit -27.07 km/h, throttle delta -17.19%, "
        "brake fraction delta 0.05."
    )
    try:
        resp = provider.respond([
            {"role": "system", "content": (
                "You are a Formula 1 engineering assistant. Use ONLY the "
                "evidence below. Distinguish measured facts from estimates. "
                "State what is unresolved.")},
            {"role": "user", "content": (
                f"EVIDENCE: {evidence_block}\n"
                "QUESTION: Why did Perez lose time in sector 2? Answer in "
                "under 120 words, citing the measured numbers.")},
        ])
    except ProviderUnavailable as exc:
        print(f"LIVE CALL FAILED: {exc}")
        return 1
    text = resp.content or ""
    import unicodedata
    norm = unicodedata.normalize("NFKC", text)
    safe_preview = text[:400].encode("ascii", "backslashreplace").decode("ascii")
    print(f"live answer ({len(text)} chars): {safe_preview!r}")
    lowered = norm.lower()

    checks = {
        "addresses sector 2": "sector 2" in lowered,
        "grounds measured delta": "0.732" in norm or "0.73" in norm,
        "grounds sector-2 delta": "0.411" in norm or "0.41" in norm,
        "acknowledges uncertainty": any(
            w in lowered for w in
            ("unresolved", "uncertain", "residual", "unexplained", "estimate")),
        "usage captured": bool(resp.usage),
    }
    for name, ok in checks.items():
        print(f"  [{'OK' if ok else 'FAIL'}] {name}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())

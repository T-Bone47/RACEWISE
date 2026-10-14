"""End-to-end Perez answer via the question-engine ask() path."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from racewise.data.historical.canonical_queries import get_canonical_queries
from racewise.question_engine.engine import ask

out = ask(
    get_canonical_queries(),
    "why did perez lose time in sector 2",
    context={"driver_a": "max-verstappen", "driver_b": "sergio-perez",
             "season": 2023, "round": 1, "lap_number": 6, "sector": 2},
)
ans = out.get("answer") or {}
print("status:", out.get("status"), "| answer_status:", ans.get("status"))
for o in (ans.get("observations") or [])[:10]:
    print(f"  [{o.get('claim_class')}] {o.get('statement')}: {o.get('value')} {o.get('unit')}")
print("--- residuals ---")
for r in (ans.get("residuals") or [])[:3]:
    print(f"  {r.get('value')} :: {(r.get('statement') or '')[:60]}")
print("--- spatial ---")
for s in (ans.get("spatial") or [])[:4]:
    print(f"  {s.get('scope')}: measured={s.get('measured_delta_s')} "
          f"tel_est={s.get('telemetry_estimated_loss_s')}")
print("--- calculations (mechanism evidence) ---")
for c in (ans.get("calculations") or [])[:12]:
    print(f"  [{c.get('claim_class')}] {c.get('statement')}: "
          f"{c.get('value', c.get('detail'))} {c.get('unit') or ''}"
          f" | hyp={c.get('hypothesis_id')} cap={c.get('capability_id')}")
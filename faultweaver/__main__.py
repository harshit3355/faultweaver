"""CLI: run the benchmark, or print the Diagnostic Witness Graph for one catalogue incident."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import bench as bench_mod
from . import rca
from .sim import load_scenarios, simulate


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m faultweaver", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bench", help="run catalogue + sweep, write reports/benchmark.{json,md}")
    b.add_argument("--seed", type=int, default=7)
    b.add_argument("--per-level", type=int, default=60)
    b.add_argument("--out", default="reports")
    e = sub.add_parser("explain", help="investigate one catalogue incident and print its witness graph")
    e.add_argument("incident")
    e.add_argument("--seed", type=int, default=7)
    e.add_argument("--tau", type=float, default=rca.TAU)
    a = ap.parse_args(argv)

    if a.cmd == "explain":
        spec = next((s for s in load_scenarios() if s["id"].startswith(a.incident)), None)
        if spec is None:
            ap.error(f"unknown incident {a.incident}")
        inc = simulate(spec, a.seed)
        r = rca.investigate(inc, a.tau)
        h = r["hypothesis"]
        print(json.dumps({"incident": spec["id"], "symptom": "SLO alert at frontend",
                          "hypothesis": {"cause": h.service, "fault": h.fault, "rivals": h.rivals,
                                         "propagation_path": h.path, "proposed_remediation": h.action},
                          "decision": r["decision"], "probes_run": r["probes"], "witness_graph": r["card"],
                          "ground_truth": {"remediation": inc.remediation}}, indent=2))
        return 0

    rep = bench_mod.bench(a.seed, a.per_level)
    rep["provenance"] = bench_mod.provenance(a.seed)
    for m, x in rep["sweep"]["summary"].items():
        print(f"{m:18s} top1 {x['top1']:.3f}  fix {x['correct_fix']:.3f}  unsafe {x['unsafe']:.3f}  esc {x['escalated']:.3f}")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "benchmark.json").write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8", newline="\n")
    (out / "benchmark.md").write_text(bench_mod.markdown(rep), encoding="utf-8", newline="\n")
    print(f"wrote {out / 'benchmark.json'} and {out / 'benchmark.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

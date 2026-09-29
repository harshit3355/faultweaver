"""Benchmark: RCA accuracy, unsafe remediations and escalations for FAULTWEAVER vs baselines.

Two synthetic workloads: the hand-labelled catalogue (scenarios/incidents.json) and a seeded random
sweep at 0/10/20/30% blind-spot rates. A remediation is *correct* only if both the action and the
target match the ground truth; any other action is *unsafe*. Escalating is neither.
"""
from __future__ import annotations

import datetime
import hashlib
import platform
import subprocess
import sys
from collections import Counter

from . import rca
from .sim import ROOT, SCENARIOS, load_scenarios, simulate, sweep_specs

METHODS = ("anomaly_pagerank", "log_reader", "blind_unaware", "gala_like", "confidence_gate",
           "dwc_no_probes", "dwc_no_penalties", "faultweaver")
LABELS = {"anomaly_pagerank": "Graph-only anomaly ranking (personalised PageRank), act on top-1",
          "log_reader": "Log-only reader (stand-in for LLM-only RCA, no LLM run), act on top-1",
          "blind_unaware": "Blind-spot-unaware graph agent, act on top-1",
          "gala_like": "GALA-like graph-constrained agent without DWC, act on top-1",
          "confidence_gate": "Same agent + gate on its own ranking confidence",
          "dwc_no_probes": "DWC gate, escalate instead of probing (ablation)",
          "dwc_no_penalties": "DWC without independence/blind-spot/ambiguity penalties (ablation)",
          "faultweaver": "**FAULTWEAVER: DWC gate + falsifying probes**"}
CONF_GRID = [round(.5 + i / 100, 2) for i in range(50)]
TAU_GRID = (.4, .5, .6, .7, .8)


def _outcome(inc, ranking, decision, action, probes=0, score=None) -> dict:
    root, fault = inc.spec["root"], inc.spec["fault"]
    top = [h.service for h in ranking[:3]]
    return {"id": inc.spec["id"], "decision": decision, "action": list(action) if action else None,
            "correct": action == inc.remediation, "unsafe": action is not None and action != inc.remediation,
            "top1": top[0] == root, "top3": root in top,
            "top1_fault": ranking[0].service == root and ranking[0].fault == fault,
            "probes": probes, "score": score}


def run_method(m: str, inc, tau: float = rca.TAU, tau_conf: float = .8) -> dict:
    if m in ("dwc_no_probes", "dwc_no_penalties", "faultweaver"):
        r = rca.investigate(inc, tau, penalties=m != "dwc_no_penalties", budget=0 if m == "dwc_no_probes" else 3)
        return _outcome(inc, r["ranking"], r["decision"], r["action"], len(r["probes"]), r["dwc"])
    ranking = {"anomaly_pagerank": rca.pagerank, "log_reader": rca.log_reader,
               "blind_unaware": lambda o: rca.rank(o, blind_aware=False)}.get(m, rca.rank)(inc.obs)
    if m == "confidence_gate":
        c = rca.confidence(ranking)
        return _outcome(inc, ranking, "act" if c >= tau_conf else "escalate",
                        ranking[0].action if c >= tau_conf else None, score=round(c, 4))
    return _outcome(inc, ranking, "act", ranking[0].action)


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    acted = [r for r in rows if r["decision"] == "act"]
    rate = lambda k, xs=rows: round(sum(r[k] for r in xs) / len(xs), 4) if xs else None
    return {"n": n, "top1": rate("top1"), "top3": rate("top3"), "top1_with_fault": rate("top1_fault"),
            "correct_fix": rate("correct"), "unsafe": rate("unsafe"), "unsafe_n": sum(r["unsafe"] for r in rows),
            "escalated": round(sum(r["decision"] == "escalate" for r in rows) / n, 4),
            "unsafe_given_act": rate("unsafe", acted), "mean_probes": round(sum(r["probes"] for r in rows) / n, 3)}


def calibration(pairs: list[tuple[float, bool]]) -> dict:
    """Reliability bins and Brier score of a [0,1] score used as P(top hypothesis and fault are right)."""
    bins = []
    for lo in (0, .2, .4, .6, .8):
        xs = [(s, c) for s, c in pairs if lo <= s < lo + .2 or (lo == .8 and s == 1)]
        bins.append({"bin": f"[{lo:.1f}, {lo + .2:.1f})", "n": len(xs),
                     "mean_score": round(sum(s for s, _ in xs) / len(xs), 3) if xs else None,
                     "accuracy": round(sum(c for _, c in xs) / len(xs), 3) if xs else None})
    return {"brier": round(sum((s - c) ** 2 for s, c in pairs) / len(pairs), 4), "bins": bins}


ROBUST = ("gala_like", "confidence_gate", "dwc_no_penalties", "faultweaver")


def robustness(seed: int, per_level: int, tau_conf: float) -> dict:
    """The sweep's headline comparison on independent seeds (catalogue and curve are not rerun)."""
    incs = [simulate(s, seed) for s in sweep_specs(seed, per_level)]
    return {m: summarize([run_method(m, i, tau_conf=tau_conf) for i in incs]) for m in ROBUST}


def bench(seed: int, per_level: int = 60, extra_seeds: int = 4) -> dict:
    catalogue = [simulate(s, seed) for s in load_scenarios()]
    sweep = [simulate(s, seed) for s in sweep_specs(seed, per_level)]

    base = {m: [run_method(m, i) for i in sweep] for m in METHODS if m != "confidence_gate"}
    target = summarize(base["faultweaver"])["escalated"]
    # compare with a confidence gate that escalates as often as FAULTWEAVER does
    conf = [rca.confidence(rca.rank(i.obs)) for i in sweep]
    tau_conf = min(CONF_GRID, key=lambda t: (abs(sum(c < t for c in conf) / len(conf) - target), -t))
    base["confidence_gate"] = [run_method("confidence_gate", i, tau_conf=tau_conf) for i in sweep]
    cat = {m: [run_method(m, i, tau_conf=tau_conf) for i in catalogue] for m in METHODS}

    levels = sorted({i.spec["blind_level"] for i in sweep})
    by_level = {f"{int(lv * 100)}%": {m: summarize([r for r, i in zip(base[m], sweep) if i.spec["blind_level"] == lv])
                                      for m in METHODS} for lv in levels}
    curve = {m: {str(t): summarize([run_method(m, i, tau=t) for i in sweep])
                 for t in TAU_GRID} for m in ("faultweaver", "dwc_no_probes", "dwc_no_penalties")}
    curve["confidence_gate"] = {str(t): summarize([run_method("confidence_gate", i, tau_conf=t) for i in sweep])
                                for t in (.5, .55, .6, .65, .7, .75, .8)}

    def pre(i, penalties):
        h = rca.rank(i.obs)[0]
        return rca.dwc(i.obs, h, penalties)["dwc"], h.service == i.spec["root"] and h.fault == i.spec["fault"]
    calib = {"dwc_before_probes": calibration([pre(i, True) for i in sweep]),
             "dwc_no_penalties_before_probes": calibration([pre(i, False) for i in sweep]),
             "confidence": calibration([(c, pre(i, True)[1]) for c, i in zip(conf, sweep)]),
             "faultweaver_final_dwc": calibration([(r["score"], r["top1_fault"]) for r in base["faultweaver"]])}

    def tags(i):
        s = i.spec
        return [t for t, on in (("root blind", bool(set(s.get("blind", {}).get(s["root"], [])) & {"all", "metrics"})),
                                ("red herring", bool(s.get("red_herrings"))),
                                ("shared exporter", bool(s.get("shared_exporter"))),
                                ("faulty exporter", bool(s.get("faulty_exporter")))) if on] or ["none"]
    failures = [{**r, "fault": i.spec["fault"], "root": i.spec["root"], "blind_level": i.spec["blind_level"],
                 "conditions": tags(i)} for r, i in zip(base["faultweaver"], sweep) if r["unsafe"]]
    honest = next(i for i in catalogue if i.spec["id"].startswith("inc22"))
    relabeled = simulate({**honest.spec, "faulty_exporter": {**honest.spec["faulty_exporter"], "mislabeled": False}}, seed)
    return {"seed": seed, "tau": rca.TAU, "tau_conf_matched": tau_conf, "probe_budget": 3,
            "catalogue": {"incidents": len(catalogue), "summary": {m: summarize(cat[m]) for m in METHODS},
                          "rows": {i.spec["id"]: {"fault": i.spec["fault"], "root": i.spec["root"],
                                                  "negative": i.spec.get("negative", False),
                                                  "note": i.spec.get("note", ""),
                                                  **{m: cat[m][k] for m in METHODS}}
                                   for k, i in enumerate(catalogue)}},
            "sweep": {"incidents": len(sweep), "per_level": per_level,
                      "summary": {m: summarize(base[m]) for m in METHODS}, "by_blind_level": by_level,
                      "faultweaver_unsafe": failures},
            "operating_curve": curve, "calibration": calib,
            "seed_robustness": {str(seed + k): robustness(seed + k, per_level, tau_conf) for k in range(1, extra_seeds + 1)},
            "inc22_with_honest_provenance": run_method("faultweaver", relabeled)}


def provenance(seed: int) -> dict:
    def git(*args):
        r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else None
    sha = git("rev-parse", "HEAD")
    dirty = bool(git("status", "--porcelain", "--", "faultweaver", "scenarios"))
    return {"commit": (sha or "unknown") + ("-dirty" if dirty else ""),
            "command": "python -m faultweaver " + " ".join(sys.argv[1:]),
            "seed": seed, "python": platform.python_version(), "platform": platform.platform(),
            "dependencies": "none (stdlib only)",
            "scenarios_sha256": hashlib.sha256(SCENARIOS.read_bytes()).hexdigest()[:16],
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}


def _count(xs) -> str:
    c = Counter(xs)
    return ", ".join(f"{k} {v}" for k, v in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))) or "none"


def _pct(x):
    return "n/a" if x is None else f"{100 * x:.1f}%"


def _table(summary: dict) -> list[str]:
    L = ["| Method | Top-1 | Top-3 | Correct fix | **Unsafe action** | Escalated | Unsafe when acting | Probes/incident |",
         "|---|---|---|---|---|---|---|---|"]
    for m in METHODS:
        x = summary[m]
        L.append(f"| {LABELS[m]} | {_pct(x['top1'])} | {_pct(x['top3'])} | {_pct(x['correct_fix'])} | "
                 f"{_pct(x['unsafe'])} ({x['unsafe_n']}) | {_pct(x['escalated'])} | {_pct(x['unsafe_given_act'])} | {x['mean_probes']} |")
    return L


SYM = {"act": lambda r: "fix" if r["correct"] else "**UNSAFE**", "escalate": lambda r: "esc"}


def markdown(rep: dict) -> str:
    sw, cat = rep["sweep"], rep["catalogue"]
    L = ["# FAULTWEAVER benchmark: evidence-bounded remediation", "",
         "_Synthetic, simulated incidents. Every number below was produced by the command in the provenance section._", "",
         f"- DWC threshold tau = {rep['tau']}, probe budget {rep['probe_budget']}. The confidence gate's threshold "
         f"({rep['tau_conf_matched']}) is chosen so it escalates as often as FAULTWEAVER on the sweep.",
         "- *Correct fix*: right action on the right service. *Unsafe*: any other action. *Escalated*: handed to a human.",
         "- Top-1/Top-3 are service-level; for gated methods they refer to the ranking after any probes.", "",
         f"## Random sweep ({sw['incidents']} incidents, {sw['per_level']} per blind-spot level)", "", *_table(sw["summary"]),
         "", "## By blind-spot level (share of services with traces hidden; metrics/logs hidden at half that rate)", "",
         "| Level | Method | Top-1 | Correct fix | Unsafe | Escalated |", "|---|---|---|---|---|---|"]
    for lv, ms in sw["by_blind_level"].items():
        for m in ("gala_like", "confidence_gate", "dwc_no_penalties", "faultweaver"):
            x = ms[m]
            L.append(f"| {lv} | {m} | {_pct(x['top1'])} | {_pct(x['correct_fix'])} | {_pct(x['unsafe'])} | {_pct(x['escalated'])} |")
    L += ["", f"## Seed robustness (sweep regenerated with other seeds, same thresholds)", "",
          "| Seed | " + " | ".join(f"{m} unsafe / fix / esc" for m in ROBUST) + " |", "|---|" + "---|" * len(ROBUST)]
    for sd, ms in {str(rep["seed"]): {m: sw["summary"][m] for m in ROBUST}, **rep["seed_robustness"]}.items():
        L.append(f"| {sd} | " + " | ".join(f"{ms[m]['unsafe_n']} / {_pct(ms[m]['correct_fix'])} / {_pct(ms[m]['escalated'])}"
                                           for m in ROBUST) + " |")
    runs = [{m: sw["summary"][m] for m in ROBUST}, *rep["seed_robustness"].values()]
    L.append("| **total unsafe** | " + " | ".join(f"**{sum(r[m]['unsafe_n'] for r in runs)}** / "
                                             f"{sum(r[m]['n'] for r in runs)}" for m in ROBUST) + " |")
    L += ["", "Unsafe is a count out of each sweep's incidents.", "", "## Operating curve (sweep): unsafe vs escalation as the threshold moves", "",
          "| Gate | Threshold | Correct fix | Unsafe | Escalated | Probes/incident |", "|---|---|---|---|---|---|"]
    for m, pts in rep["operating_curve"].items():
        for t, x in pts.items():
            L.append(f"| {m} | {t} | {_pct(x['correct_fix'])} | {_pct(x['unsafe'])} | {_pct(x['escalated'])} | {x['mean_probes']} |")
    L += ["", "## Calibration (sweep): does the score predict that the top hypothesis and its fault type are right?", "",
          "| Score | Brier | " + " | ".join(b["bin"] for b in rep["calibration"]["confidence"]["bins"]) + " |",
          "|---|---|" + "---|" * 5]
    for k, c in rep["calibration"].items():
        L.append(f"| {k} | {c['brier']} | " + " | ".join(
            f"{b['accuracy']} (n={b['n']})" if b["n"] else "-" for b in c["bins"]) + " |")
    L += ["", "Cells: observed accuracy (count). DWC is a coverage score, not a probability; the table shows how far "
              "it is from one.", "",
          f"## Hand-labelled catalogue ({cat['incidents']} incidents)", "", *_table(cat["summary"]), "",
          "| Incident | Truth | " + " | ".join(METHODS) + " |", "|---|---|" + "---|" * len(METHODS)]
    for k, r in cat["rows"].items():
        L.append(f"| {k}{' (negative)' if r['negative'] else ''} | {r['fault']} @ {r['root']} | "
                 + " | ".join(SYM[r[m]["decision"]](r[m]) for m in METHODS) + " |")
    neg = [(k, r) for k, r in cat["rows"].items() if r["faultweaver"]["unsafe"]]
    L += ["", "## Where FAULTWEAVER fails", "", "Catalogue incidents where the gate let an unsafe action through:", ""]
    L += [f"- `{k}` (DWC {r['faultweaver']['score']}): {r['note']}. Action taken: `{r['faultweaver']['action']}`."
          for k, r in neg] or ["- none"]
    h = rep["inc22_with_honest_provenance"]
    L += ["", f"- Control for `inc22`: the same incident with the faulty collector declared as one shared source ends in "
              f"`{h['decision']}` (correct: {h['correct']}, DWC {h['score']}).", "",
          f"Sweep incidents where FAULTWEAVER acted unsafely: {len(sw['faultweaver_unsafe'])}. "
          f"By true fault: {_count(f['fault'] for f in sw['faultweaver_unsafe'])}. "
          f"By condition: {_count(c for f in sw['faultweaver_unsafe'] for c in f['conditions'])}.", "",
          "| Incident | Truth | Action taken | DWC | Probes | Conditions |", "|---|---|---|---|---|---|"]
    L += [f"| {f['id']} | {f['fault']} @ {f['root']} | {f['action']} | {f['score']} | {f['probes']} | "
          f"{', '.join(f['conditions'])} |" for f in sw["faultweaver_unsafe"]]
    L += ["", "## Provenance", "", *(f"- {k}: `{v}`" for k, v in rep["provenance"].items()), ""]
    return "\n".join(L)

"""Hypothesis generation, Diagnostic Witness Coverage (DWC), the remediation gate, and baselines.

Nothing here reads ground truth. Every function sees only the observation list (plus probe
results it asked for) and the public topology.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .sim import CALLERS, DEPS, FAULTS, LINK, MATES, NODE, PROBES, ROOTS, SYMPTOM, Incident, Obs, probe, probeable

REL = {"metric": .7, "log": .6, "trace": .8, "event": .9, "probe": .9}  # how much one witness can prove
ANOMALY = .3  # a signal below this is not a witness
OWN = ("latency", "errors", "cpu", "mem", "origin", "deploy", "config")
# responder-side fault signatures over features; *_in = what callers say about the service
SIG = {"resource_exhaustion": {"mem": 1, "latency": .6, "origin": .4, "upstream_in": .5, "span_in": .5},
       "bad_deploy": {"deploy": 1, "errors": .8, "origin": .8, "upstream_in": .5},
       "config_error": {"config": 1, "errors": .8, "origin": .8, "upstream_in": .5},
       "dependency_latency": {"latency": 1, "upstream_in": .8, "span_in": .8},
       "network_partition": {"refused_in": 1, "span_in": .8},
       "noisy_neighbour": {"cpu": 1, "coloc": .8}}
KEY = {f: [c for c, w in sig.items() if w >= .8] for f, sig in SIG.items()}  # channels that must be witnessed
# the signal that tells this fault apart from the others; unobservable -> the remediation type is a guess
DEFINING = {"resource_exhaustion": ("mem",), "bad_deploy": ("deploy",), "config_error": ("config",),
            "dependency_latency": ("latency", "upstream_in"), "network_partition": ("refused_in",),
            "noisy_neighbour": ("cpu",)}
PLAUSIBLE = {s: [f for f in SIG if s in ROOTS[f]] or list(SIG) for s in NODE}  # the known fault model
BLIND_PENALTY = .5  # cause has a dependency nobody can see into: a deeper cause cannot be ruled out
AMBIGUITY_PENALTY = .5  # a defining signal of the fault or of a close rival is unobservable
RIVAL = .8  # fault classes whose signature fit is within this ratio of the best are rivals
TAU = .6


@dataclass(frozen=True)
class Hyp:
    service: str
    fault: str
    score: float
    path: tuple[str, ...] | None  # cause ... SYMPTOM
    rivals: tuple[str, ...] = ()  # other fault classes the evidence does not rule out

    @property
    def action(self) -> tuple[str, str]:
        return FAULTS[self.fault][2], self.service


def values(obs: list[Obs]) -> dict:
    """Latest value per (service, channel, target); an active probe overrides passive telemetry."""
    return {(o.service, o.channel, o.target): o.value for o in sorted(obs, key=lambda o: o.kind == "probe")}


def features(v: dict, s: str) -> dict:
    """Observed features only: an unobservable signal is unknown, not zero."""
    f = {ch: v[s, ch, None] for ch in OWN if (s, ch, None) in v}
    for ch in LINK:
        xs = [v[c, ch, s] for c in CALLERS[s] if (c, ch, s) in v]
        if xs:
            f[ch + "_in"] = max(xs)
    xs = [v[m, "cpu", None] for m in MATES[s] if (m, "cpu", None) in v]
    if xs:
        f["coloc"] = max(xs)
    return f


def classify(f: dict, s: str) -> tuple[str, tuple[str, ...]]:
    """Best-fitting plausible fault (cosine to its signature over observed features) and close rivals."""
    norm = math.sqrt(sum(x * x for x in f.values())) or 1

    def cos(sig):
        dims = [c for c in sig if c in f]
        return sum(sig[c] * f[c] for c in dims) / (norm * math.sqrt(sum(sig[c] ** 2 for c in dims))) if dims else 0.0

    fit = {k: cos(SIG[k]) for k in PLAUSIBLE[s]}
    order = sorted(fit, key=lambda k: (-fit[k], k))
    return order[0], tuple(k for k in order[1:] if fit[k] >= RIVAL * fit[order[0]])


def link(v: dict, cause: str, victim: str) -> float:
    if cause in DEPS[victim]:
        return max(v.get((victim, ch, cause), 0.0) for ch in LINK)
    return v.get((victim, "cpu", None), 0.0)  # co-located: the victim is CPU-throttled


def paths(s: str, fault: str) -> list[tuple[str, ...]]:
    out, stack = [], [(s,)]
    while stack:
        p = stack.pop()
        if p[-1] == SYMPTOM:
            out.append(p)
            continue
        nxt = CALLERS[p[-1]] + (MATES[s] if len(p) == 1 and fault == "noisy_neighbour" else [])
        stack += [p + (n,) for n in nxt if n not in p]
    return out


def rank(obs: list[Obs], blind_aware: bool = True) -> list[Hyp]:
    """Deterministic graph-constrained hypothesis generator (stands in for an investigation agent)."""
    v = values(obs)
    seen_link = {(o.service, o.target) for o in obs if o.channel in LINK}
    own = {s: max(v.get((s, ch, None), 0.0) for ch in OWN) for s in NODE}
    cause_ev = {s: max(v.get((s, ch, None), 0.0) for ch in ("cpu", "mem", "origin", "deploy", "config")) for s in NODE}
    anomalous = {s for s in NODE if own[s] >= .4}
    hyps = []
    for s in NODE:
        ev = own[s]
        if blind_aware:
            ev = max(ev, max((link(v, s, c) for c in CALLERS[s]), default=0.0),
                     .7 * max((own[c] * (1 - cause_ev[c]) for c in CALLERS[s] if (c, s) not in seen_link), default=0.0))
        down = max((link(v, d, s) for d in DEPS[s]), default=0.0)
        reach, todo = set(), [s] + (MATES[s] if v.get((s, "cpu", None), 0) >= .5 else [])
        while todo:
            x = todo.pop()
            if x not in reach:
                reach.add(x)
                todo += CALLERS[x]
        explains = len((reach - {s}) & anomalous) / max(1, len(anomalous - {s}))
        fault, rivals = classify(features(v, s), s)
        ps = paths(s, fault)
        best = max(ps, key=lambda p: (sum(link(v, a, b) for a, b in zip(p, p[1:])) / max(1, len(p) - 1),
                                      -len(p), p)) if ps else None
        hyps.append(Hyp(s, fault, round(ev * (1 - .8 * down) * (.4 + .6 * explains), 4), best, rivals))
    return sorted(hyps, key=lambda h: (-h.score, h.service))


def _witnesses(obs: list[Obs], elem: tuple) -> list[Obs]:
    if elem[0] == "cause":
        _, s, chans = elem
        own = {c for c in chans if c in OWN}
        inc = {c[:-3] for c in chans if c.endswith("_in")}
        return [o for o in obs if (o.service == s and o.target is None and o.channel in own)
                or (o.target == s and o.channel in inc)
                or ("coloc" in chans and o.service in MATES[s] and o.channel == "cpu")]
    _, cause, victim = elem
    if cause in DEPS[victim]:
        return [o for o in obs if o.service == victim and o.target == cause and o.channel in LINK]
    return [o for o in obs if o.service == victim and o.channel == "cpu" and o.target is None]


def support(ws: list[Obs], independent: bool = True) -> float:
    """Noisy-OR over independence groups: signals through one exporter count once."""
    groups: dict = {}
    for i, o in enumerate(ws):
        g = o.source if independent else i
        groups[g] = max(groups.get(g, 0.0), o.value * REL[o.kind] if o.value >= ANOMALY else 0.0)
    return 1 - math.prod(1 - x for x in groups.values())


def dwc(obs: list[Obs], h: Hyp, penalties: bool = True) -> dict:
    """Diagnostic Witness Coverage of hypothesis h, with the witness breakdown (the DWG)."""
    if h.path is None:
        return {"dwc": 0.0, "reason": "no propagation path to the symptom", "elements": []}
    elems = [(("cause", h.service, tuple(KEY[h.fault])), 2.0)]
    elems += [(("link", a, b), 1.0) for a, b in zip(h.path, h.path[1:])]
    rows, num, den, contradicted = [], 0.0, 0.0, False
    for e, w in elems:
        ws = _witnesses(obs, e)
        sup = support(ws, independent=penalties)
        probed = [o.value for o in ws if o.kind == "probe"]
        if probed and max(probed) < ANOMALY:  # an active test looked and found nothing
            contradicted = True
        blind = not ws
        if penalties or not blind:  # without penalties, unobservable elements silently drop out
            num, den = num + w * sup, den + w
        rows.append({"element": list(e[1:]) if e[0] == "link" else [h.service, h.fault], "kind": e[0],
                     "weight": w, "support": round(sup, 3), "blind": blind,
                     "witnesses": [[o.service, o.channel, o.target, o.value, o.source] for o in ws if o.value >= ANOMALY]})
    coverage = num / den if den else 0.0
    falsifier = max((support(_witnesses(obs, ("link", d, h.service)), penalties) for d in DEPS[h.service]), default=0.0)
    seen = {(o.service, o.target) for o in obs if o.channel in LINK}
    unresolved = [d for d in DEPS[h.service] if (h.service, d) not in seen]
    pen = BLIND_PENALTY if penalties and unresolved else 0.0
    unseen = [f for f in (h.fault, *h.rivals) if not _witnesses(obs, ("cause", h.service, DEFINING[f]))]
    amb = AMBIGUITY_PENALTY if penalties and unseen else 0.0
    value = 0.0 if contradicted else coverage * (1 - falsifier) * (1 - pen) * (1 - amb)
    return {"dwc": round(value, 4), "coverage": round(coverage, 4), "falsifier": round(falsifier, 4),
            "blind_penalty": pen, "unresolved_dependencies": unresolved, "ambiguity_penalty": amb,
            "undiscriminated_faults": unseen, "contradicted_by_probe": contradicted, "elements": rows}


def next_probe(inc: Incident, h: Hyp, card: dict, done: set) -> tuple | None:
    """Cheapest falsifying test: look into unresolved dependencies first, then the weakest element."""
    want = [("dependency_check", h.service, d) for d in card.get("unresolved_dependencies", [])]
    want += [p for f in card.get("undiscriminated_faults", []) for c in DEFINING[f] for p in _probes_for(h.service, c)]
    for r in sorted(card["elements"], key=lambda r: -r["weight"] * (1 - r["support"])):
        if r["kind"] == "link":
            a, b = r["element"]
            want.append(("dependency_check", b, a) if a in DEPS[b] else ("resource_profile", b, None))
            continue
        want += [p for c in KEY[h.fault] for p in _probes_for(h.service, c)]
    return next((p for p in want if p not in done and probeable(inc.spec, *p)), None)


def _probes_for(s: str, c: str) -> list[tuple]:
    if c.endswith("_in"):
        return [("dependency_check", x, s) for x in CALLERS[s]]
    if c == "coloc":
        return [("resource_profile", m, None) for m in MATES[s]]
    return [(p, s, None) for p, chs in PROBES.items() if c in chs]  # e.g. error logs have no probe


def investigate(inc: Incident, tau: float = TAU, penalties: bool = True, budget: int = 3) -> dict:
    """FAULTWEAVER: act only when the top hypothesis' DWC >= tau, otherwise probe, then escalate."""
    obs, done = list(inc.obs), []
    while True:
        hyps = rank(obs)
        top, card = hyps[0], dwc(obs, hyps[0], penalties)
        if card["dwc"] >= tau:
            decision = "act"
            break
        p = next_probe(inc, top, card, set(done)) if len(done) < budget else None
        if p is None:
            decision = "escalate"
            break
        done.append(p)
        obs += probe(inc, *p)
    return {"decision": decision, "action": top.action if decision == "act" else None, "ranking": hyps,
            "dwc": card["dwc"], "probes": done, "card": card, "hypothesis": top}


# ---- baselines -------------------------------------------------------------------------------

def pagerank(obs: list[Obs]) -> list[Hyp]:
    """Graph-only anomaly ranking (MicroRCA-style personalised PageRank over metric anomalies)."""
    v = values(obs)
    a = {s: max(v.get((s, ch, None), 0.0) for ch in ("latency", "errors", "cpu", "mem")) + 1e-3 for s in NODE}
    tot = sum(a.values())
    pers = {s: a[s] / tot for s in NODE}
    r = dict(pers)
    for _ in range(50):
        new = {s: .15 * pers[s] for s in NODE}
        for s in NODE:
            outs = [(d, a[d]) for d in DEPS[s]] + [(s, a[s])]  # walk toward anomalous dependencies
            z = sum(w for _, w in outs)
            for d, w in outs:
                new[d] += .85 * r[s] * w / z
        r = new
    return _as_hyps(v, r)


def log_reader(obs: list[Obs]) -> list[Hyp]:
    """Stand-in for 'LLM-only RCA': reads logs only (own errors + who is blamed), no graph, no metrics.
    No LLM is run; this is a deterministic text-evidence heuristic."""
    v = values(obs)
    return _as_hyps(v, {s: max([v.get((s, "origin", None), 0.0)] + [v.get((c, ch, s), 0.0) for c in CALLERS[s]
                                                                    for ch in ("upstream", "refused")])
                        for s in NODE})


def _as_hyps(v: dict, score: dict) -> list[Hyp]:
    hyps = []
    for s in NODE:
        f, rivals = classify(features(v, s), s)
        ps = paths(s, f)
        hyps.append(Hyp(s, f, round(score[s], 4), min(ps, key=len) if ps else None, rivals))
    return sorted(hyps, key=lambda h: (-h.score, h.service))


def confidence(hyps: list[Hyp]) -> float:
    return hyps[0].score / (hyps[0].score + hyps[1].score) if hyps[0].score + hyps[1].score else 0.5

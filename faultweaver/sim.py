"""Deterministic, seeded microservice incident simulator (synthetic data).

A fault is injected at a root service, its symptoms propagate to callers (and, for a noisy
neighbour, to co-located services), and an observation layer decides what a responder can see:
blind spots remove signals, shared exporters collapse several signals into one source, and a
faulty exporter adds correlated evidence that is wrong. Probes read the ground truth directly,
subject to per-incident probe permissions.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from graphlib import TopologicalSorter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = ROOT / "scenarios" / "incidents.json"

NODE = {"frontend": "n1", "api-gateway": "n1", "auth": "n1",
        "cart": "n2", "checkout": "n2", "payment": "n2", "queue": "n2",
        "catalog": "n3", "search": "n3", "recommender": "n3",
        "assistant": "n4", "llm-gateway": "n4", "embedding": "n4", "vector-store": "n4", "worker": "n4",
        "db": "n5", "cache": "n5", "llm-provider": "external"}
DEPS = {"frontend": ["api-gateway"],
        "api-gateway": ["auth", "cart", "checkout", "catalog", "search", "recommender", "assistant"],
        "auth": ["db", "cache"], "cart": ["cache", "db"], "checkout": ["cart", "payment", "queue"],
        "payment": ["db"], "catalog": ["db", "cache"], "search": ["embedding", "vector-store"],
        "recommender": ["catalog", "vector-store"], "assistant": ["llm-gateway", "vector-store", "embedding"],
        "llm-gateway": ["llm-provider"], "worker": ["queue", "db"],
        "embedding": [], "vector-store": [], "queue": [], "db": [], "cache": [], "llm-provider": []}
CALLERS = {s: sorted(c for c, ds in DEPS.items() if s in ds) for s in NODE}
EXTERNAL = {"llm-provider"}  # third party: emits no telemetry of its own, cannot be profiled
MATES = {s: sorted(m for m in NODE if m != s and NODE[m] == NODE[s] and s not in EXTERNAL) for s in NODE}
SYMPTOM = "frontend"  # the SLO alert fires here
TOPO = list(TopologicalSorter(DEPS).static_order())  # dependencies before their callers

KIND = {"latency": "metric", "errors": "metric", "cpu": "metric", "mem": "metric", "origin": "log",
        "upstream": "log", "refused": "log", "span": "trace", "deploy": "event", "config": "event"}
LINK = ("span", "upstream", "refused")  # (caller, channel, callee): evidence that the callee hurts the caller
BLIND_KINDS = {"metric": "metrics", "log": "logs", "trace": "traces", "event": "events"}

# fault -> (signature at the root, what callers log, safe remediation, impact on consumers)
FAULTS = {
    "resource_exhaustion": ({"mem": .9, "latency": .7, "errors": .4, "origin": .5, "cpu": .4}, "upstream", "scale_out", .9),
    "bad_deploy": ({"deploy": 1.0, "errors": .9, "origin": .9, "latency": .3}, "upstream", "rollback", .9),
    "config_error": ({"config": 1.0, "errors": .8, "origin": .8, "latency": .2}, "upstream", "revert_config", .85),
    "dependency_latency": ({"latency": .9, "cpu": .3}, "upstream", "failover", .9),
    "network_partition": ({}, "refused", "reroute", .95),
    "noisy_neighbour": ({"cpu": 1.0, "latency": .2}, "upstream", "throttle", .75),
}
DECAY = .9  # impact kept per hop upstream
APP = ["api-gateway", "auth", "cart", "checkout", "payment", "catalog", "search", "recommender", "assistant",
       "llm-gateway", "embedding"]
ROOTS = {"resource_exhaustion": APP + ["db", "cache", "vector-store", "queue"],
         "bad_deploy": APP, "config_error": APP,
         "dependency_latency": ["db", "cache", "vector-store", "queue", "embedding", "llm-provider"],
         "network_partition": APP[1:] + ["db", "cache", "vector-store", "queue", "llm-provider"],
         "noisy_neighbour": ["worker", "cache", "db", "embedding"]}
PROBES = {"synthetic_check": ("latency", "errors"), "resource_profile": ("cpu", "mem"),
          "change_history": ("deploy", "config"), "dependency_check": LINK}


@dataclass(frozen=True)
class Obs:
    service: str
    channel: str
    value: float
    source: str  # independence group: the exporter/pipeline the signal came through
    target: str | None = None

    @property
    def kind(self) -> str:
        return "probe" if self.source.startswith("probe:") else KIND[self.channel]


@dataclass
class Incident:
    spec: dict
    truth: dict
    obs: list[Obs]

    @property
    def remediation(self) -> tuple[str, str]:
        return FAULTS[self.spec["fault"]][2], self.spec["root"]


def load_scenarios(path: Path = SCENARIOS) -> list[dict]:
    specs = json.loads(path.read_text(encoding="utf-8"))["incidents"]
    for s in specs:
        if s["root"] not in ROOTS[s["fault"]]:
            raise ValueError(f"{s['id']}: {s['fault']} cannot be rooted at {s['root']}")
        for svc in [*s.get("blind", {}), *(r["service"] for r in s.get("red_herrings", []))]:
            if svc not in NODE:
                raise ValueError(f"{s['id']}: unknown service {svc}")
    return specs


def simulate(spec: dict, seed: int) -> Incident:
    rng = random.Random(f"{seed}:{spec['id']}")
    u = lambda lo=.85: rng.uniform(lo, 1.0)
    truth: dict = {}

    def bump(s, ch, v, t=None):
        truth[s, ch, t] = round(max(truth.get((s, ch, t), 0.0), min(1.0, v)), 3)

    for s in NODE:
        for ch in ("latency", "errors", "cpu", "mem", "origin"):
            bump(s, ch, rng.uniform(0, .15))
        bump(s, "deploy", 0)
        bump(s, "config", 0)
        for d in DEPS[s]:
            for ch in LINK:
                bump(s, ch, rng.uniform(0, .1), d)

    root, fault = spec["root"], spec["fault"]
    impact: dict[str, float] = {}

    def inject(s, f, strength):
        for ch, v in FAULTS[f][0].items():
            bump(s, ch, v * strength * u(.9))

    inject(root, fault, 1.0)
    if fault == "noisy_neighbour":  # the hog throttles its node-mates, which then hurt their callers
        for m in MATES[root]:
            bump(m, "cpu", .6 * u())
            bump(m, "latency", .7 * u())
            impact[m] = FAULTS[fault][3]
    else:
        impact[root] = FAULTS[fault][3]
    for rh in spec.get("red_herrings", []):  # a real but non-causal anomaly
        inject(rh["service"], rh["fault"], rh.get("strength", .85))
        if rh.get("propagate"):
            impact[rh["service"]] = max(impact.get(rh["service"], 0), rh["propagate"])
    for s in TOPO:
        for d in DEPS[s]:
            i = impact.get(d, 0)
            if i <= 0:
                continue
            bump(s, "span", i * u(), d)
            bump(s, "refused" if d == root and fault == "network_partition" else "upstream", i * u(.8), d)
            bump(s, "latency", i * .9 * u())
            bump(s, "errors", i * .8 * u())
            impact[s] = max(impact.get(s, 0), i * DECAY)
    return Incident(spec, truth, observe(spec, truth))


def hidden(spec: dict, s: str, kind: str) -> bool:
    b = spec.get("blind", {}).get(s, ())
    return s in EXTERNAL or "all" in b or BLIND_KINDS[kind] in b


def observe(spec: dict, truth: dict) -> list[Obs]:
    shared = set(spec.get("shared_exporter", []))
    fx = spec.get("faulty_exporter")
    if fx and not fx.get("mislabeled"):
        shared.add(fx["node"])
    out = []
    for (s, ch, t), v in sorted(truth.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2] or "")):
        kind = KIND[ch]
        # a span needs both ends instrumented; an untraced callee leaves a hole in the call graph
        if hidden(spec, s, kind) or (kind == "trace" and hidden(spec, t, kind)):
            continue
        n = NODE[s]
        if fx and n == fx["node"] and ch in ("latency", "errors", "origin", "span", "upstream"):
            v = round(min(1.0, v + fx["value"]), 3)  # the collector itself is broken: correlated, wrong
        src = ("cd-audit" if kind == "event" else f"collector:{n}" if n in shared
               else {"metric": f"prom:{n}", "log": f"logs:{n}", "trace": "otel"}[kind])
        out.append(Obs(s, ch, v, src, t))
    return out


def probeable(spec: dict, name: str, s: str, t: str | None = None) -> bool:
    if s in EXTERNAL or s in spec.get("unprobeable", []) or (t and t in spec.get("unprobeable", [])):
        return False
    return name == "dependency_check" or t is None


def probe(inc: Incident, name: str, s: str, t: str | None = None) -> list[Obs]:
    """Active measurement: bypasses exporters and blind spots, returns ground truth."""
    if not probeable(inc.spec, name, s, t):
        return []
    return [Obs(s, ch, inc.truth.get((s, ch, t), 0.0), f"probe:{name}", t) for ch in PROBES[name]]


def sweep_specs(seed: int, per_level: int = 60, levels=(0.0, .1, .2, .3)) -> list[dict]:
    """Random incidents at increasing blind-spot rates (share of services with traces hidden)."""
    rng = random.Random(seed)
    nodes = sorted(set(NODE.values()) - {"external"})
    specs = []
    for level in levels:
        for i in range(per_level):
            fault = rng.choice(sorted(FAULTS))
            root = rng.choice(ROOTS[fault])
            blind = {}
            for s in NODE:
                kinds = [k for k, p in (("traces", level), ("metrics", level / 2), ("logs", level / 2),
                                        ("events", level / 3)) if rng.random() < p]
                if kinds:
                    blind[s] = kinds
            spec = {"id": f"sweep-{int(level * 100):02d}-{i:02d}", "fault": fault, "root": root,
                    "blind": blind, "blind_level": level}
            if rng.random() < .3:
                spec["red_herrings"] = [{"service": rng.choice(sorted(set(APP + ["cache", "db"]) - {root})),
                                         "fault": rng.choice(["resource_exhaustion", "bad_deploy"])}]
            if rng.random() < .2:
                spec["shared_exporter"] = [rng.choice(nodes)]
            if rng.random() < .1:
                spec["faulty_exporter"] = {"node": rng.choice(nodes), "value": .6}
            specs.append(spec)
    return specs

import pytest

from faultweaver import bench, rca
from faultweaver.sim import FAULTS, NODE, Obs, load_scenarios, simulate

CATALOGUE = {s["id"][:5]: s for s in load_scenarios()}


def test_signals_through_one_exporter_count_once():
    a = Obs("db", "latency", .9, "collector:n5")
    b = Obs("db", "errors", .9, "collector:n5")
    c = Obs("db", "origin", .9, "logs:n5")
    assert rca.support([a, b]) == pytest.approx(rca.support([a]))
    assert rca.support([a, c]) > rca.support([a, b])
    assert rca.support([a, b], independent=False) > rca.support([a, b])  # the ablation double-counts


def test_signals_below_the_anomaly_threshold_are_not_witnesses():
    assert rca.support([Obs("db", "latency", rca.ANOMALY - .01, "prom:n5")]) == 0


def test_unobservable_dependency_blocks_the_victim_hypothesis():
    # cart cannot see into db (db dark, cart's logs missing): a deeper cause cannot be ruled out
    inc = simulate({"id": "t", "fault": "dependency_latency", "root": "db",
                    "blind": {"db": ["all"], "cart": ["logs"]}}, 7)
    h = next(h for h in rca.rank(inc.obs) if h.service == "cart")
    card = rca.dwc(inc.obs, h)
    assert card["unresolved_dependencies"] == ["db"] and card["blind_penalty"] == rca.BLIND_PENALTY
    assert rca.dwc(inc.obs, h, penalties=False)["blind_penalty"] == 0


def test_a_probe_that_finds_nothing_falsifies_the_hypothesis():
    inc = simulate(CATALOGUE["inc11"], 7)  # config error on auth with the change audit missing
    h = rca.rank(inc.obs)[0]
    assert h.action == ("rollback", "auth") and rca.dwc(inc.obs, h)["dwc"] < rca.TAU
    probed = inc.obs + [o for o in rca.probe(inc, "change_history", "auth")]
    assert rca.dwc(probed, h)["contradicted_by_probe"] and rca.dwc(probed, h)["dwc"] == 0
    assert rca.investigate(inc)["action"] == inc.remediation


def test_simulator_is_deterministic_and_labelled():
    specs = load_scenarios()
    assert len(specs) >= 20
    for s in specs:
        inc = simulate(s, 7)
        assert inc.obs == simulate(s, 7).obs
        assert inc.remediation[0] in {f[2] for f in FAULTS.values()} and inc.remediation[1] in NODE
    assert simulate(specs[0], 7).obs != simulate(specs[0], 8).obs


@pytest.mark.parametrize("key", ["inc19", "inc20"])
def test_gate_escalates_when_the_cause_is_hidden(key):
    inc = simulate(CATALOGUE[key], 7)
    assert bench.run_method("gala_like", inc)["unsafe"]
    assert rca.investigate(inc)["decision"] == "escalate"


def test_mechanism_reduces_unsafe_actions_on_the_catalogue():
    """Fails if the gate, the probes or the penalties stop doing their job."""
    incs = [simulate(s, 7) for s in load_scenarios()]
    unsafe = {m: sum(bench.run_method(m, i)["unsafe"] for i in incs)
              for m in ("gala_like", "dwc_no_penalties", "faultweaver")}
    assert unsafe["faultweaver"] < unsafe["dwc_no_penalties"] < unsafe["gala_like"]


def test_known_failures_stay_documented():
    # independently witnessed red herring with a hidden root, and mislabelled exporter provenance
    for key in ("inc21", "inc22"):
        assert CATALOGUE[key]["negative"]
        assert bench.run_method("faultweaver", simulate(CATALOGUE[key], 7))["unsafe"]


def test_bench_report_smoke():
    rep = bench.bench(7, per_level=3, extra_seeds=1)
    rep["provenance"] = bench.provenance(7)
    md = bench.markdown(rep)
    assert rep["sweep"]["incidents"] == 12 and "## Provenance" in md and "scenarios_sha256" in md

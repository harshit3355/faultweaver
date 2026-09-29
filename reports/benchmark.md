# FAULTWEAVER benchmark: evidence-bounded remediation

_Synthetic, simulated incidents. Every number below was produced by the command in the provenance section._

- DWC threshold tau = 0.6, probe budget 3. The confidence gate's threshold (0.52) is chosen so it escalates as often as FAULTWEAVER on the sweep.
- *Correct fix*: right action on the right service. *Unsafe*: any other action. *Escalated*: handed to a human.
- Top-1/Top-3 are service-level; for gated methods they refer to the ranking after any probes.

## Random sweep (240 incidents, 60 per blind-spot level)

| Method | Top-1 | Top-3 | Correct fix | **Unsafe action** | Escalated | Unsafe when acting | Probes/incident |
|---|---|---|---|---|---|---|---|
| Graph-only anomaly ranking (personalised PageRank), act on top-1 | 31.2% | 64.6% | 31.2% | 68.8% (165) | 0.0% | 68.8% | 0.0 |
| Log-only reader (stand-in for LLM-only RCA, no LLM run), act on top-1 | 75.8% | 80.4% | 75.0% | 25.0% (60) | 0.0% | 25.0% | 0.0 |
| Blind-spot-unaware graph agent, act on top-1 | 72.1% | 78.8% | 71.2% | 28.7% (69) | 0.0% | 28.7% | 0.0 |
| GALA-like graph-constrained agent without DWC, act on top-1 | 88.8% | 97.1% | 87.9% | 12.1% (29) | 0.0% | 12.1% | 0.0 |
| Same agent + gate on its own ranking confidence | 88.8% | 97.1% | 86.2% | 9.2% (22) | 4.6% | 9.6% | 0.0 |
| DWC gate, escalate instead of probing (ablation) | 88.8% | 97.1% | 68.8% | 3.8% (9) | 27.5% | 5.2% | 0.0 |
| DWC without independence/blind-spot/ambiguity penalties (ablation) | 90.0% | 97.1% | 89.2% | 5.4% (13) | 5.4% | 5.7% | 0.275 |
| **FAULTWEAVER: DWC gate + falsifying probes** | 90.0% | 97.1% | 90.0% | 4.6% (11) | 5.4% | 4.9% | 0.442 |

## By blind-spot level (share of services with traces hidden; metrics/logs hidden at half that rate)

| Level | Method | Top-1 | Correct fix | Unsafe | Escalated |
|---|---|---|---|---|---|
| 0% | gala_like | 90.0% | 90.0% | 10.0% | 0.0% |
| 0% | confidence_gate | 90.0% | 90.0% | 8.3% | 1.7% |
| 0% | dwc_no_penalties | 90.0% | 90.0% | 5.0% | 5.0% |
| 0% | faultweaver | 90.0% | 90.0% | 5.0% | 5.0% |
| 10% | gala_like | 85.0% | 85.0% | 15.0% | 0.0% |
| 10% | confidence_gate | 85.0% | 83.3% | 10.0% | 6.7% |
| 10% | dwc_no_penalties | 86.7% | 86.7% | 5.0% | 8.3% |
| 10% | faultweaver | 86.7% | 86.7% | 5.0% | 8.3% |
| 20% | gala_like | 91.7% | 90.0% | 10.0% | 0.0% |
| 20% | confidence_gate | 91.7% | 86.7% | 6.7% | 6.7% |
| 20% | dwc_no_penalties | 91.7% | 90.0% | 3.3% | 6.7% |
| 20% | faultweaver | 91.7% | 91.7% | 1.7% | 6.7% |
| 30% | gala_like | 88.3% | 86.7% | 13.3% | 0.0% |
| 30% | confidence_gate | 88.3% | 85.0% | 11.7% | 3.3% |
| 30% | dwc_no_penalties | 91.7% | 90.0% | 8.3% | 1.7% |
| 30% | faultweaver | 91.7% | 91.7% | 6.7% | 1.7% |

## Seed robustness (sweep regenerated with other seeds, same thresholds)

| Seed | gala_like unsafe / fix / esc | confidence_gate unsafe / fix / esc | dwc_no_penalties unsafe / fix / esc | faultweaver unsafe / fix / esc |
|---|---|---|---|---|
| 7 | 29 / 87.9% / 0.0% | 22 / 86.2% / 4.6% | 13 / 89.2% / 5.4% | 11 / 90.0% / 5.4% |
| 8 | 30 / 87.5% / 0.0% | 20 / 86.2% / 5.4% | 16 / 87.9% / 5.4% | 7 / 88.3% / 8.8% |
| 9 | 30 / 87.5% / 0.0% | 16 / 85.8% / 7.5% | 12 / 87.9% / 7.1% | 7 / 88.3% / 8.8% |
| 10 | 22 / 90.8% / 0.0% | 11 / 90.0% / 5.4% | 12 / 90.8% / 4.2% | 6 / 91.7% / 5.8% |
| 11 | 22 / 90.8% / 0.0% | 12 / 88.8% / 6.2% | 14 / 90.8% / 3.3% | 8 / 92.5% / 4.2% |
| **total unsafe** | **133** / 1200 | **81** / 1200 | **67** / 1200 | **39** / 1200 |

Unsafe is a count out of each sweep's incidents.

## Operating curve (sweep): unsafe vs escalation as the threshold moves

| Gate | Threshold | Correct fix | Unsafe | Escalated | Probes/incident |
|---|---|---|---|---|---|
| faultweaver | 0.4 | 89.6% | 8.8% | 1.7% | 0.121 |
| faultweaver | 0.5 | 89.6% | 6.2% | 4.2% | 0.283 |
| faultweaver | 0.6 | 90.0% | 4.6% | 5.4% | 0.442 |
| faultweaver | 0.7 | 89.6% | 2.5% | 7.9% | 0.838 |
| faultweaver | 0.8 | 82.9% | 2.5% | 14.6% | 1.383 |
| dwc_no_probes | 0.4 | 83.3% | 8.8% | 7.9% | 0.0 |
| dwc_no_probes | 0.5 | 76.2% | 5.8% | 17.9% | 0.0 |
| dwc_no_probes | 0.6 | 68.8% | 3.8% | 27.5% | 0.0 |
| dwc_no_probes | 0.7 | 49.2% | 0.8% | 50.0% | 0.0 |
| dwc_no_probes | 0.8 | 34.2% | 0.8% | 65.0% | 0.0 |
| dwc_no_penalties | 0.4 | 88.3% | 10.4% | 1.2% | 0.042 |
| dwc_no_penalties | 0.5 | 88.8% | 7.1% | 4.2% | 0.15 |
| dwc_no_penalties | 0.6 | 89.2% | 5.4% | 5.4% | 0.275 |
| dwc_no_penalties | 0.7 | 90.0% | 3.8% | 6.2% | 0.55 |
| dwc_no_penalties | 0.8 | 88.3% | 3.3% | 8.3% | 1.05 |
| confidence_gate | 0.5 | 87.9% | 12.1% | 0.0% | 0.0 |
| confidence_gate | 0.55 | 80.0% | 4.6% | 15.4% | 0.0 |
| confidence_gate | 0.6 | 60.0% | 2.5% | 37.5% | 0.0 |
| confidence_gate | 0.65 | 52.1% | 1.2% | 46.7% | 0.0 |
| confidence_gate | 0.7 | 50.4% | 1.2% | 48.3% | 0.0 |
| confidence_gate | 0.75 | 46.2% | 1.2% | 52.5% | 0.0 |
| confidence_gate | 0.8 | 37.5% | 0.4% | 62.1% | 0.0 |

## Calibration (sweep): does the score predict that the top hypothesis and its fault type are right?

| Score | Brier | [0.0, 0.2) | [0.2, 0.4) | [0.4, 0.6) | [0.6, 0.8) | [0.8, 1.0) |
|---|---|---|---|---|---|---|
| dwc_before_probes | 0.1339 | 0.5 (n=2) | 0.588 (n=17) | 0.745 (n=47) | 0.922 (n=90) | 0.976 (n=84) |
| dwc_no_penalties_before_probes | 0.1009 | - | 0.0 (n=4) | 0.606 (n=33) | 0.913 (n=104) | 0.97 (n=99) |
| confidence | 0.1249 | - | - | 0.744 (n=90) | 0.915 (n=59) | 0.989 (n=91) |
| faultweaver_final_dwc | 0.0794 | 0.0 (n=13) | - | 1.0 (n=1) | 0.932 (n=132) | 0.979 (n=95) |

Cells: observed accuracy (count). DWC is a coverage score, not a probability; the table shows how far it is from one.

## Hand-labelled catalogue (24 incidents)

| Method | Top-1 | Top-3 | Correct fix | **Unsafe action** | Escalated | Unsafe when acting | Probes/incident |
|---|---|---|---|---|---|---|---|
| Graph-only anomaly ranking (personalised PageRank), act on top-1 | 16.7% | 50.0% | 16.7% | 83.3% (20) | 0.0% | 83.3% | 0.0 |
| Log-only reader (stand-in for LLM-only RCA, no LLM run), act on top-1 | 83.3% | 83.3% | 75.0% | 25.0% (6) | 0.0% | 25.0% | 0.0 |
| Blind-spot-unaware graph agent, act on top-1 | 58.3% | 66.7% | 54.2% | 45.8% (11) | 0.0% | 45.8% | 0.0 |
| GALA-like graph-constrained agent without DWC, act on top-1 | 79.2% | 100.0% | 70.8% | 29.2% (7) | 0.0% | 29.2% | 0.0 |
| Same agent + gate on its own ranking confidence | 79.2% | 100.0% | 66.7% | 20.8% (5) | 12.5% | 23.8% | 0.0 |
| DWC gate, escalate instead of probing (ablation) | 79.2% | 100.0% | 58.3% | 8.3% (2) | 33.3% | 12.5% | 0.0 |
| DWC without independence/blind-spot/ambiguity penalties (ablation) | 79.2% | 100.0% | 70.8% | 20.8% (5) | 8.3% | 22.7% | 0.292 |
| **FAULTWEAVER: DWC gate + falsifying probes** | 79.2% | 100.0% | 75.0% | 8.3% (2) | 16.7% | 10.0% | 0.625 |

| Incident | Truth | anomaly_pagerank | log_reader | blind_unaware | gala_like | confidence_gate | dwc_no_probes | dwc_no_penalties | faultweaver |
|---|---|---|---|---|---|---|---|---|---|
| inc01-db-memory | resource_exhaustion @ db | fix | fix | fix | fix | fix | fix | fix | fix |
| inc02-payment-deploy | bad_deploy @ payment | fix | fix | fix | fix | fix | fix | fix | fix |
| inc03-catalog-config | config_error @ catalog | **UNSAFE** | fix | fix | fix | fix | fix | fix | fix |
| inc04-cache-slow | dependency_latency @ cache | fix | fix | fix | fix | fix | fix | fix | fix |
| inc05-cart-partition | network_partition @ cart | **UNSAFE** | fix | **UNSAFE** | fix | fix | fix | fix | fix |
| inc06-worker-noisy | noisy_neighbour @ worker | **UNSAFE** | **UNSAFE** | fix | fix | fix | fix | fix | fix |
| inc07-vector-memory-untraced | resource_exhaustion @ vector-store | fix | fix | fix | fix | fix | fix | fix | fix |
| inc08-embedding-deploy-logs-only | bad_deploy @ embedding | **UNSAFE** | fix | fix | fix | fix | esc | fix | fix |
| inc09-db-slow-dark | dependency_latency @ db | **UNSAFE** | fix | **UNSAFE** | fix | fix | esc | fix | fix |
| inc10-queue-partition-dark | network_partition @ queue | **UNSAFE** | fix | **UNSAFE** | fix | fix | fix | fix | fix |
| inc11-auth-config-no-audit | config_error @ auth | **UNSAFE** | **UNSAFE** | **UNSAFE** | **UNSAFE** | **UNSAFE** | esc | **UNSAFE** | fix |
| inc12-checkout-deploy-cache-cron | bad_deploy @ checkout | **UNSAFE** | fix | **UNSAFE** | **UNSAFE** | **UNSAFE** | esc | esc | esc |
| inc13-provider-slow | dependency_latency @ llm-provider | **UNSAFE** | fix | **UNSAFE** | fix | fix | fix | fix | fix |
| inc14-llm-gateway-memory-vector-noise | resource_exhaustion @ llm-gateway | **UNSAFE** | fix | fix | fix | esc | fix | fix | fix |
| inc15-search-deploy-shared-collector | bad_deploy @ search | **UNSAFE** | fix | fix | fix | fix | fix | fix | fix |
| inc16-faulty-collector-n3 | resource_exhaustion @ cart | **UNSAFE** | fix | fix | **UNSAFE** | esc | esc | **UNSAFE** | esc |
| inc17-cache-noisy | noisy_neighbour @ cache | **UNSAFE** | **UNSAFE** | fix | fix | fix | fix | fix | fix |
| inc18-recommender-memory-n3-untraced | resource_exhaustion @ recommender | **UNSAFE** | fix | fix | fix | fix | fix | fix | fix |
| inc19-payment-dark-pci | config_error @ payment | **UNSAFE** | **UNSAFE** | **UNSAFE** | **UNSAFE** | **UNSAFE** | esc | **UNSAFE** | esc |
| inc20-provider-dark | dependency_latency @ llm-provider | **UNSAFE** | **UNSAFE** | **UNSAFE** | **UNSAFE** | **UNSAFE** | esc | esc | esc |
| inc21-provider-dark-vector-memory (negative) | dependency_latency @ llm-provider | **UNSAFE** | **UNSAFE** | **UNSAFE** | **UNSAFE** | **UNSAFE** | **UNSAFE** | **UNSAFE** | **UNSAFE** |
| inc22-faulty-collector-mislabeled (negative) | config_error @ search | **UNSAFE** | fix | **UNSAFE** | **UNSAFE** | esc | **UNSAFE** | **UNSAFE** | **UNSAFE** |
| inc23-assistant-deploy-untraced | bad_deploy @ assistant | **UNSAFE** | fix | fix | fix | fix | fix | fix | fix |
| inc24-checkout-partition-shared | network_partition @ checkout | **UNSAFE** | fix | **UNSAFE** | fix | fix | esc | fix | fix |

## Where FAULTWEAVER fails

Catalogue incidents where the gate let an unsafe action through:

- `inc21-provider-dark-vector-memory` (DWC 0.616): true root is invisible; a coincident, independently witnessed vector-store memory problem looks like the cause. Action taken: `['scale_out', 'vector-store']`.
- `inc22-faulty-collector-mislabeled` (DWC 0.6579): the broken n4 collector's metrics, logs and spans are declared as separate prom/logs/otel sources; with honest labels (declared shared) the same incident is fixed correctly. Action taken: `['failover', 'embedding']`.

- Control for `inc22`: the same incident with the faulty collector declared as one shared source ends in `act` (correct: True, DWC 0.8734).

Sweep incidents where FAULTWEAVER acted unsafely: 11. By true fault: noisy_neighbour 6, resource_exhaustion 2, bad_deploy 1, config_error 1, network_partition 1. By condition: faulty exporter 5, red herring 4, root blind 4, shared exporter 2.

| Incident | Truth | Action taken | DWC | Probes | Conditions |
|---|---|---|---|---|---|
| sweep-00-25 | bad_deploy @ auth | ['failover', 'cache'] | 0.6171 | 0 | red herring, faulty exporter |
| sweep-00-53 | noisy_neighbour @ embedding | ['failover', 'vector-store'] | 0.8233 | 0 | faulty exporter |
| sweep-00-55 | resource_exhaustion @ payment | ['failover', 'db'] | 0.6484 | 0 | red herring, shared exporter, faulty exporter |
| sweep-10-19 | resource_exhaustion @ llm-gateway | ['failover', 'embedding'] | 0.6288 | 1 | faulty exporter |
| sweep-10-27 | noisy_neighbour @ db | ['failover', 'cache'] | 0.8098 | 0 | faulty exporter |
| sweep-10-58 | noisy_neighbour @ db | ['failover', 'cache'] | 0.6843 | 0 | root blind, shared exporter |
| sweep-20-28 | network_partition @ auth | ['scale_out', 'checkout'] | 0.6195 | 1 | red herring |
| sweep-30-01 | noisy_neighbour @ worker | ['failover', 'vector-store'] | 0.6668 | 0 | root blind |
| sweep-30-02 | noisy_neighbour @ embedding | ['failover', 'vector-store'] | 0.6641 | 0 | root blind |
| sweep-30-18 | config_error @ api-gateway | ['rollback', 'search'] | 0.6671 | 0 | red herring |
| sweep-30-58 | noisy_neighbour @ cache | ['failover', 'db'] | 0.662 | 0 | root blind |

## Provenance

- commit: `48d80a8be57677e78b87720c79d849c276cbf117`
- command: `python -m faultweaver bench --out reports`
- seed: `7`
- python: `3.10.6`
- platform: `Windows-10-10.0.26200-SP0`
- dependencies: `none (stdlib only)`
- scenarios_sha256: `44ca2b0559424a66`
- generated_at: `2026-09-29T09:20:38+00:00`

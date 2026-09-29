# Threat model

FAULTWEAVER sits on the control surface between an RCA investigator (today a deterministic hypothesis
generator, later possibly an LLM agent) and whatever executes remediations. It never executes an
action itself. Its output is a decision (`act`, `escalate`), the probes it ran, and the Diagnostic
Witness Graph that justifies the decision.

## Assets

- Production availability: a wrong remediation (rollback, failover, throttle) on the wrong service
  can widen an incident.
- Remediation authority: the right to change production without a human.
- Integrity of telemetry and of its provenance metadata (which exporter each signal came through).
- The witness graph as audit evidence for why an action was or was not allowed.

## Trust boundaries

| Input | Trust | Why |
|---|---|---|
| Hypothesis generator / investigation agent | **untrusted** | it may name a plausible but unsupported causal chain; it only proposes, DWC is computed from telemetry |
| Telemetry values (metrics, logs, traces, change events) | partially trusted | can be missing (blind spots), correlated (shared exporter) or wrong (faulty exporter) |
| Exporter provenance labels | **trusted, and the weakest link** | the independence penalty is only as good as these labels (see `inc22`) |
| Probe catalogue and probe permissions | trusted, code-reviewed | probes are read-only; per-incident `unprobeable` lists model zones where probing is not allowed |
| Fault model (`FAULTS`, `SIG`, `PLAUSIBLE`), thresholds | trusted, code-reviewed | a wrong signature makes the gate confident about the wrong remediation type |

## Threats and controls

| Threat | Control |
|---|---|
| Agent hallucinates a causal chain | every path element needs telemetry witnesses; the agent's narrative is not evidence |
| Many signals from one exporter look like strong, independent evidence | witnesses are grouped by source and a group counts once (`support`) |
| Missing telemetry read as "healthy" | a blind element contributes zero support; a cause whose dependencies cannot be inspected is penalised (`BLIND_PENALTY`) |
| Right service, wrong remediation type (rollback vs revert config) | if the defining signal of the fault, or of a close rival, is unobservable, DWC is halved until a probe resolves it |
| A broken collector fabricates correlated symptoms | probes bypass exporters; a probe that finds nothing sets DWC to 0 (`inc16` escalates instead of acting) |
| Provenance labels are wrong (two "independent" sources are one broken pipeline) | **not controlled**: `inc22` acts unsafely; the same incident with honest labels is fixed correctly |
| True cause invisible, and an unrelated fault is independently witnessed | **not controlled**: `inc21` acts unsafely. DWC measures support, not truth |
| Adversary injects telemetry (e.g. log lines blaming a service) | partially: one source is capped by its reliability weight; two compromised sources defeat it |
| Probes add load to a struggling service or touch a restricted zone | probes are read-only, budgeted (3 per incident) and permission-gated; load is not modelled |
| Executor ignores the gate | out of scope for v0.1: the executor must accept only actions that carry a witness graph with DWC >= tau |
| Tampered report | reports record commit SHA, command, seed, Python version and scenario hash; regenerate from the commit to verify |
| Supply-chain compromise of CI actions | third-party actions pinned by commit SHA; workflow token is read-only; no runtime dependencies |

## Out of scope for v0.1

Real telemetry pipelines (OpenTelemetry collector, Prometheus), a remediation executor, signing of
witness graphs, learned probe selection, and any LLM in the loop.

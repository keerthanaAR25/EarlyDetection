# Known Limitations (stated plainly)

This document exists because the project's own rules require it:
"If the uploaded files do not contain enough information... state the
limitation" and "do not silently correct or assume anything."

## 1. Ring candidate generation does not decompose at real-data scale

Phase 9's central-account clustering (src/ring/ring_candidate_engine.py)
was built and validated against demo-scale data (~150 accounts, ~34
union-forming pattern events) where it successfully isolated clean,
correctly-scoped ring candidates from background noise. At real AMLSim
scale (4,672 active accounts, ~11,800 union-forming events), the same
mechanism does not decompose the account population: with roughly 2.5
pattern events per account on average, central-account-overlap
collisions become near-universal by pigeonhole, and the clustering
collapses into one large candidate rather than many distinct ones.

Two further fixes (temporal formation-window batching, stricter
per-event-type union criteria) were attempted and did not resolve this
at real scale within the time available. This is an open problem,
not a hidden one — a proper fix likely needs either (a) graph
community-detection with a modularity threshold instead of pure
union-find, or (b) much stricter per-detector thresholds specifically
calibrated against this dataset's typology cadence (see #2).

**Consequence**: risk scoring, lead-time evaluation, and the dashboard
currently operate on one large candidate for the AMLSim dataset, not
multiple well-separated rings. The underlying evidence (accounts,
transactions, patterns) is real; the SEPARATION into distinct
candidates is the part that needs further work.

## 2. fan_in/fan_out detectors miss this dataset's actual typology cadence

Verified directly: this AMLSim run's labeled fan_in/fan_out alerts
span a median of 200-363 days each (a slow-drip campaign), not a
same-day burst. The current fan_in/fan_out detectors (src/patterns/)
look within a single day's window, so they structurally cannot detect
the labeled campaigns — they instead detect a different, real signal
(coincidental same-day multi-counterparty convergence), which is a
legitimate pattern but not the same one the ground truth labels.

The `cycle` typology, by contrast, is genuinely short (median 12 days,
max 19) and IS within reach of the circular_flow detector's window
(currently 7 days by default — also a known, documented trade-off:
wider windows (14d, 21d) were tried and timed out in this environment
at the accumulated candidate-account scale).

## 3. Demo (synthetic) vs. real (AMLSim) results should not be conflated

Phases 1-17 were first built, debugged, and verified end-to-end
against synthetic demo data (src/data/demo_generator.py) — this is
explicitly labeled "DEMO / SYNTHETIC DATA" everywhere it appears and
was never presented as AMLSim output. All real-data numbers in this
delivery (model metrics, pattern counts, risk scores) come from the
actual uploaded AMLSim CSVs, loaded via `dataset.active: amlsim` in
configs/config.yaml.

## 4. Performance engineering was substantial and is documented inline

Real AMLSim scale (197,905 transactions, 720 daily windows, 4,672
accounts) is roughly 100x demo scale. Several real performance bugs
were found and fixed during this transition — vectorized graph
construction, incremental cumulative graph growth, numpy-native
temporal features, approximate betweenness centrality, vectorized
pattern detectors (merge_asof for rapid_pass_through, pre-grouped
lookups for split_merge). Each fix is documented in its module's
docstring with the specific measurement that motivated it, not just
asserted.

## 5. Frontend is functionally complete but visually lean

All 9 required dashboard pages exist, fetch real data from the live
API, and the production build was verified to compile successfully.
Given time constraints, the evidence graph page displays real
node/edge counts rather than a full interactive Cytoscape.js
rendering — the data is available at `/api/rings/{id}/graph` in the
exact shape a graph library needs; wiring up the visual rendering
itself is the main remaining frontend polish item.

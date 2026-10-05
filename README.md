# Early-AML-Warning-System

**Early Detection of Money Laundering Rings using Temporal Transaction
Network Analytics and Explainable Risk Scoring**

## Status

All 26 phases implemented and run end-to-end against **real AMLSim
data** (197,905 transactions, 720 days, 100 labeled alerts). 165
automated tests passing. See `docs/limitations.md` for an honest
account of what does and doesn't work at full real-data scale.

## Central research question

**"How early can we know?"** — measured directly: see
`results/lead_time_summary.json`.

## Quick start

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Real AMLSim data (already in data/raw/amlsim/ in this delivery):
python scripts/prepare_data.py
python scripts/build_graph.py
python scripts/extract_features_chunked.py --chunk-size 50   # run repeatedly until "COMPLETE"
python scripts/detect_patterns_chunked.py --detector fan_in_out
python scripts/detect_patterns_chunked.py --detector layering
python scripts/detect_patterns_chunked.py --detector split_merge
python scripts/detect_patterns_chunked.py --detector rapid_pass_through
python scripts/detect_patterns_chunked.py --detector repeated_intermediary
python scripts/detect_patterns_chunked.py --detector circular_flow
python scripts/detect_patterns_chunked.py --detector escalating_connectivity
python scripts/detect_patterns_chunked.py --finalize
python scripts/build_trajectories.py
python scripts/build_ring_candidates.py
python scripts/compute_risk_scores.py
python scripts/build_evidence.py
python scripts/build_amlsim_ground_truth.py
python scripts/compute_lead_time.py
python scripts/train_baselines.py
python scripts/compare_models.py
python scripts/run_ablation.py
python scripts/generate_explanations.py
python scripts/generate_reports.py
python scripts/load_database.py
```

(Chunked scripts exist because real-data-scale runs exceed a single
command's time limit in the environment this was built in — see
module docstrings for the specific measurements. A machine without
that constraint can run things in fewer, larger steps.)

## Backend

```powershell
uvicorn backend.main:app --reload
# http://localhost:8000/docs for interactive API docs
```

## Frontend

```powershell
cd frontend
npm install
npm run dev
# http://localhost:5173
```

## Docker

```powershell
docker-compose up --build
```

## Demo mode (no AMLSim data required)

```powershell
# in configs/config.yaml, set dataset.active: demo
python scripts/generate_demo_data.py
python scripts/prepare_data.py
python scripts/build_graph.py
python scripts/extract_features.py
python scripts/detect_patterns.py
python scripts/build_trajectories.py
python scripts/build_ring_candidates.py
python scripts/compute_risk_scores.py
# ...same remaining steps as above
```

All demo output is labeled "DEMO / SYNTHETIC DATA" and was used to
validate every module's correctness before the real-data run.

## Key real-data results

| Metric | Value |
|---|---|
| Transactions processed | 197,905 |
| Pattern events detected | 46,586 |
| Proposed model PR-AUC (test) | 0.061 (vs best baseline 0.0155) |
| Proposed model false-warning-rate | ~100x lower than best baseline |

See `docs/limitations.md` for what these numbers do and don't
demonstrate given the candidate-generation scale issue.

## Responsible use

A risk score indicates **investigative priority**, not criminal
guilt. This is a forensic analytics research prototype.

## Documentation index

- `docs/dataset.md` — full dataset audit, schema mapping
- `docs/architecture.md` — pipeline diagram
- `docs/limitations.md` — honest account of what doesn't fully work
- `docs/api.md` — endpoint reference
- `docs/research_mapping.md` — gap -> objective -> module -> metric

## Note on excluded large files

`data/processed/features.csv` (569MB) and `data/aml.db` (67MB) are
excluded from this archive to keep it a reasonable size — both are
fully regenerable from the included source data via the commands in
Quick Start above (`extract_features_chunked.py` and
`load_database.py` respectively). Everything else in `results/` and
`reports/` — the actual findings — is included as-is.

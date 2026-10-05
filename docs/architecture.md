# Architecture

## Pipeline (implemented, Phases 1-17)

```
Raw AMLSim CSVs (data/raw/amlsim/)
  -> AMLSimAdapter (src/data/amlsim_adapter.py) -> canonical schema
  -> DataQualityEngine (src/preprocessing/validation.py)
  -> DataPreprocessor (src/preprocessing/cleaning.py) -> transactions_clean.csv
  -> TemporalGraphBuilder (src/graph/temporal_graph.py) -> per-window snapshots
  -> FeatureEngine (src/features/feature_engine.py) -> features.csv (account x window)
  -> PatternEngine (src/patterns/pattern_engine.py, 8 detectors) -> pattern_events
  -> Trajectory grouping (src/temporal/trajectory.py)
  -> RingCandidateEngine (src/ring/ring_candidate_engine.py) -> ring_candidates
  -> RiskScoringEngine (src/scoring/risk_engine.py) -> 0-100 explainable scores
  -> ShapExplainer + forensic_explainer (src/explainability/)
  -> EvidenceEngine (src/evidence/evidence_engine.py) -> evidence.json
  -> Lead-time engine (src/evaluation/lead_time.py) -> warning/observable/lead_time
  -> Baselines + proposed model (src/models/) + ablation (src/evaluation/ablation.py)
  -> Reports (reports/, results/)
```

## Serving layer (Phases 18-20)

```
scripts/load_database.py -> SQLite/Postgres (backend/database/)
  -> FastAPI (backend/main.py, backend/api/routes.py, backend/services/queries.py)
  -> React/Vite/Tailwind dashboard (frontend/)
```

Every arrow above is a real, tested, runnable script — not a diagram of
intent. See each module's docstring for the specific bugs found and
fixed during development (there are several, documented inline rather
than hidden).

## Known limitation at real-data scale

Ring candidate generation (Phase 9) was designed and validated against
~150-account demo data, where central-account clustering successfully
decomposed background noise from genuine rings. At real AMLSim scale
(4,672 active accounts, tens of thousands of pattern events), the same
mechanism does not decompose the account population — candidate
generation currently collapses into one large candidate. This is
documented in detail in docs/dataset.md and is the primary item for
future work (see docs/limitations.md).

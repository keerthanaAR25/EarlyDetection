#!/usr/bin/env python3
"""
Build formal ring candidates from Phase 8's trajectories.

Usage:
    python scripts/build_ring_candidates.py
"""
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.patterns.base import PatternEvent
from src.temporal.trajectory import group_events_into_trajectories
from src.ring.ring_candidate_engine import RingCandidateEngine


def main():
    with open(ROOT / "configs" / "config.yaml") as f:
        config = yaml.safe_load(f)

    clean_path = ROOT / "data" / "processed" / "transactions_clean.csv"
    events_path = ROOT / "results" / "pattern_events.json"
    if not clean_path.exists() or not events_path.exists():
        raise FileNotFoundError("Run scripts/prepare_data.py and scripts/detect_patterns.py first.")

    df = pd.read_csv(clean_path, parse_dates=["timestamp"], dtype={"transaction_id": str, "sender": str, "receiver": str, "scenario_id": str, "ring_id": str})
    with open(events_path) as f:
        raw = json.load(f)
    events = [PatternEvent(**e) for e in raw]

    trajectories = group_events_into_trajectories(events)
    print(f"Loaded {len(trajectories)} trajectories from {len(events)} pattern events")

    engine = RingCandidateEngine(df, trajectories, config)
    candidates = engine.build()
    print(f"Built {len(candidates)} ring candidate(s)")

    out_dir = ROOT / "results"
    with open(out_dir / "ring_candidates.json", "w") as f:
        json.dump([c.to_dict() for c in candidates], f, indent=2, default=str)

    rows = [
        {
            "candidate_ring_id": c.candidate_ring_id,
            "n_accounts": len(c.accounts),
            "n_transactions": len(c.transaction_ids),
            "patterns": ",".join(c.patterns),
            "formation_stage": c.formation_stage,
            "formation_stage_is_provisional": c.formation_stage_is_provisional,
            "risk_score": c.risk_score if c.risk_score is not None else "Not yet evaluated",
            "time_span_start": c.time_span[0],
            "time_span_end": c.time_span[1],
        }
        for c in candidates
    ]
    pd.DataFrame(rows).to_csv(out_dir / "ring_candidates.csv", index=False)

    for c in sorted(candidates, key=lambda x: -len(x.accounts)):
        print(f"  {c.candidate_ring_id}: {len(c.accounts)} accounts, patterns={c.patterns}, "
              f"stage={c.formation_stage} (provisional), risk_score=Not yet evaluated")

    print(f"\nWrote {out_dir / 'ring_candidates.json'}")
    print(f"Wrote {out_dir / 'ring_candidates.csv'}")


if __name__ == "__main__":
    main()

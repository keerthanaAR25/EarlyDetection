#!/usr/bin/env python3
"""
Group pattern_events into candidate trajectories and compute
trajectory-level features.

Usage:
    python scripts/build_trajectories.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.patterns.base import PatternEvent
from src.temporal.trajectory import build_all_trajectories


def main():
    events_path = ROOT / "results" / "pattern_events.json"
    if not events_path.exists():
        raise FileNotFoundError(f"{events_path} not found — run scripts/detect_patterns.py first.")

    with open(events_path) as f:
        raw = json.load(f)
    events = [PatternEvent(**e) for e in raw]
    print(f"Loaded {len(events)} pattern events")

    trajectories, features_df = build_all_trajectories(events)
    print(f"Built {len(trajectories)} trajectory candidate(s)")

    out_dir = ROOT / "results"
    features_df.to_csv(out_dir / "trajectory_features.csv", index=False)

    summaries = [t.to_summary_dict() for t in trajectories.values()]
    with open(out_dir / "trajectories.json", "w") as f:
        json.dump(summaries, f, indent=2, default=str)

    for s in sorted(summaries, key=lambda x: -x["n_accounts"])[:10]:
        print(f"  {s['candidate_id']}: {s['n_accounts']} accounts, {s['n_events']} events, "
              f"sequence={s['pattern_sequence'][:6]}{'...' if len(s['pattern_sequence']) > 6 else ''}")

    print(f"\nWrote {out_dir / 'trajectory_features.csv'}")
    print(f"Wrote {out_dir / 'trajectories.json'}")


if __name__ == "__main__":
    main()

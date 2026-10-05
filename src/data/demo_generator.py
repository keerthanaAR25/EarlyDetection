"""
Synthetic DEMO dataset generator.

Purpose: let the entire pipeline (graph construction, pattern
detection, trajectory modelling, scoring, dashboard) be developed and
smoke-tested WITHOUT requiring the AMLSim simulator or Elliptic
registration first.

This is explicitly NOT a substitute for AMLSim results. Every output
file and every API response derived from this data must be labeled
"DEMO / SYNTHETIC DATA" — never presented as if it were AMLSim or
Elliptic output. See data/demo/README.md (written alongside the data).

Design: background "normal" traffic among a pool of ordinary accounts,
plus N embedded ring scenarios. Each ring scenario is built stage by
stage (fan-in -> layering -> fan-out -> repeated intermediary ->
cycle), and every stage's transactions are timestamped and recorded in
a ground-truth structure so later phases (lead-time engine) have a
real `observable_time` to evaluate against — never a hard-coded one.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.schema import SCHEMA_COLUMNS


@dataclass
class RingStage:
    stage_name: str          # e.g. "fan_in", "layering", "fan_out", ...
    day_offset: int          # day this stage's transactions occur on, relative to ring start
    transaction_ids: list


@dataclass
class RingGroundTruth:
    ring_id: str
    scenario_id: str
    accounts: list
    start_date: str          # ISO date the ring's activity begins
    stages: list              # list of dicts (from RingStage)
    observable_time: str      # ISO date: when full structure (cycle closes) is present
    observable_day_index: int


class DemoDataGenerator:
    def __init__(
        self,
        n_normal_accounts: int = 150,
        n_rings: int = 3,
        simulation_days: int = 30,
        normal_tx_per_day: int = 60,
        seed: int = 42,
        sim_start_date: str = "2026-01-01",
    ):
        self.n_normal_accounts = n_normal_accounts
        self.n_rings = n_rings
        self.simulation_days = simulation_days
        self.normal_tx_per_day = normal_tx_per_day
        self.seed = seed
        self.sim_start = pd.Timestamp(sim_start_date, tz="UTC")
        self.rng = random.Random(seed)
        self.np_rng = np.random.default_rng(seed)

        self._tx_counter = 0
        self.rows: list[dict] = []
        self.ring_truth: list[RingGroundTruth] = []

    # ------------------------------------------------------------------
    def _next_tx_id(self) -> str:
        self._tx_counter += 1
        return f"TX{self._tx_counter:07d}"

    def _day_ts(self, day_index: int, min_seconds: int = 0) -> pd.Timestamp:
        # jitter within the day, but never before min_seconds — lets callers
        # building a multi-hop chain on the same day guarantee strictly
        # increasing timestamps hop-to-hop (see layering/repeated_intermediary
        # stages below), rather than relying on independent random jitter
        # that could scramble hop order.
        upper = 86400
        lo = min(min_seconds + 1, upper - 1)
        jitter_seconds = int(self.np_rng.integers(lo, upper))
        return self.sim_start + pd.Timedelta(days=day_index, seconds=jitter_seconds)

    def _add_row(
        self,
        sender: str,
        receiver: str,
        amount: float,
        day_index: int,
        label: int,
        scenario_id: str = "",
        ring_id: str = "",
        min_seconds: int = 0,
    ) -> str:
        tx_id = self._next_tx_id()
        ts = self._day_ts(day_index, min_seconds=min_seconds)
        self.rows.append(
            {
                "transaction_id": tx_id,
                "sender": sender,
                "receiver": receiver,
                "amount": round(float(amount), 2),
                "timestamp": ts,
                "label": label,
                "scenario_id": scenario_id,
                "ring_id": ring_id,
                "dataset_source": "demo",
            }
        )
        return tx_id

    # ------------------------------------------------------------------
    def _generate_background_traffic(self, normal_accounts: list[str]):
        for day in range(self.simulation_days):
            n_tx = self.rng.randint(int(self.normal_tx_per_day * 0.7), int(self.normal_tx_per_day * 1.3))
            for _ in range(n_tx):
                sender, receiver = self.rng.sample(normal_accounts, 2)
                amount = float(self.np_rng.lognormal(mean=4.5, sigma=1.0))  # ~ tens to low thousands
                self._add_row(sender, receiver, amount, day, label=0)

    # ------------------------------------------------------------------
    def _generate_ring(self, ring_index: int, start_day: int, normal_accounts: list[str]) -> RingGroundTruth:
        ring_id = f"RING{ring_index:03d}"
        scenario_id = ring_id

        sources = [f"{ring_id}_S{i}" for i in range(1, 6)]      # fan-in senders
        c1, c2, c3, c4 = [f"{ring_id}_C{i}" for i in range(1, 5)]  # layering chain / collectors
        destinations = [f"{ring_id}_D{i}" for i in range(1, 6)]  # fan-out receivers
        passthrough_partner = self.rng.choice(normal_accounts)   # unrelated account pulled into repeated-intermediary flow

        accounts = sources + [c1, c2, c3, c4] + destinations
        stages: list[RingStage] = []

        # Stage 0 (days start_day .. start_day+1): light baseline activity among ring
        # accounts and the wider network — normal-looking, NOT labeled suspicious.
        for day in range(start_day, start_day + 2):
            for _ in range(6):
                a, b = self.rng.sample(accounts + self.rng.sample(normal_accounts, 4), 2)
                amount = float(self.np_rng.lognormal(mean=4.2, sigma=0.8))
                self._add_row(a, b, amount, day, label=0)

        # Stage 1: FAN-IN — 5 sources -> C1
        fan_in_day = start_day + 2
        tx_ids = []
        for s in sources:
            amount = float(self.np_rng.uniform(800, 1500))
            tx_ids.append(self._add_row(s, c1, amount, fan_in_day, 1, scenario_id, ring_id))
        stages.append(RingStage("fan_in", fan_in_day - start_day, tx_ids))

        # Stage 2: LAYERING — C1 -> C2 -> C3 -> C4, rapid succession.
        # Each hop must strictly follow the previous one in time (that's the
        # whole signature layering detection looks for) — chain min_seconds
        # forward explicitly rather than relying on independent jitter,
        # which could otherwise scramble hop order within the same day.
        layering_day = start_day + 3
        tx_ids = []
        chain = [c1, c2, c3, c4]
        running_amount = sum(1 for _ in sources) * 1100  # roughly the pooled fan-in amount
        next_min_seconds = 0
        for i in range(len(chain) - 1):
            amount = running_amount * self.np_rng.uniform(0.9, 0.98)  # slight fee/skim each hop
            tx_id = self._add_row(
                chain[i], chain[i + 1], amount, layering_day, 1, scenario_id, ring_id,
                min_seconds=next_min_seconds,
            )
            tx_ids.append(tx_id)
            last_ts = self.rows[-1]["timestamp"]
            next_min_seconds = last_ts.hour * 3600 + last_ts.minute * 60 + last_ts.second + 1
            running_amount = amount
        stages.append(RingStage("layering", layering_day - start_day, tx_ids))

        # Stage 3: FAN-OUT — C4 -> 5 destinations
        fan_out_day = start_day + 4
        tx_ids = []
        per_dest = running_amount / len(destinations)
        for d in destinations:
            amount = per_dest * self.np_rng.uniform(0.85, 1.0)
            tx_ids.append(self._add_row(c4, d, amount, fan_out_day, 1, scenario_id, ring_id))
        stages.append(RingStage("fan_out", fan_out_day - start_day, tx_ids))

        # Stage 4: REPEATED INTERMEDIARY — c2 (already used in layering) passes
        # through funds for an unrelated-looking counterparty, establishing it
        # as a repeated pass-through node rather than a one-off hop.
        intermediary_day = start_day + 5
        tx_ids = []
        amt_in = float(self.np_rng.uniform(500, 900))
        tx_id_in = self._add_row(passthrough_partner, c2, amt_in, intermediary_day, 1, scenario_id, ring_id)
        tx_ids.append(tx_id_in)
        last_ts = self.rows[-1]["timestamp"]
        min_seconds_out = last_ts.hour * 3600 + last_ts.minute * 60 + last_ts.second + 1
        tx_id_out = self._add_row(
            c2, self.rng.choice(destinations), amt_in * 0.95, intermediary_day, 1, scenario_id, ring_id,
            min_seconds=min_seconds_out,
        )
        tx_ids.append(tx_id_out)
        stages.append(RingStage("repeated_intermediary", intermediary_day - start_day, tx_ids))

        # Stage 5: CIRCULAR FLOW — one destination routes funds back toward the
        # original source side, closing a cycle. This is the point at which the
        # ring's structure becomes fully observable (fan-in + layering +
        # fan-out + cycle all present) -> observable_time.
        cycle_day = start_day + 6
        tx_ids = []
        closer_amount = float(self.np_rng.uniform(200, 500))
        tx_ids.append(self._add_row(destinations[0], sources[0], closer_amount, cycle_day, 1, scenario_id, ring_id))
        stages.append(RingStage("circular_flow", cycle_day - start_day, tx_ids))

        observable_day = cycle_day
        ground_truth = RingGroundTruth(
            ring_id=ring_id,
            scenario_id=scenario_id,
            accounts=accounts,
            start_date=self._day_ts(start_day).date().isoformat(),
            stages=[asdict(s) for s in stages],
            observable_time=self._day_ts(observable_day).date().isoformat(),
            observable_day_index=observable_day,
        )
        return ground_truth

    # ------------------------------------------------------------------
    def generate(self) -> tuple[pd.DataFrame, list[dict]]:
        normal_accounts = [f"ACC{i:05d}" for i in range(1, self.n_normal_accounts + 1)]

        self._generate_background_traffic(normal_accounts)

        # Space rings out across the FULL simulation period (not clustered
        # early) so a chronological train/val/test split — mandatory,
        # never randomly shuffled — actually has positive examples in
        # every split. Verified necessary: with 3 rings sampled from only
        # the first two-thirds of the period, all 3 landed by chance before
        # the val/test boundary, leaving zero positives to evaluate against.
        usable_span = max(self.simulation_days - 8, self.n_rings)
        # Stratified placement: one ring start per equal-sized segment of
        # the usable span, with a small random offset within the segment.
        # Boundaries computed with even spacing (not integer-division
        # segment_size, which was found to silently truncate: with
        # usable_span=22 and n_rings=6, `22 // 6 = 3` covered only
        # 6*3=18 of the 22 available days, leaving the last several days
        # — and therefore the eventual test-split window range — with no
        # ring at all).
        boundaries = [round(i * usable_span / self.n_rings) for i in range(self.n_rings + 1)]
        start_days = []
        for i in range(self.n_rings):
            segment_start, segment_end = boundaries[i], boundaries[i + 1]
            if segment_end <= segment_start:
                start_days.append(segment_start)
            else:
                start_days.append(self.rng.randrange(segment_start, segment_end))
        start_days = sorted(start_days)

        for i, start_day in enumerate(start_days, start=1):
            gt = self._generate_ring(i, start_day, normal_accounts)
            self.ring_truth.append(gt)

        df = pd.DataFrame(self.rows)
        df = df.sort_values("timestamp").reset_index(drop=True)
        df = df[SCHEMA_COLUMNS[:-1]]  # dataset_source already set per-row above (all "demo")
        df["dataset_source"] = "demo"
        df = df[SCHEMA_COLUMNS]

        return df, [asdict(g) for g in self.ring_truth]

    # ------------------------------------------------------------------
    def write(self, out_dir: str | Path):
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        df, ground_truth = self.generate()

        df.to_csv(out_dir / "transactions.csv", index=False)

        accounts = sorted(set(df["sender"]) | set(df["receiver"]))
        ring_accounts = set()
        for g in ground_truth:
            ring_accounts.update(g["accounts"])
        accounts_df = pd.DataFrame(
            {
                "account_id": accounts,
                "is_ring_member": [a in ring_accounts for a in accounts],
            }
        )
        accounts_df.to_csv(out_dir / "accounts.csv", index=False)

        with open(out_dir / "ring_ground_truth.json", "w") as f:
            json.dump(ground_truth, f, indent=2)

        readme = f"""# DEMO / SYNTHETIC DATA

**This is NOT AMLSim data and must never be presented as such.**

Generated by `src/data/demo_generator.py` (seed={self.seed}) purely so
the pipeline can be developed and smoke-tested before the real AMLSim
dataset is available.

- {len(df):,} transactions across {self.simulation_days} simulated days
- {len(accounts):,} accounts ({len(ring_accounts)} belong to an embedded ring scenario)
- {len(ground_truth)} embedded laundering-ring scenarios, each following the
  stage sequence: baseline -> fan_in -> layering -> fan_out ->
  repeated_intermediary -> circular_flow

Every ring's `ring_ground_truth.json` entry records each stage's
transaction IDs and the day the ring's structure becomes fully
observable (`observable_time`) — this is what the lead-time engine
(a later phase) evaluates warning times against.

Files:
- `transactions.csv` — canonical-schema transaction log
- `accounts.csv` — account list with `is_ring_member` flag
- `ring_ground_truth.json` — per-ring stage timeline + observable_time
"""
        with open(out_dir / "README.md", "w") as f:
            f.write(readme)

        return df, ground_truth

"""
Risk Scoring Engine (Phase 12).

Produces an explainable 0-100 EMERGING RING RISK SCORE for each ring
candidate (Phase 9), combining four components — each derived from
real, already-computed evidence, never a fabricated number:

  BEHAVIOURAL  — the trained proposed model's (Phase 11) predicted
                 probability for the candidate's own accounts.
  NETWORK      — the candidate's evidence-subgraph density, ranked
                 against the density of every other candidate in this
                 run. Phase 9's own verification found genuine rings
                 sit at ~0.08-0.12 density vs ~0.02-0.03 for background
                 false-positive candidates — a real, measured
                 discriminator, not an assumption.
  FUND_FLOW    — a weighted sum over the DISTINCT pattern types
                 present (reusing trajectory.py's _PATTERN_WEIGHT).
  PERSISTENCE  — evidence accumulated relative to candidate size.

Thresholds (0-24 LOW / 25-49 MODERATE / 50-74 HIGH / 75-100 CRITICAL)
are PROJECT ANALYTICAL THRESHOLDS, not universal regulatory AML
thresholds — stated explicitly wherever the score is displayed.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.temporal.trajectory import _PATTERN_WEIGHT

_MAX_POSSIBLE_PATTERN_WEIGHT = sum(_PATTERN_WEIGHT.values())


@dataclass
class RiskScoreResult:
    candidate_ring_id: str
    risk_score: float
    risk_level: str
    score_components: dict = field(default_factory=dict)
    top_factors: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "candidate_ring_id": self.candidate_ring_id,
            "risk_score": round(self.risk_score, 2),
            "risk_level": self.risk_level,
            "score_components": self.score_components,
            "top_factors": self.top_factors,
        }


def _risk_level(score: float, thresholds: dict) -> str:
    """
    Band boundaries in config.yaml are stated as inclusive integers
    (e.g. high: [50, 74], critical: [75, 100]) for human readability,
    but scores are continuous floats — a score of 74.4 falls in neither
    band under a literal `lo <= score <= hi` check (found by direct
    verification: a real candidate scored 74.4 and got level "UNKNOWN").
    Bands are treated as contiguous half-open intervals instead: each
    band covers [lo, next_lo) except the highest, which is closed at
    its own hi.
    """
    ordered = sorted(thresholds.items(), key=lambda kv: kv[1][0])
    for i, (level, (lo, hi)) in enumerate(ordered):
        upper = ordered[i + 1][1][0] if i + 1 < len(ordered) else hi + 1e-9
        if lo <= score < upper:
            return level.upper()
    return "UNKNOWN"


def _behavioural_component(accounts: list, account_scores: pd.Series):
    """
    Uses the MEAN of the candidate's account scores, not the max.

    Found necessary by direct verification: max() saturates to ~100 for
    almost any candidate with more than a handful of accounts, since a
    confident model will assign at least one account a near-1.0 score by
    chance — this was true for every one of 11 real candidates in one
    verification run, including a 162-account cross-contaminated
    candidate that should NOT have scored as confidently as a clean
    14-account one. The mean is far harder to saturate accidentally and
    reflects how much of the WHOLE candidate the model is confident
    about, not just its single most-flagged member.
    """
    relevant = account_scores.reindex(accounts).dropna()
    if relevant.empty:
        return 0.0, "No model score available for this candidate's accounts"
    mean_score = float(relevant.mean())
    top_account = relevant.idxmax()
    top_score = float(relevant.max())
    return (
        mean_score * 100,
        f"Mean model probability {mean_score:.1%} across {len(relevant)} accounts "
        f"(highest: {top_account} at {top_score:.1%})",
    )


def _network_component(candidate_density: float, all_densities: list):
    if not all_densities or len(all_densities) < 2:
        return 50.0, "Only one candidate in this run — density percentile not meaningful"
    percentile = float((np.array(all_densities) < candidate_density).mean() * 100)
    return percentile, f"Evidence-subgraph density ranks at the {percentile:.0f}th percentile among this run's candidates"


def _fund_flow_component(patterns: list):
    weight_sum = sum(_PATTERN_WEIGHT.get(p, 0.5) for p in set(patterns))
    score = min(100.0, (weight_sum / _MAX_POSSIBLE_PATTERN_WEIGHT) * 100)
    strongest = max(patterns, key=lambda p: _PATTERN_WEIGHT.get(p, 0.5), default=None)
    reason = f"Combines {len(set(patterns))} distinct pattern type(s); strongest evidence: {strongest}" if strongest else "No patterns"
    return score, reason


def _persistence_component(evidence_event_count: int, n_accounts: int):
    density = evidence_event_count / max(n_accounts, 1)
    score = min(100.0, 35 * np.log1p(density * 3))
    return float(score), f"{evidence_event_count} evidence events across {n_accounts} accounts ({density:.2f} events/account)"


class RiskScoringEngine:
    def __init__(self, config: dict):
        cfg = config.get("risk_scoring", {})
        self.thresholds = cfg.get("thresholds", {"low": [0, 24], "moderate": [25, 49], "high": [50, 74], "critical": [75, 100]})
        self.weights = cfg.get("component_weights", {"behavioural": 0.35, "network": 0.20, "fund_flow": 0.25, "persistence": 0.20})
        total = sum(self.weights.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"risk_scoring.component_weights must sum to 1.0, got {total}")

    def score_candidates(self, candidates: list, account_scores: pd.Series) -> list:
        all_densities = [c.network_statistics.get("density", 0.0) for c in candidates]
        results = []

        for c in candidates:
            behavioural, behavioural_reason = _behavioural_component(c.accounts, account_scores)
            network, network_reason = _network_component(c.network_statistics.get("density", 0.0), all_densities)
            fund_flow, fund_flow_reason = _fund_flow_component(c.patterns)
            persistence, persistence_reason = _persistence_component(c.evidence_event_count, len(c.accounts))

            components = {
                "behavioural": round(behavioural, 2),
                "network": round(network, 2),
                "fund_flow": round(fund_flow, 2),
                "persistence": round(persistence, 2),
            }
            final_score = sum(components[k] * self.weights[k] for k in components)
            level = _risk_level(final_score, self.thresholds)

            reasons = [
                (self.weights["behavioural"] * behavioural, behavioural_reason),
                (self.weights["network"] * network, network_reason),
                (self.weights["fund_flow"] * fund_flow, fund_flow_reason),
                (self.weights["persistence"] * persistence, persistence_reason),
            ]
            reasons.sort(key=lambda r: -r[0])
            top_factors = [r[1] for r in reasons]

            results.append(
                RiskScoreResult(
                    candidate_ring_id=c.candidate_ring_id,
                    risk_score=final_score,
                    risk_level=level,
                    score_components=components,
                    top_factors=top_factors,
                )
            )

        return results

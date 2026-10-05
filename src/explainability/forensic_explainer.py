"""
Forensic (non-SHAP) explanation (Phase 13).

SHAP explains the MODEL's reasoning at the account-window level. This
module answers the investigator-facing question at the RING CANDIDATE
level: every alert must be traceable to WHO / WHAT / WHEN / WHERE /
HOW / WHY, using only evidence already computed by earlier phases —
nothing invented here.

"HOW EARLY" is deliberately left as a placeholder pointing to Phase
15's lead-time engine rather than guessed at here — lead time is a
specific, carefully-defined quantity (observable_time - warning_time)
that this module has no way to compute correctly in isolation.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ForensicExplanation:
    candidate_ring_id: str
    who: dict
    what: dict
    when: dict
    where: dict
    how: dict
    why: dict
    how_early: dict

    def to_dict(self) -> dict:
        return {
            "candidate_ring_id": self.candidate_ring_id,
            "who": self.who, "what": self.what, "when": self.when,
            "where": self.where, "how": self.how, "why": self.why, "how_early": self.how_early,
        }


def build_forensic_explanation(candidate, risk_result=None) -> ForensicExplanation:
    who = {
        "accounts": candidate.accounts,
        "n_accounts": len(candidate.accounts),
        "account_roles": _infer_roles(candidate),
    }

    what = {
        "patterns_detected": candidate.patterns,
        "pattern_sequence": candidate.trajectory.get("pattern_sequence", []),
        "description": _describe_patterns(candidate.patterns),
    }

    when = {
        "time_span_start": candidate.time_span[0],
        "time_span_end": candidate.time_span[1],
        "formation_stage": candidate.formation_stage,
        "formation_stage_is_provisional": candidate.formation_stage_is_provisional,
    }

    where = {
        "network_statistics": candidate.network_statistics,
        "evidence_density": candidate.network_statistics.get("density"),
    }

    how = {
        "transaction_ids": candidate.transaction_ids,
        "n_transactions": len(candidate.transaction_ids),
        "evidence_event_count": candidate.evidence_event_count,
        "source_trajectory_id": candidate.source_trajectory_id,
    }

    if risk_result is not None:
        why = {
            "risk_score": risk_result.risk_score,
            "risk_level": risk_result.risk_level,
            "score_components": risk_result.score_components,
            "top_factors": risk_result.top_factors,
            "disclaimer": "A risk score indicates investigative priority and does not establish criminal guilt.",
        }
    else:
        why = {
            "risk_score": candidate.risk_score,
            "note": "Not yet evaluated" if candidate.risk_score is None else None,
            "disclaimer": "A risk score indicates investigative priority and does not establish criminal guilt.",
        }

    how_early = {
        "warning_time": None,
        "observable_time": None,
        "lead_time": None,
        "note": "Computed by the lead-time engine (Phase 15), not this module.",
    }

    return ForensicExplanation(
        candidate_ring_id=candidate.candidate_ring_id,
        who=who, what=what, when=when, where=where, how=how, why=why, how_early=how_early,
    )


def _infer_roles(candidate) -> dict:
    roles = {}
    seq_types = candidate.trajectory.get("pattern_sequence", [])
    if "fan_in" in seq_types:
        roles.setdefault("possible_collector", []).append("see fan_in evidence for central account")
    if "fan_out" in seq_types:
        roles.setdefault("possible_distributor", []).append("see fan_out evidence for central account")
    if "repeated_intermediary" in seq_types:
        roles.setdefault("possible_mule", []).append("see repeated_intermediary evidence for central account")
    return roles


def _describe_patterns(patterns: list) -> str:
    if not patterns:
        return "No fund-flow patterns recorded."
    descriptions = {
        "fan_in": "multiple accounts converging funds into one",
        "fan_out": "one account distributing funds to many",
        "layering": "rapid multi-hop pass-through of funds",
        "split_merge": "funds split across accounts then recombined",
        "circular_flow": "funds returning to their origin",
        "repeated_intermediary": "an account repeatedly used as a pass-through",
        "rapid_pass_through": "funds held only briefly before forwarding",
        "escalating_connectivity": "growing network connectivity over time",
    }
    parts = [descriptions.get(p, p) for p in sorted(set(patterns))]
    return "; ".join(parts).capitalize() + "."

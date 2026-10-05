"""
Shared evidence structure for all fund-flow pattern detectors.

Every detector in this package (fan_in, fan_out, layering, split_merge,
circular_flow, repeated_intermediary, rapid_pass_through, escalating
connectivity) returns a list of PatternEvent — never a bare boolean.
This is what makes every alert traceable to WHO/WHAT/WHEN evidence
later in the forensic evidence engine (Phase 14).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class PatternEvent:
    pattern_type: str            # "fan_in" | "fan_out" | "layering" | ...
    window_id: int
    timestamp: str               # ISO timestamp of the pattern's anchor event
    central_account: str         # the account the pattern is centered on
    accounts: list                # all accounts involved
    transaction_ids: list
    pattern_strength: float       # detector-specific severity score in [0, 1]
    evidence: dict = field(default_factory=dict)  # detector-specific supporting detail

    def to_dict(self) -> dict:
        return asdict(self)

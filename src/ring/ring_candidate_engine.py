"""
Ring Candidate Engine — Phase 9

Converts temporal pattern trajectories into evidence-backed ring candidates.

Design principles
-----------------
1. Never use the ambient transaction graph to define a ring.
2. Use only transactions belonging to detected pattern events.
3. Keep candidate formation temporally bounded.
4. Avoid transitive "giant blob" merging.
5. Weak signals such as rapid_pass_through must support a structural
   pattern rather than create thousands of candidates by themselves.
6. A candidate must contain meaningful structural evidence.
7. Preserve the temporal trajectory needed by the lead-time engine.
8. Formation stage is provisional until Phase 15 evaluates the candidate.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

import networkx as nx
import pandas as pd

from src.graph.graph_ops import snapshot_stats


# ---------------------------------------------------------------------------
# Pattern categories
# ---------------------------------------------------------------------------

# Structural patterns can establish the core of a candidate.
_STRUCTURAL_TYPES = {
    "fan_in",
    "fan_out",
    "layering",
    "repeated_intermediary",
}

# Supporting patterns should strengthen an existing structural candidate.
_SUPPORT_TYPES = {
    "circular_flow",
    "split_merge",
    "rapid_pass_through",
    "escalating_connectivity",
}


# ---------------------------------------------------------------------------
# Formation-stage rules
# ---------------------------------------------------------------------------

_STAGE_RULES_ORDER = [
    (
        "OBSERVABLE_RING",
        lambda types: (
            "circular_flow" in types
            and len(types) >= 3
        ),
    ),
    (
        "EMERGING",
        lambda types: len(types) >= 3,
    ),
    (
        "FORMING",
        lambda types: len(types) >= 2,
    ),
    (
        "WATCH",
        lambda types: len(types) >= 1,
    ),
]


def _interim_formation_stage(pattern_types: set[str]) -> str:
    """
    Assign a provisional formation stage.

    This is NOT the final risk/evaluation stage.
    """
    for label, rule in _STAGE_RULES_ORDER:
        if rule(pattern_types):
            return label

    return "WATCH"


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------

def _is_real_timestamp(ts) -> bool:
    """
    Return True only for actual transaction/event timestamps.

    Synthetic feature events may contain values such as:

        window_109_to_111

    Those are intentionally excluded from temporal arithmetic.
    """
    try:
        parsed = pd.Timestamp(ts)

        # Synthetic window identifiers must never be treated as dates.
        if str(ts).startswith("window_"):
            return False

        return pd.notna(parsed)

    except Exception:
        return False


def _safe_timestamp(ts):
    """
    Convert an event timestamp to pandas Timestamp.

    Returns None for synthetic/non-date timestamps.
    """
    if not _is_real_timestamp(ts):
        return None

    try:
        return pd.Timestamp(ts)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Evidence graph
# ---------------------------------------------------------------------------

def _build_evidence_graph(
    df: pd.DataFrame,
    transaction_ids: set,
) -> nx.MultiDiGraph:
    """
    Build a graph ONLY from transactions explicitly identified as evidence.
    """

    if not transaction_ids:
        return nx.MultiDiGraph()

    rows = df[df["transaction_id"].isin(transaction_ids)]

    graph = nx.MultiDiGraph()

    for row in rows.itertuples(index=False):
        graph.add_edge(
            row.sender,
            row.receiver,
            transaction_id=row.transaction_id,
            amount=row.amount,
            timestamp=row.timestamp,
        )

    return graph


# ---------------------------------------------------------------------------
# RingCandidate
# ---------------------------------------------------------------------------

@dataclass
class RingCandidate:
    candidate_ring_id: str

    accounts: list = field(default_factory=list)

    transaction_ids: list = field(default_factory=list)

    time_span: list = field(default_factory=list)

    patterns: list = field(default_factory=list)

    trajectory: dict = field(default_factory=dict)

    network_statistics: dict = field(default_factory=dict)

    formation_stage: str = "WATCH"

    formation_stage_is_provisional: bool = True

    risk_score: object = None

    evidence_event_count: int = 0

    source_trajectory_id: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Central-account clustering
# ---------------------------------------------------------------------------

def _central_account_clusters(
    union_events: list,
) -> list[list]:
    """
    Cluster structural events using CENTRAL accounts as bridges.

    Important:

    We deliberately do NOT connect two events merely because they share
    any peripheral account.

    Example:

        fan_in(A, B, C, D)
        fan_in(E, F, G, H)

    These should not merge merely because one incidental participant later
    appears elsewhere.

    A structural cluster is formed when a central account participates in
    another structural event as a central account or bridge.
    """

    if not union_events:
        return []

    central_accounts = {
        str(e.central_account)
        for e in union_events
        if e.central_account is not None
    }

    if not central_accounts:
        return []

    parent = {account: account for account in central_accounts}

    def find(account):
        parent.setdefault(account, account)

        while parent[account] != account:
            parent[account] = parent[parent[account]]
            account = parent[account]

        return account

    def union(a, b):
        ra = find(a)
        rb = find(b)

        if ra != rb:
            parent[ra] = rb

    events_by_central = {}

    for event in union_events:
        central = str(event.central_account)

        events_by_central.setdefault(
            central,
            [],
        ).append(event)

    # Only allow a central account to bridge structural events.
    for event in union_events:

        event_central = str(event.central_account)

        for account in event.accounts:

            account = str(account)

            if account == event_central:
                continue

            if account in central_accounts:
                union(event_central, account)

    clusters = {}

    for central in central_accounts:

        root = find(central)

        clusters.setdefault(
            root,
            [],
        ).extend(
            events_by_central.get(central, [])
        )

    return list(clusters.values())


# ---------------------------------------------------------------------------
# Ring Candidate Engine
# ---------------------------------------------------------------------------

class RingCandidateEngine:

    def __init__(
        self,
        df: pd.DataFrame,
        trajectories: dict,
        config: dict,
    ):

        self.df = df

        self.trajectories = trajectories

        cfg = config.get(
            "ring_candidates",
            {},
        )

        # Minimum number of accounts in evidence graph.
        self.min_accounts = int(
            cfg.get(
                "min_accounts",
                3,
            )
        )

        # Minimum number of evidence events.
        self.min_pattern_count = int(
            cfg.get(
                "min_pattern_count",
                2,
            )
        )

        # Formation episode maximum gap.
        self.max_formation_gap_days = float(
            cfg.get(
                "max_formation_gap_days",
                10,
            )
        )

        # Maximum time between structural and supporting evidence.
        self.support_gap_days = float(
            cfg.get(
                "support_gap_days",
                10,
            )
        )

        # Minimum number of shared accounts required for a weak event
        # to attach when it does NOT share the central account.
        self.min_support_overlap = int(
            cfg.get(
                "min_support_overlap",
                2,
            )
        )

    # ------------------------------------------------------------------
    # Formation batches
    # ------------------------------------------------------------------

    def _formation_batches(
        self,
        trajectory,
    ) -> list[list]:

        """
        Split a trajectory into bounded temporal formation episodes.

        IMPORTANT:

        We use the actual timestamps of pattern events.

        Synthetic timestamps such as:

            window_109_to_111

        are not parsed as dates.
        """

        timed = []

        untimed = []

        for event in trajectory.events:

            timestamp = _safe_timestamp(
                event.timestamp
            )

            if timestamp is None:
                untimed.append(event)
            else:
                timed.append(
                    (
                        event,
                        timestamp,
                    )
                )

        timed.sort(
            key=lambda x: x[1]
        )

        if not timed:

            return (
                [list(trajectory.events)]
                if trajectory.events
                else []
            )

        batches = [
            [timed[0][0]]
        ]

        batch_start = timed[0][1]

        previous_timestamp = timed[0][1]

        for event, timestamp in timed[1:]:

            # IMPORTANT:
            #
            # We measure the entire episode from its START,
            # not only consecutive gaps.
            #
            # This prevents:
            #
            # day 1 → day 10 → day 19
            #
            # from becoming one 18-day formation episode
            # merely because each adjacent gap is <= 10 days.

            span_days = (
                timestamp - batch_start
            ).total_seconds() / 86400.0

            gap_days = (
                timestamp - previous_timestamp
            ).total_seconds() / 86400.0

            if (
                span_days > self.max_formation_gap_days
                or gap_days > self.max_formation_gap_days
            ):

                batches.append([])

                batch_start = timestamp

            batches[-1].append(event)

            previous_timestamp = timestamp

        # --------------------------------------------------------------
        # Attach synthetic events carefully.
        #
        # They are NOT allowed to create a new temporal episode.
        # They can only attach to an existing episode if they share
        # meaningful structural accounts.
        # --------------------------------------------------------------

        for event in untimed:

            event_accounts = {
                str(a)
                for a in event.accounts
            }

            best_batch = None

            best_overlap = 0

            for batch in batches:

                batch_accounts = {
                    str(a)
                    for existing in batch
                    for a in existing.accounts
                }

                overlap = len(
                    event_accounts
                    & batch_accounts
                )

                if overlap > best_overlap:

                    best_overlap = overlap

                    best_batch = batch

            if (
                best_batch is not None
                and best_overlap >= self.min_support_overlap
            ):

                best_batch.append(event)

        return batches

    # ------------------------------------------------------------------
    # Structural qualification
    # ------------------------------------------------------------------

    def _candidate_qualifies(
        self,
        pattern_types: set[str],
        local_events: list,
    ) -> bool:

        """
        Decide whether an evidence episode is strong enough to become
        a formal ring candidate.

        This is the most important anti-noise gate.

        We do NOT allow:

            fan_in + rapid_pass_through

        alone to generate thousands of ring candidates.

        Structural evidence must form the core.
        """

        structural = (
            pattern_types
            & _STRUCTURAL_TYPES
        )

        support = (
            pattern_types
            & _SUPPORT_TYPES
        )

        # Need at least one structural pattern.
        if not structural:
            return False

        # --------------------------------------------------------------
        # Rule 1:
        # Two different structural patterns.
        #
        # Examples:
        #
        # fan_in + layering
        # fan_in + fan_out
        # fan_in + repeated_intermediary
        # layering + repeated_intermediary
        # --------------------------------------------------------------

        if len(structural) >= 2:
            return True

        # --------------------------------------------------------------
        # Rule 2:
        # Circular flow is a strong structural confirmation.
        #
        # A structural pattern + circular flow is meaningful.
        # --------------------------------------------------------------

        if (
            "circular_flow" in support
            and len(structural) >= 1
        ):
            return True

        # --------------------------------------------------------------
        # Rule 3:
        # Structural pattern + split_merge.
        # --------------------------------------------------------------

        if (
            "split_merge" in support
            and len(structural) >= 1
        ):
            return True

        # --------------------------------------------------------------
        # Rule 4:
        # Structural pattern + escalating connectivity.
        # --------------------------------------------------------------

        if (
            "escalating_connectivity" in support
            and len(structural) >= 1
        ):
            return True

        # --------------------------------------------------------------
        # IMPORTANT:
        #
        # fan_in + rapid_pass_through is NOT sufficient.
        #
        # fan_out + rapid_pass_through is NOT sufficient.
        #
        # layering + rapid_pass_through is NOT sufficient.
        #
        # repeated_intermediary + rapid_pass_through is NOT sufficient.
        #
        # This is what prevents the current thousands of candidates.
        # --------------------------------------------------------------

        return False

    # ------------------------------------------------------------------
    # Supporting-event attachment
    # ------------------------------------------------------------------

    def _attach_support_events(
        self,
        structural_events: list,
        support_events: list,
    ) -> list:

        """
        Attach supporting evidence to a structural cluster.

        Supporting evidence must satisfy:

        1. Temporal proximity.
        2. Meaningful account overlap.
        3. Preferably overlap with a central account.

        Crucially, the account boundary is FROZEN.

        We never allow:

            weak event → new accounts → another weak event → new accounts

        because that creates cascading network growth.
        """

        if not structural_events:
            return []

        original_accounts = {
            str(account)
            for event in structural_events
            for account in event.accounts
        }

        central_accounts = {
            str(event.central_account)
            for event in structural_events
            if event.central_account is not None
        }

        structural_times = [
            _safe_timestamp(event.timestamp)
            for event in structural_events
        ]

        structural_times = [
            t
            for t in structural_times
            if t is not None
        ]

        attached = []

        for event in support_events:

            event_accounts = {
                str(account)
                for account in event.accounts
            }

            # ----------------------------------------------------------
            # Account overlap
            # ----------------------------------------------------------

            central_overlap = (
                event_accounts
                & central_accounts
            )

            total_overlap = (
                event_accounts
                & original_accounts
            )

            # Central overlap gets priority.
            if central_overlap:

                account_match = True

            elif len(total_overlap) >= self.min_support_overlap:

                account_match = True

            else:

                account_match = False

            if not account_match:
                continue

            # ----------------------------------------------------------
            # Temporal overlap
            # ----------------------------------------------------------

            event_time = _safe_timestamp(
                event.timestamp
            )

            # Synthetic event:
            # account evidence is enough because it cannot be
            # meaningfully compared by timestamp.
            if event_time is None:

                attached.append(event)

                continue

            if not structural_times:
                continue

            nearest_gap = min(
                abs(
                    (
                        event_time
                        - structural_time
                    ).total_seconds()
                ) / 86400.0
                for structural_time in structural_times
            )

            if nearest_gap <= self.support_gap_days:

                attached.append(event)

        return attached

    # ------------------------------------------------------------------
    # Build candidates
    # ------------------------------------------------------------------

    def build(self) -> list:

        candidates = []

        counter = 0

        for trajectory_id, trajectory in self.trajectories.items():

            batches = self._formation_batches(
                trajectory
            )

            for batch in batches:

                if not batch:
                    continue

                # ------------------------------------------------------
                # Separate structural and supporting evidence.
                # ------------------------------------------------------

                structural_events = [
                    event
                    for event in batch
                    if event.pattern_type
                    in _STRUCTURAL_TYPES
                ]

                support_events = [
                    event
                    for event in batch
                    if event.pattern_type
                    in _SUPPORT_TYPES
                ]

                if not structural_events:
                    continue

                # ------------------------------------------------------
                # Structural clustering.
                # ------------------------------------------------------

                clusters = _central_account_clusters(
                    structural_events
                )

                for cluster_events in clusters:

                    if not cluster_events:
                        continue

                    # --------------------------------------------------
                    # Structural accounts
                    # --------------------------------------------------

                    structural_accounts = {
                        str(account)
                        for event in cluster_events
                        for account in event.accounts
                    }

                    if (
                        len(structural_accounts)
                        < self.min_accounts
                    ):
                        continue

                    # --------------------------------------------------
                    # Structural pattern types
                    # --------------------------------------------------

                    structural_types = {
                        event.pattern_type
                        for event in cluster_events
                    }

                    # --------------------------------------------------
                    # Attach supporting evidence.
                    # --------------------------------------------------

                    attached_support = (
                        self._attach_support_events(
                            cluster_events,
                            support_events,
                        )
                    )

                    local_events = (
                        list(cluster_events)
                        + attached_support
                    )

                    pattern_types = {
                        event.pattern_type
                        for event in local_events
                    }

                    # --------------------------------------------------
                    # Candidate qualification.
                    # --------------------------------------------------

                    if not self._candidate_qualifies(
                        pattern_types,
                        local_events,
                    ):
                        continue

                    if (
                        len(local_events)
                        < self.min_pattern_count
                    ):
                        continue

                    # --------------------------------------------------
                    # Freeze account boundary.
                    #
                    # Supporting events may contribute their accounts,
                    # but only once. They cannot recursively trigger
                    # more support events.
                    # --------------------------------------------------

                    candidate_accounts = set(
                        structural_accounts
                    )

                    for event in attached_support:

                        candidate_accounts.update(
                            str(account)
                            for account in event.accounts
                        )

                    if (
                        len(candidate_accounts)
                        < self.min_accounts
                    ):
                        continue

                    # --------------------------------------------------
                    # Evidence transaction IDs
                    # --------------------------------------------------

                    transaction_ids = set()

                    for event in local_events:

                        transaction_ids.update(
                            str(tx_id)
                            for tx_id
                            in event.transaction_ids
                        )

                    if not transaction_ids:
                        continue

                    # --------------------------------------------------
                    # Evidence graph
                    # --------------------------------------------------

                    evidence_graph = (
                        _build_evidence_graph(
                            self.df,
                            transaction_ids,
                        )
                    )

                    if evidence_graph.number_of_nodes() == 0:
                        continue

                    stats = snapshot_stats(
                        evidence_graph
                    )

                    # --------------------------------------------------
                    # Time span
                    # --------------------------------------------------

                    timestamps = [
                        _safe_timestamp(
                            event.timestamp
                        )
                        for event in local_events
                    ]

                    timestamps = [
                        timestamp
                        for timestamp in timestamps
                        if timestamp is not None
                    ]

                    if timestamps:

                        start_time = min(timestamps)

                        end_time = max(timestamps)

                        time_span = [
                            start_time.isoformat(),
                            end_time.isoformat(),
                        ]

                    else:

                        time_span = [
                            None,
                            None,
                        ]

                    # --------------------------------------------------
                    # Sort events chronologically.
                    # --------------------------------------------------

                    local_events.sort(
                        key=lambda event: (
                            _safe_timestamp(
                                event.timestamp
                            )
                            or pd.Timestamp.max
                        )
                    )

                    pattern_sequence = [
                        event.pattern_type
                        for event in local_events
                    ]

                    pattern_types_present = sorted(
                        set(pattern_sequence)
                    )

                    # --------------------------------------------------
                    # Deduplicate candidates.
                    #
                    # Two clusters can sometimes produce identical
                    # evidence. Use structural account set + transaction
                    # set + time span as a deterministic signature.
                    # --------------------------------------------------

                    candidate_signature = (
                        tuple(sorted(candidate_accounts)),
                        tuple(sorted(transaction_ids)),
                        tuple(pattern_types_present),
                    )

                    # Lazy-initialised set on first use.
                    if not hasattr(
                        self,
                        "_candidate_signatures",
                    ):
                        self._candidate_signatures = set()

                    if (
                        candidate_signature
                        in self._candidate_signatures
                    ):
                        continue

                    self._candidate_signatures.add(
                        candidate_signature
                    )

                    # --------------------------------------------------
                    # Candidate ID
                    # --------------------------------------------------

                    counter += 1

                    candidate_id = (
                        f"RING{counter:03d}"
                    )

                    # --------------------------------------------------
                    # Final candidate
                    # --------------------------------------------------

                    candidates.append(
                        RingCandidate(
                            candidate_ring_id=candidate_id,

                            accounts=sorted(
                                candidate_accounts
                            ),

                            transaction_ids=sorted(
                                transaction_ids
                            ),

                            time_span=time_span,

                            patterns=pattern_types_present,

                            trajectory={
                                "pattern_count": len(
                                    local_events
                                ),

                                "pattern_diversity": len(
                                    pattern_types_present
                                ),

                                "pattern_sequence": (
                                    pattern_sequence
                                ),

                                "event_window_ids": [
                                    event.window_id
                                    for event
                                    in local_events
                                ],

                                "structural_pattern_types": (
                                    sorted(
                                        structural_types
                                    )
                                ),

                                "supporting_pattern_types": sorted(
                                    pattern_types
                                    - structural_types
                                ),
                            },

                            network_statistics={
                                "n_nodes": (
                                    stats.n_nodes
                                ),

                                "n_edges": (
                                    stats.n_edges
                                ),

                                "density": round(
                                    stats.density,
                                    4,
                                ),

                                "weakly_connected_components": (
                                    stats.weakly_connected_components
                                ),

                                "strongly_connected_components": (
                                    stats.strongly_connected_components
                                ),

                                "largest_scc_size": (
                                    stats.largest_scc_size
                                ),
                            },

                            formation_stage=(
                                _interim_formation_stage(
                                    set(
                                        pattern_types_present
                                    )
                                )
                            ),

                            formation_stage_is_provisional=True,

                            risk_score=None,

                            evidence_event_count=len(
                                local_events
                            ),

                            source_trajectory_id=(
                                trajectory_id
                            ),
                        )
                    )

        return candidates
"""
Pattern Trajectory Engine
=========================

Purpose
-------
Track WHEN suspicious fund-flow patterns appear, WHETHER they persist,
WHETHER they combine with other pattern types, and WHETHER an emerging
ring-like structure is forming.

Design
------
The previous implementation used global/transitive account connectivity.
That allowed unrelated activity to become one giant trajectory.

This implementation uses bounded temporal formation episodes.

A structural event can join an existing trajectory only when:

1. It occurs within MAX_SPAN_DAYS from the trajectory start.
2. It shares at least MIN_SHARED_ACCOUNTS with that trajectory.

Weak/supporting events cannot create trajectories.

Weak events can attach only when they:
1. Have a valid timestamp.
2. Share at least MIN_SHARED_ACCOUNTS accounts.
3. Are temporally close to the trajectory.

Important
---------
AML ground-truth labels are NOT used during trajectory creation.
They are reserved for evaluation.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

import pandas as pd


# ============================================================
# PATTERN TYPES
# ============================================================

_STRUCTURAL_TYPES = {
    "fan_in",
    "fan_out",
    "layering",
    "split_merge",
    "circular_flow",
    "repeated_intermediary",
}


# These patterns are allowed to CREATE trajectories.
# They represent stronger structural evidence.
_UNION_TYPES = {
    "fan_in",
    "fan_out",
    "layering",
    "repeated_intermediary",
}


# Supporting patterns.
# They CANNOT create a trajectory by themselves.
_WEAK_TYPES = {
    "escalating_connectivity",
    "rapid_pass_through",
    "circular_flow",
    "split_merge",
}


# ============================================================
# PATTERN WEIGHTS
# ============================================================

_PATTERN_WEIGHT = {
    "fan_in": 1.0,
    "fan_out": 1.0,
    "layering": 2.0,
    "split_merge": 2.0,
    "repeated_intermediary": 2.0,
    "circular_flow": 3.0,
    "rapid_pass_through": 0.5,
    "escalating_connectivity": 0.5,
}


# ============================================================
# TRAJECTORY CONFIGURATION
# ============================================================

# Maximum formation period.
#
# Example:
# Event 1 -> Jan 1
# Event 2 -> Jan 5       OK
# Event 3 -> Jan 10      OK
# Event 4 -> Jan 12      REJECTED
#
# because Jan 12 is > 10 days from the trajectory start.
MAX_SPAN_DAYS = 10


# IMPORTANT:
#
# Previous value = 1
#
# That allowed:
#
# A-B
# B-C
# C-D
# D-E
#
# to become:
#
# A-B-C-D-E
#
# even though there was no strong multi-account overlap.
#
# Requiring 2 shared accounts dramatically reduces this
# transitive-cascade problem.
MIN_SHARED_ACCOUNTS = 2


# A trajectory needs at least two structural events.
MIN_STRUCTURAL_EVENTS = 2


# Prevent pathological giant trajectories.
#
# This is NOT a laundering assumption.
# It is a computational/forensic coherence safeguard.
#
# If a genuine ring is larger than this, the evidence graph can
# still contain the individual pattern events, but one trajectory
# should not automatically absorb thousands of accounts.
MAX_TRAJECTORY_ACCOUNTS = 100


# ============================================================
# TRAJECTORY DATA CLASS
# ============================================================

@dataclass
class Trajectory:

    candidate_id: str

    accounts: set = field(default_factory=set)

    events: list = field(default_factory=list)

    def to_summary_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "accounts": sorted(self.accounts),
            "n_accounts": len(self.accounts),
            "n_events": len(self.events),
            "pattern_sequence": [
                event.pattern_type
                for event in self.events
            ],
            "events": [
                event.to_dict()
                for event in self.events
            ],
        }


# ============================================================
# TIMESTAMP HELPERS
# ============================================================

def _parse_timestamp(value):
    """
    Safely convert a timestamp to pandas.Timestamp.

    Invalid synthetic window identifiers such as:

        window_109_to_111

    are rejected and return None.
    """

    if value is None:
        return None

    # Already a pandas timestamp
    if isinstance(value, pd.Timestamp):
        return value

    try:

        timestamp = pd.Timestamp(value)

        # Defensive protection against non-date window IDs.
        if str(value).startswith("window_"):
            return None

        return timestamp

    except (
        TypeError,
        ValueError,
        OverflowError,
        pd.errors.ParserError,
    ):
        return None


def _normalize_events(events):
    """
    Normalize timestamps and accounts exactly once.

    This avoids repeatedly calling pd.Timestamp() inside nested loops.
    """

    normalized = []

    for event in events:

        timestamp = _parse_timestamp(
            getattr(event, "timestamp", None)
        )

        raw_accounts = getattr(
            event,
            "accounts",
            []
        )

        accounts = {
            str(account)
            for account in (raw_accounts or [])
            if account is not None
        }

        normalized.append(
            {
                "event": event,
                "timestamp": timestamp,
                "accounts": accounts,
            }
        )

    return normalized


# ============================================================
# TRAJECTORY GROUPING
# ============================================================

def group_events_into_trajectories(events: list) -> dict:
    """
    Build bounded temporal formation trajectories.

    Structural events create trajectories.

    Weak events only attach to existing trajectories.

    No global Union-Find is used.

    The algorithm uses an account index so that an event is compared
    only against potentially relevant trajectories.
    """

    if not events:
        return {}

    # ========================================================
    # 1. NORMALIZE EVENTS
    # ========================================================

    normalized = _normalize_events(events)

    # ========================================================
    # 2. SEPARATE STRUCTURAL / WEAK EVENTS
    # ========================================================

    structural = []
    weak = []

    for item in normalized:

        event = item["event"]

        if event.pattern_type in _UNION_TYPES:

            structural.append(item)

        else:

            weak.append(item)

    # ========================================================
    # 3. REMOVE INVALID STRUCTURAL EVENTS
    # ========================================================

    structural = [
        item
        for item in structural
        if item["timestamp"] is not None
        and len(item["accounts"]) >= 2
    ]

    # Chronological processing is essential.
    structural.sort(
        key=lambda item: item["timestamp"]
    )

    # ========================================================
    # 4. BUILD TEMPORAL FORMATION EPISODES
    # ========================================================

    episodes = []

    # Account -> episode IDs.
    #
    # This lets us find only episodes sharing an account.
    account_to_episodes = defaultdict(set)

    # Episodes are chronological.
    active_episode_ids = deque()

    for item in structural:

        event = item["event"]

        event_time = item["timestamp"]

        event_accounts = item["accounts"]

        # ----------------------------------------------------
        # Remove expired episodes.
        # ----------------------------------------------------

        while active_episode_ids:

            episode_id = active_episode_ids[0]

            episode = episodes[episode_id]

            age_days = (
                event_time - episode["start_time"]
            ).total_seconds() / 86400.0

            if age_days <= MAX_SPAN_DAYS:

                break

            active_episode_ids.popleft()

            for account in episode["accounts"]:

                account_to_episodes[account].discard(
                    episode_id
                )

        # ----------------------------------------------------
        # Find candidate episodes through shared accounts.
        # ----------------------------------------------------

        candidate_episode_ids = set()

        for account in event_accounts:

            candidate_episode_ids.update(
                account_to_episodes.get(
                    account,
                    set()
                )
            )

        # ----------------------------------------------------
        # Find compatible episode.
        # ----------------------------------------------------

        selected_episode_id = None

        selected_score = None

        for episode_id in candidate_episode_ids:

            episode = episodes[episode_id]

            # -----------------------------------------------
            # Temporal constraint.
            # -----------------------------------------------

            age_days = (
                event_time - episode["start_time"]
            ).total_seconds() / 86400.0

            if age_days < 0:

                continue

            if age_days > MAX_SPAN_DAYS:

                continue

            # -----------------------------------------------
            # Multi-account coherence.
            # -----------------------------------------------

            shared_accounts = (
                event_accounts
                & episode["accounts"]
            )

            shared_count = len(shared_accounts)

            if shared_count < MIN_SHARED_ACCOUNTS:

                continue

            # -----------------------------------------------
            # Check resulting trajectory size.
            # -----------------------------------------------

            resulting_accounts = (
                episode["accounts"]
                | event_accounts
            )

            if len(resulting_accounts) > MAX_TRAJECTORY_ACCOUNTS:

                continue

            # -----------------------------------------------
            # Score compatibility.
            #
            # More shared accounts = stronger relationship.
            #
            # If tied, prefer the more recent episode.
            # -----------------------------------------------

            score = (
                shared_count,
                episode["start_time"]
            )

            if (
                selected_score is None
                or score > selected_score
            ):

                selected_episode_id = episode_id

                selected_score = score

        # ====================================================
        # 4A. EXTEND EXISTING EPISODE
        # ====================================================

        if selected_episode_id is not None:

            episode = episodes[
                selected_episode_id
            ]

            episode["events"].append(
                event
            )

            episode["accounts"].update(
                event_accounts
            )

            episode["end_time"] = event_time

            # Update account index.
            for account in event_accounts:

                account_to_episodes[account].add(
                    selected_episode_id
                )

        # ====================================================
        # 4B. CREATE NEW EPISODE
        # ====================================================

        else:

            episode_id = len(episodes)

            episode = {
                "start_time": event_time,
                "end_time": event_time,
                "events": [event],
                "accounts": set(event_accounts),
            }

            episodes.append(
                episode
            )

            active_episode_ids.append(
                episode_id
            )

            for account in event_accounts:

                account_to_episodes[account].add(
                    episode_id
                )

    # ========================================================
    # 5. REMOVE SINGLE-EVENT EPISODES
    # ========================================================

    episodes = [
        episode
        for episode in episodes
        if len(episode["events"])
        >= MIN_STRUCTURAL_EVENTS
    ]

    # ========================================================
    # 6. CONVERT STRUCTURAL EPISODES TO TRAJECTORIES
    # ========================================================

    trajectories = []

    for episode in episodes:

        trajectory = Trajectory(
            candidate_id="",

            accounts=set(
                episode["accounts"]
            ),

            events=list(
                episode["events"]
            ),
        )

        trajectories.append(
            trajectory
        )

    # ========================================================
    # 7. PRE-COMPUTE TRAJECTORY METADATA
    # ========================================================

    trajectory_metadata = {}

    for trajectory_id, trajectory in enumerate(
        trajectories
    ):

        valid_times = []

        for event in trajectory.events:

            timestamp = _parse_timestamp(
                event.timestamp
            )

            if timestamp is not None:

                valid_times.append(
                    timestamp
                )

        if not valid_times:

            continue

        trajectory_metadata[
            trajectory_id
        ] = {
            "start_time": min(valid_times),
            "end_time": max(valid_times),
        }

    # ========================================================
    # 8. BUILD ACCOUNT -> TRAJECTORY INDEX
    # ========================================================

    account_to_trajectories = defaultdict(set)

    for trajectory_id, trajectory in enumerate(
        trajectories
    ):

        for account in trajectory.accounts:

            account_to_trajectories[
                account
            ].add(
                trajectory_id
            )

    # ========================================================
    # 9. NORMALIZE WEAK EVENTS
    # ========================================================

    weak = [
        item
        for item in weak
        if item["timestamp"] is not None
        and len(item["accounts"]) >= MIN_SHARED_ACCOUNTS
    ]

    weak.sort(
        key=lambda item: item["timestamp"]
    )

    # ========================================================
    # 10. ATTACH WEAK EVENTS
    # ========================================================

    for item in weak:

        event = item["event"]

        event_time = item["timestamp"]

        event_accounts = item["accounts"]

        # ----------------------------------------------------
        # Candidate trajectories sharing at least one account.
        # ----------------------------------------------------

        candidate_trajectory_ids = set()

        for account in event_accounts:

            candidate_trajectory_ids.update(
                account_to_trajectories.get(
                    account,
                    set()
                )
            )

        # ----------------------------------------------------
        # Evaluate each candidate trajectory.
        # ----------------------------------------------------

        best_trajectory_id = None

        best_score = None

        for trajectory_id in candidate_trajectory_ids:

            metadata = trajectory_metadata.get(
                trajectory_id
            )

            if metadata is None:

                continue

            trajectory = trajectories[
                trajectory_id
            ]

            # -----------------------------------------------
            # Temporal compatibility.
            # -----------------------------------------------

            start_time = metadata["start_time"]

            end_time = metadata["end_time"]

            distance_from_start = abs(
                (
                    event_time
                    - start_time
                ).total_seconds()
            ) / 86400.0

            distance_from_end = abs(
                (
                    event_time
                    - end_time
                ).total_seconds()
            ) / 86400.0

            if min(
                distance_from_start,
                distance_from_end,
            ) > MAX_SPAN_DAYS:

                continue

            # -----------------------------------------------
            # Multi-account coherence.
            # -----------------------------------------------

            shared_accounts = (
                event_accounts
                & trajectory.accounts
            )

            shared_count = len(
                shared_accounts
            )

            if shared_count < MIN_SHARED_ACCOUNTS:

                continue

            # -----------------------------------------------
            # Do not let weak evidence create a giant
            # trajectory.
            # -----------------------------------------------

            resulting_accounts = (
                trajectory.accounts
                | event_accounts
            )

            if (
                len(resulting_accounts)
                > MAX_TRAJECTORY_ACCOUNTS
            ):

                continue

            # -----------------------------------------------
            # Select strongest compatible trajectory.
            # -----------------------------------------------

            distance = min(
                distance_from_start,
                distance_from_end,
            )

            score = (
                shared_count,
                -distance,
            )

            if (
                best_score is None
                or score > best_score
            ):

                best_score = score

                best_trajectory_id = (
                    trajectory_id
                )

        # ----------------------------------------------------
        # Attach weak event only to best trajectory.
        # ----------------------------------------------------

        if best_trajectory_id is not None:

            trajectory = trajectories[
                best_trajectory_id
            ]

            trajectory.events.append(
                event
            )

            trajectory.accounts.update(
                event_accounts
            )

    # ========================================================
    # 11. REMOVE PATHOLOGICAL TRAJECTORIES
    # ========================================================

    trajectories = [
        trajectory
        for trajectory in trajectories
        if (
            len(trajectory.events)
            >= MIN_STRUCTURAL_EVENTS
            and len(trajectory.accounts)
            <= MAX_TRAJECTORY_ACCOUNTS
        )
    ]

    # ========================================================
    # 12. SORT TRAJECTORIES
    # ========================================================

    def trajectory_start_time(trajectory):

        timestamps = []

        for event in trajectory.events:

            timestamp = _parse_timestamp(
                event.timestamp
            )

            if timestamp is not None:

                timestamps.append(
                    timestamp
                )

        if timestamps:

            return min(timestamps)

        return pd.Timestamp.max

    trajectories.sort(
        key=trajectory_start_time
    )

    # ========================================================
    # 13. ASSIGN TRAJECTORY IDs
    # ========================================================

    final = {}

    for index, trajectory in enumerate(
        trajectories,
        start=1,
    ):

        candidate_id = (
            f"TRAJ{index:04d}"
        )

        trajectory.candidate_id = (
            candidate_id
        )

        # Sort events chronologically.
        trajectory.events.sort(
            key=lambda event: (
                _parse_timestamp(
                    event.timestamp
                )
                if _parse_timestamp(
                    event.timestamp
                ) is not None
                else pd.Timestamp.min
            )
        )

        final[
            candidate_id
        ] = trajectory

    return final


# ============================================================
# TRAJECTORY FEATURES
# ============================================================

def compute_trajectory_features(
    traj: Trajectory,
) -> dict:

    events = traj.events

    if not events:

        return {}

    # ========================================================
    # PATTERN SEQUENCE
    # ========================================================

    pattern_types_seen = [
        event.pattern_type
        for event in events
    ]

    structural_seen = [
        pattern
        for pattern in pattern_types_seen
        if pattern in _STRUCTURAL_TYPES
    ]

    # ========================================================
    # WINDOW PERSISTENCE
    # ========================================================

    window_ids = sorted(
        {
            event.window_id
            for event in events
        }
    )

    persistence = 1

    best = 1

    for index in range(
        1,
        len(window_ids),
    ):

        if (
            window_ids[index]
            == window_ids[index - 1] + 1
        ):

            persistence += 1

            best = max(
                best,
                persistence,
            )

        else:

            persistence = 1

    # ========================================================
    # STRUCTURAL EVENTS
    # ========================================================

    structural_events_sorted = sorted(
        [
            event
            for event in events
            if event.pattern_type
            in _STRUCTURAL_TYPES
        ],
        key=lambda event: (
            _parse_timestamp(
                event.timestamp
            )
            if _parse_timestamp(
                event.timestamp
            ) is not None
            else pd.Timestamp.min
        ),
    )

    # ========================================================
    # PATTERN TRANSITIONS
    # ========================================================

    transitions = [
        (
            f"{structural_events_sorted[index].pattern_type}"
            f"->"
            f"{structural_events_sorted[index + 1].pattern_type}"
        )
        for index in range(
            len(structural_events_sorted) - 1
        )
    ]

    # ========================================================
    # PATTERN ESCALATION
    # ========================================================

    seen_types = set()

    escalation_steps = 0

    for pattern in pattern_types_seen:

        if pattern not in seen_types:

            if seen_types:

                escalation_steps += 1

            seen_types.add(pattern)

    # ========================================================
    # COMBINATION SCORE
    # ========================================================

    combination_score = sum(
        _PATTERN_WEIGHT.get(
            pattern,
            0.5,
        )
        for pattern in set(
            pattern_types_seen
        )
    )

    # ========================================================
    # FINAL FEATURES
    # ========================================================

    return {

        "candidate_id":
            traj.candidate_id,

        "n_accounts":
            len(traj.accounts),

        "pattern_count":
            len(events),

        "pattern_diversity":
            len(set(pattern_types_seen)),

        "pattern_persistence_windows":
            best,

        "n_consecutive_suspicious_windows":
            best,

        "first_suspicious_pattern":
            pattern_types_seen[0],

        "latest_suspicious_pattern":
            pattern_types_seen[-1],

        "pattern_transitions":
            transitions,

        "n_transitions":
            len(transitions),

        "pattern_escalation_steps":
            escalation_steps,

        "pattern_combination_score":
            round(
                combination_score,
                2,
            ),

        "has_structural_sequence":
            len(structural_seen) >= 2,

        "window_span":
            [
                window_ids[0],
                window_ids[-1],
            ],
    }


# ============================================================
# BUILD ALL TRAJECTORIES
# ============================================================

def build_all_trajectories(events: list):

    trajectories = (
        group_events_into_trajectories(
            events
        )
    )

    feature_rows = [
        compute_trajectory_features(
            trajectory
        )
        for trajectory
        in trajectories.values()
    ]

    features_df = pd.DataFrame(
        feature_rows
    )

    return trajectories, features_df
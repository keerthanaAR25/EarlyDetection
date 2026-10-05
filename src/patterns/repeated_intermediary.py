"""
Repeated intermediary detection.

An account is considered a repeated intermediary when it performs
multiple rapid pass-through events within a bounded temporal episode.

Important:
- Rapid pass-through determines whether one receive -> send pair
  qualifies as "rapid".
- Repeated intermediary groups those rapid events into temporal
  episodes instead of aggregating the account's entire history.
- This prevents historical transaction IDs from being attached to
  a much later repeated-intermediary event.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from src.patterns.base import PatternEvent
from src.patterns.rapid_pass_through import detect_rapid_pass_through


# Keep consistent with ring_candidates.max_formation_gap_days.
MAX_EPISODE_GAP_DAYS = 10


def detect_repeated_intermediary(
    df,
    window_bounds: list,
    max_hold_time_hours: float = 6,
    min_pass_through_count: int = 3,
) -> list[PatternEvent]:

    pass_through_events = detect_rapid_pass_through(
        df,
        window_bounds,
        max_hold_time_hours,
    )

    if not pass_through_events:
        return []

    # ---------------------------------------------------------
    # Group rapid pass-through events by central/intermediary
    # account.
    # ---------------------------------------------------------
    by_account = defaultdict(list)

    for ev in pass_through_events:
        by_account[ev.central_account].append(ev)

    results = []

    # ---------------------------------------------------------
    # Process each account independently.
    # ---------------------------------------------------------
    for account, events in by_account.items():

        # Events must be processed chronologically.
        events = sorted(
            events,
            key=lambda e: e.timestamp,
        )

        # -----------------------------------------------------
        # Build bounded temporal episodes.
        #
        # An event belongs to the current episode only when it
        # occurs within MAX_EPISODE_GAP_DAYS of the episode's
        # first event.
        # -----------------------------------------------------
        episodes = []
        current_episode = []
        episode_start = None

        for ev in events:

            try:
                current_timestamp = _parse_timestamp(ev.timestamp)
            except Exception:
                continue

            if episode_start is None:
                current_episode = [ev]
                episode_start = current_timestamp
                continue

            elapsed = current_timestamp - episode_start

            if elapsed <= timedelta(days=MAX_EPISODE_GAP_DAYS):
                current_episode.append(ev)
            else:
                # Close the previous episode.
                episodes.append(current_episode)

                # Start a new episode.
                current_episode = [ev]
                episode_start = current_timestamp

        if current_episode:
            episodes.append(current_episode)

        # -----------------------------------------------------
        # Convert sufficiently large episodes into
        # repeated-intermediary PatternEvents.
        # -----------------------------------------------------
        for episode in episodes:

            if len(episode) < min_pass_through_count:
                continue

            all_accounts = {account}
            all_tx_ids = []

            upstream_accounts = set()
            downstream_accounts = set()
            hold_times = []

            for ev in episode:

                all_accounts.update(ev.accounts)

                all_tx_ids.extend(
                    str(tx_id)
                    for tx_id in ev.transaction_ids
                )

                if ev.accounts:
                    upstream_accounts.add(
                        str(ev.accounts[0])
                    )

                if len(ev.accounts) >= 3:
                    downstream_accounts.add(
                        str(ev.accounts[-1])
                    )

                hold_time = ev.evidence.get("hold_time_hours")

                if hold_time is not None:
                    hold_times.append(
                        float(hold_time)
                    )

            # Remove duplicate transaction IDs while preserving
            # their first-seen order.
            all_tx_ids = list(
                dict.fromkeys(all_tx_ids)
            )

            first_event = min(
                episode,
                key=lambda e: e.timestamp,
            )

            last_event = max(
                episode,
                key=lambda e: e.timestamp,
            )

            strength = min(
                1.0,
                len(episode)
                / (min_pass_through_count * 2),
            )

            results.append(
                PatternEvent(
                    pattern_type="repeated_intermediary",

                    # The event is anchored to the final
                    # observation in THIS temporal episode,
                    # not the account's entire history.
                    window_id=last_event.window_id,

                    timestamp=last_event.timestamp,

                    central_account=account,

                    accounts=sorted(all_accounts),

                    transaction_ids=all_tx_ids,

                    pattern_strength=round(
                        float(strength),
                        4,
                    ),

                    evidence={
                        "pass_through_count": len(episode),

                        "distinct_upstream_accounts": len(
                            upstream_accounts
                        ),

                        "distinct_downstream_accounts": len(
                            downstream_accounts
                        ),

                        "mean_hold_time_hours": (
                            sum(hold_times) / len(hold_times)
                            if hold_times
                            else 0.0
                        ),

                        "episode_start": first_event.timestamp,

                        "episode_end": last_event.timestamp,

                        "episode_span_days": (
                            (
                                _parse_timestamp(last_event.timestamp)
                                - _parse_timestamp(first_event.timestamp)
                            ).total_seconds()
                            / 86400.0
                        ),

                        "max_episode_gap_days": MAX_EPISODE_GAP_DAYS,
                    },
                )
            )

    return results


def _parse_timestamp(timestamp):
    """
    Parse PatternEvent timestamps safely.

    Rapid-pass-through events should normally contain real ISO
    timestamps. This helper keeps the detector robust if an
    unexpected synthetic timestamp appears.
    """
    from pandas import Timestamp

    return Timestamp(timestamp)
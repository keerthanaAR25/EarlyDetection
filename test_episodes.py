import json
from datetime import datetime
from collections import defaultdict

with open("results/pattern_events.json") as f:
    events = json.load(f)

STRUCTURAL = {
    "fan_in",
    "fan_out",
    "layering",
    "repeated_intermediary",
}

events = [
    e for e in events
    if e["pattern_type"] in STRUCTURAL
]

def parse_time(x):
    return datetime.fromisoformat(x.replace("Z", "+00:00"))

by_account = defaultdict(list)

for e in events:
    by_account[e["central_account"]].append(e)

episodes = []

MAX_DAYS = 10

for account, account_events in by_account.items():

    account_events.sort(key=lambda e: parse_time(e["timestamp"]))

    current = []
    start_time = None

    for event in account_events:

        event_time = parse_time(event["timestamp"])

        if not current:
            current = [event]
            start_time = event_time
            continue

        span_days = (event_time - start_time).total_seconds() / 86400

        if span_days <= MAX_DAYS:
            current.append(event)

        else:
            episodes.append((account, current))

            current = [event]
            start_time = event_time

    if current:
        episodes.append((account, current))


summary = []

for account, ep in episodes:

    patterns = set(e["pattern_type"] for e in ep)

    summary.append({
        "account": account,
        "events": len(ep),
        "patterns": len(patterns),
        "pattern_types": sorted(patterns),
        "start": ep[0]["timestamp"],
        "end": ep[-1]["timestamp"],
        "duration_days": (
            parse_time(ep[-1]["timestamp"])
            - parse_time(ep[0]["timestamp"])
        ).total_seconds() / 86400,
    })


print()
print("========== BOUNDED EPISODE DIAGNOSTIC ==========")
print("Structural events :", len(events))
print("Central accounts  :", len(by_account))
print("10-day episodes   :", len(summary))

print(
    "Episodes >=2 pattern types:",
    sum(1 for x in summary if x["patterns"] >= 2)
)

print(
    "Episodes >=3 pattern types:",
    sum(1 for x in summary if x["patterns"] >= 3)
)

print()
print("TOP 20 EPISODES BY EVENT COUNT")

for x in sorted(
    summary,
    key=lambda x: x["events"],
    reverse=True
)[:20]:
    print(
        x["account"],
        "| events:", x["events"],
        "| patterns:", x["patterns"],
        "|", x["pattern_types"],
        "| duration:", round(x["duration_days"], 2),
        "days",
        "|", x["start"], "->", x["end"]
    )

print("================================================")
import json
import csv
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

# Known AMLSim alert accounts
alert_accounts = set()

with open("data/raw/amlsim/alert_accounts.csv", newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        alert_accounts.add(str(row["acct_id"]))

# Group structural events by central account
by_account = defaultdict(list)

for e in events:
    by_account[str(e["central_account"])].append(e)

episodes = []

MAX_DAYS = 10

for account, account_events in by_account.items():

    account_events.sort(key=lambda e: parse_time(e["timestamp"]))

    current = []
    start_time = None

    for e in account_events:

        t = parse_time(e["timestamp"])

        if not current:
            current = [e]
            start_time = t
            continue

        span = (t - start_time).total_seconds() / 86400

        if span <= MAX_DAYS:
            current.append(e)
        else:
            episodes.append(current)
            current = [e]
            start_time = t

    if current:
        episodes.append(current)


results = []

for ep in episodes:

    patterns = set(e["pattern_type"] for e in ep)

    if len(patterns) < 2:
        continue

    episode_accounts = set()

    for e in ep:
        episode_accounts.update(str(a) for a in e["accounts"])

    overlap = episode_accounts & alert_accounts

    results.append({
        "patterns": sorted(patterns),
        "events": len(ep),
        "accounts": len(episode_accounts),
        "known_accounts": len(overlap),
        "overlap": sorted(overlap),
        "start": ep[0]["timestamp"],
        "end": ep[-1]["timestamp"],
    })


print()
print("========== GROUP GROUND-TRUTH DIAGNOSTIC ==========")
print("Known AML accounts :", len(alert_accounts))
print("Multi-pattern episodes:", len(results))

print(
    "Episodes with >=1 known AML account:",
    sum(1 for x in results if x["known_accounts"] >= 1)
)

print(
    "Episodes with >=2 known AML accounts:",
    sum(1 for x in results if x["known_accounts"] >= 2)
)

print(
    "Episodes with >=3 known AML accounts:",
    sum(1 for x in results if x["known_accounts"] >= 3)
)

print()
print("TOP EPISODES BY AML ACCOUNT OVERLAP")

for x in sorted(
    results,
    key=lambda x: (x["known_accounts"], x["events"]),
    reverse=True
)[:30]:

    print(
        "known_accounts:", x["known_accounts"],
        "| total_accounts:", x["accounts"],
        "| events:", x["events"],
        "| patterns:", x["patterns"],
        "|", x["start"], "->", x["end"],
        "| overlap:", x["overlap"][:20]
    )

print("====================================================")
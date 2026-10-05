import json
import csv
from collections import defaultdict
from datetime import datetime

with open("results/pattern_events.json") as f:
    events = json.load(f)

# Structural patterns only
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

# Load AMLSim known alert accounts
alert_accounts = set()

with open("data/raw/amlsim/alert_accounts.csv", newline="") as f:
    reader = csv.DictReader(f)

    for row in reader:
        alert_accounts.add(str(row["acct_id"]))

# Group events by central account
by_account = defaultdict(list)

for e in events:
    by_account[str(e["central_account"])].append(e)

results = []

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
            results.append((account, current))
            current = [e]
            start_time = t

    if current:
        results.append((account, current))


multi = []

for account, episode in results:

    patterns = sorted(set(e["pattern_type"] for e in episode))

    if len(patterns) >= 2:

        multi.append({
            "account": account,
            "events": len(episode),
            "patterns": patterns,
            "start": episode[0]["timestamp"],
            "end": episode[-1]["timestamp"],
            "is_known_alert_account": account in alert_accounts,
        })


print()
print("========== GROUND-TRUTH DIAGNOSTIC ==========")
print("Known AMLSim alert accounts :", len(alert_accounts))
print("Multi-pattern episodes      :", len(multi))

known = [
    x for x in multi
    if x["is_known_alert_account"]
]

print("Multi-pattern episodes whose CENTRAL ACCOUNT is known AML:")
print(len(known))

print()
print("DETAILS:")
for x in sorted(multi, key=lambda x: x["events"], reverse=True)[:50]:

    print(
        x["account"],
        "| known:",
        x["is_known_alert_account"],
        "| events:",
        x["events"],
        "| patterns:",
        x["patterns"],
        "|",
        x["start"],
        "->",
        x["end"]
    )

print("==============================================")
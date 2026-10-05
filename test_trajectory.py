import json
from datetime import datetime
from collections import defaultdict, deque

with open("results/pattern_events.json") as f:
    events = json.load(f)

UNION_TYPES = {
    "fan_in",
    "fan_out",
    "layering",
    "repeated_intermediary",
}

events = [
    e for e in events
    if e["pattern_type"] in UNION_TYPES
]

events.sort(key=lambda e: e["timestamp"])


def parse_time(x):
    return datetime.fromisoformat(x.replace("Z", "+00:00"))


by_account = defaultdict(list)

for i, e in enumerate(events):
    for account in set(e["accounts"]):
        by_account[account].append(i)


adj = defaultdict(set)

for i, e in enumerate(events):
    accounts_i = set(e["accounts"])
    time_i = parse_time(e["timestamp"])

    for account in accounts_i:
        for j in by_account[account]:

            if i == j:
                continue

            time_j = parse_time(events[j]["timestamp"])

            # Events must be within 10 days
            if abs((time_i - time_j).total_seconds()) > 10 * 86400:
                continue

            # Require at least TWO common accounts
            shared = len(accounts_i & set(events[j]["accounts"]))

            if shared >= 2:
                adj[i].add(j)


visited = set()
components = []

for i in range(len(events)):

    if i in visited:
        continue

    q = deque([i])
    visited.add(i)
    component = []

    while q:
        x = q.popleft()
        component.append(x)

        for y in adj[x]:

            if y not in visited:
                visited.add(y)
                q.append(y)

    components.append(component)


sizes = sorted(
    [len(c) for c in components],
    reverse=True
)

print()
print("========== STRICT TRAJECTORY DIAGNOSTIC ==========")
print("Union-forming events :", len(events))
print("Number of components :", len(components))
print("Largest component    :", sizes[0] if sizes else 0)
print("Top 20 sizes         :", sizes[:20])
print("==================================================")
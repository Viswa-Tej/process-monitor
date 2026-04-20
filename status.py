#!/usr/bin/env python3
"""Status viewer — prints event history from logs/events.json."""

import json
import sys
from pathlib import Path

events_file = Path("logs/events.json")

if not events_file.exists():
    print("No events log yet. Start monitor.py first.")
    sys.exit(0)

events = json.loads(events_file.read_text())

labels = {
    "STARTED":    "[START  ]",
    "FOUND":      "[FOUND  ]",
    "DIED":       "[DIED   ]",
    "RESTARTED":  "[RESTART]",
    "CRASH_LOOP": "[DANGER ]",
    "STOPPED":    "[STOP   ]",
}

print("\n" + "=" * 62)
print("  PROCESS MONITOR — EVENT HISTORY")
print("=" * 62)
for e in events:
    label = labels.get(e["type"], "[EVENT  ]")
    ts    = e["timestamp"][:19].replace("T", " ")
    print(f"  {ts}  {label}  {e['message']}")

restarts = sum(1 for e in events if e["type"] == "RESTARTED")
deaths   = sum(1 for e in events if e["type"] == "DIED")
print("=" * 62)
print(f"  Total events: {len(events)}  |  Deaths: {deaths}  |  Auto-restarts: {restarts}")
print("=" * 62 + "\n")

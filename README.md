# Process Monitor with Auto-Restart

![SRE](https://img.shields.io/badge/SRE-Week%201%20Day%205-3C3489)
![Python](https://img.shields.io/badge/Python-3.11-0F6E56)
![psutil](https://img.shields.io/badge/psutil-5.9.8-185FA5)

A production-grade process supervisor written in pure Python using `psutil`.
Watches a target process, automatically restarts it on crash, detects crash
loops, logs all events as structured JSON, and rotates log files automatically.

**This is what systemd does — but written from scratch to understand the internals.**

---

## Architecture

```
monitor.py (supervisor)
    │
    ├── find_process()      — scans all PIDs via psutil
    ├── get_process_stats() — CPU, memory, uptime per process
    ├── start_process()     — spawns subprocess.Popen
    ├── RestartTracker      — sliding window crash loop detection
    └── ProcessMonitor      — main event loop + signal handling
         │
         ├── logs/monitor.log      — rotating log (5MB x 3 files)
         ├── logs/events.json      — structured event history
         ├── logs/app_stdout.log   — captured app stdout
         └── logs/app_stderr.log   — captured app stderr
```

## Features

| Feature | How it works |
|---|---|
| Process detection | `psutil.process_iter()` scans all PIDs by name + cmdline |
| Health check loop | Polls every 5 seconds configurable |
| Auto-restart | `subprocess.Popen` relaunches on death |
| Crash loop detection | Sliding window: N restarts in T seconds = stop |
| Structured logging | Every event appended to `logs/events.json` |
| Log rotation | `RotatingFileHandler` — 5MB max, 3 backups |
| Graceful shutdown | `signal.SIGINT` + `SIGTERM` handlers |
| Live status line | `\r` in-place console update every 5s |

## Quick Start

```bash
# Install dependency
pip install psutil

# Run the monitor (Terminal 1)
python monitor.py

# Check event history (Terminal 2)
python status.py

# Watch the log file live (Terminal 2)
tail -f logs/monitor.log
```

## Sample Output

```
2024-04-19 10:00:00 [INFO] Process Monitor starting
2024-04-19 10:00:00 [INFO] Target process : dummy_app
2024-04-19 10:00:00 [INFO] Starting process: python scripts/dummy_app.py
2024-04-19 10:00:00 [INFO] Process started with PID 18432
  [HEALTHY] PID=18432  CPU=0.3%  MEM=14.2MB  Uptime=00:00:12  Restarts=0
2024-04-19 10:00:22 [WARNING] Process 'dummy_app' is NOT running!
2024-04-19 10:00:25 [INFO] Restart #1 complete — PID 19104
  [HEALTHY] PID=19104  CPU=0.2%  MEM=13.9MB  Uptime=00:00:08  Restarts=1
```

## What I Learned

- `psutil.process_iter()` is the right way to find processes cross-platform
- `subprocess.Popen` vs `subprocess.run` — Popen is non-blocking (fire and forget)
- Sliding window algorithm for crash loop detection
- Python `signal` module for graceful shutdown handling
- `RotatingFileHandler` for production log management
- Structured JSON event logging for later analysis

## SRE Concepts Demonstrated

- **Self-healing** — automatic recovery from process failures
- **Crash loop detection** — prevents infinite restart cycles
- **Observability** — structured logs + events for postmortem analysis
- **Graceful shutdown** — clean stop without orphaned child processes

## Tech Stack

Python 3.11 · psutil · subprocess · signal · logging.RotatingFileHandler

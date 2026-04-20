#!/usr/bin/env python3
"""
Process Monitor with Auto-Restart
SRE Week 1 - Day 5 | Author: Viswa Teja Payam
Watches a target process, restarts it if it dies, logs all events.
Like a mini systemd written in pure Python.
"""

import psutil
import subprocess
import logging
import time
import json
import signal
import sys
import os
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler

# ── Configuration ─────────────────────────────────────────────────────────────
CONFIG = {
    "process_name":     "dummy_app",           # name shown in ps / task manager
    "start_command":    ["python", "scripts/dummy_app.py"],  # how to start it
    "check_interval":   5,      # seconds between health checks
    "max_restarts":     5,      # max restarts within restart_window
    "restart_window":   60,     # seconds — if 5 restarts in 60s = crash loop
    "restart_delay":    3,      # seconds to wait before restarting
    "log_file":         "logs/monitor.log",
    "events_file":      "logs/events.json",
    "log_max_bytes":    5 * 1024 * 1024,  # 5 MB
    "log_backup_count": 3,
}

# ── Logging setup ──────────────────────────────────────────────────────────────
Path("logs").mkdir(exist_ok=True)

logger = logging.getLogger("process-monitor")
logger.setLevel(logging.DEBUG)

# File handler — rotating, max 5MB per file, keep 3 files
fh = RotatingFileHandler(
    CONFIG["log_file"],
    maxBytes=CONFIG["log_max_bytes"],
    backupCount=CONFIG["log_backup_count"]
)
fh.setLevel(logging.DEBUG)

# Console handler — coloured output
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)

# Formatters
fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
fh.setFormatter(fmt)
ch.setFormatter(fmt)

logger.addHandler(fh)
logger.addHandler(ch)


# ── Event store ───────────────────────────────────────────────────────────────
def log_event(event_type: str, message: str, extra: dict = None):
    """Append a structured JSON event to events.json for later analysis."""
    event = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "type":      event_type,   # STARTED | DIED | RESTARTED | CRASH_LOOP | STOPPED
        "message":   message,
        "pid":       os.getpid(),
    }
    if extra:
        event.update(extra)

    events_path = Path(CONFIG["events_file"])
    events = []
    if events_path.exists():
        try:
            events = json.loads(events_path.read_text())
        except json.JSONDecodeError:
            events = []
    events.append(event)
    events_path.write_text(json.dumps(events, indent=2))


# ── Process utilities ──────────────────────────────────────────────────────────
def find_process(name: str) -> psutil.Process | None:
    """Find a running process by name. Returns the first match or None."""
    for proc in psutil.process_iter(["pid", "name", "cmdline", "status"]):
        try:
            # Match by process name OR by script name in cmdline
            cmdline = " ".join(proc.info["cmdline"] or [])
            if name in proc.info["name"] or name in cmdline:
                if proc.info["status"] != psutil.STATUS_ZOMBIE:
                    return proc
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return None


def get_process_stats(proc: psutil.Process) -> dict:
    """Get CPU and memory stats for a process."""
    try:
        with proc.oneshot():
            return {
                "pid":         proc.pid,
                "cpu_percent": round(proc.cpu_percent(interval=0.1), 2),
                "mem_mb":      round(proc.memory_info().rss / 1024 / 1024, 2),
                "status":      proc.status(),
                "uptime_s":    round(time.time() - proc.create_time()),
            }
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return {}


def start_process(command: list) -> subprocess.Popen:
    """Start the target process and return the Popen object."""
    logger.info(f"Starting process: {' '.join(command)}")
    proc = subprocess.Popen(
        command,
        stdout=open("logs/app_stdout.log", "a"),
        stderr=open("logs/app_stderr.log", "a"),
    )
    logger.info(f"Process started with PID {proc.pid}")
    return proc


# ── Crash loop detection ───────────────────────────────────────────────────────
class RestartTracker:
    """Tracks restart timestamps to detect crash loops."""

    def __init__(self, max_restarts: int, window_seconds: int):
        self.max_restarts   = max_restarts
        self.window_seconds = window_seconds
        self.restart_times  = []

    def record(self):
        now = time.time()
        self.restart_times.append(now)
        # Only keep restarts within the window
        self.restart_times = [t for t in self.restart_times if now - t <= self.window_seconds]

    def is_crash_loop(self) -> bool:
        return len(self.restart_times) >= self.max_restarts

    def count(self) -> int:
        return len(self.restart_times)


# ── Status printer ─────────────────────────────────────────────────────────────
def print_status(proc: psutil.Process | None, restarts: int):
    """Print a clean status line to console."""
    if proc:
        stats = get_process_stats(proc)
        if stats:
            uptime = stats["uptime_s"]
            m, s   = divmod(uptime, 60)
            h, m   = divmod(m, 60)
            print(
                f"\r  [HEALTHY] PID={stats['pid']}  "
                f"CPU={stats['cpu_percent']}%  "
                f"MEM={stats['mem_mb']}MB  "
                f"Uptime={h:02d}:{m:02d}:{s:02d}  "
                f"Restarts={restarts}    ",
                end="", flush=True
            )
    else:
        print(f"\r  [DOWN] Waiting to restart... Restarts so far={restarts}    ",
              end="", flush=True)


# ── Main monitor loop ──────────────────────────────────────────────────────────
class ProcessMonitor:

    def __init__(self, config: dict):
        self.config   = config
        self.running  = True
        self.child    = None     # subprocess.Popen
        self.tracker  = RestartTracker(
            config["max_restarts"],
            config["restart_window"]
        )
        self.total_restarts = 0

        # Graceful shutdown on Ctrl+C or SIGTERM
        signal.signal(signal.SIGINT,  self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

    def _handle_shutdown(self, signum, frame):
        logger.info("\nShutdown signal received. Stopping monitor...")
        self.running = False
        if self.child and self.child.poll() is None:
            logger.info(f"Terminating child process PID {self.child.pid}")
            self.child.terminate()
        log_event("STOPPED", "Monitor shut down by operator")
        sys.exit(0)

    def run(self):
        logger.info("=" * 60)
        logger.info(f"Process Monitor starting")
        logger.info(f"Target process : {self.config['process_name']}")
        logger.info(f"Check interval : {self.config['check_interval']}s")
        logger.info(f"Max restarts   : {self.config['max_restarts']} per {self.config['restart_window']}s")
        logger.info("=" * 60)

        # Check if process is already running
        existing = find_process(self.config["process_name"])
        if existing:
            logger.info(f"Found existing process PID {existing.pid}. Monitoring it.")
            log_event("FOUND", f"Attached to existing PID {existing.pid}")
        else:
            logger.info("Process not running. Starting it now.")
            self.child = start_process(self.config["start_command"])
            log_event("STARTED", f"Initial start PID {self.child.pid}")
            time.sleep(2)  # Give it a moment to initialise

        while self.running:
            proc = find_process(self.config["process_name"])

            if proc:
                # Process is healthy — print status
                print_status(proc, self.total_restarts)
                logger.debug(f"Health check OK — PID {proc.pid} — {get_process_stats(proc)}")
            else:
                # Process died — handle restart
                print()  # newline after the status line
                logger.warning(f"Process '{self.config['process_name']}' is NOT running!")
                log_event("DIED", f"Process {self.config['process_name']} disappeared")

                # Crash loop check
                self.tracker.record()
                if self.tracker.is_crash_loop():
                    logger.error(
                        f"CRASH LOOP DETECTED: {self.tracker.count()} restarts "
                        f"in {self.config['restart_window']}s. Stopping monitor."
                    )
                    log_event(
                        "CRASH_LOOP",
                        f"Crash loop: {self.tracker.count()} restarts in {self.config['restart_window']}s. Manual intervention required."
                    )
                    self.running = False
                    break

                # Restart
                logger.info(f"Waiting {self.config['restart_delay']}s before restart...")
                time.sleep(self.config["restart_delay"])

                self.child = start_process(self.config["start_command"])
                self.total_restarts += 1
                log_event(
                    "RESTARTED",
                    f"Restart #{self.total_restarts} — new PID {self.child.pid}",
                    {"total_restarts": self.total_restarts}
                )
                logger.info(f"Restart #{self.total_restarts} complete — PID {self.child.pid}")
                time.sleep(2)  # Let it settle

            time.sleep(self.config["check_interval"])

        logger.info("Monitor stopped.")


if __name__ == "__main__":
    monitor = ProcessMonitor(CONFIG)
    monitor.run()

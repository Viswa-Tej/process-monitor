#!/usr/bin/env python3
"""
Dummy App — the process being monitored.
Simulates a real service: starts, runs, then randomly crashes.
"""

import time
import random
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("dummy-app")

logger.info("Dummy app starting up...")
time.sleep(1)
logger.info("Dummy app initialised. Running...")

run_duration = random.randint(10, 25)
logger.info(f"Will run for ~{run_duration}s then simulate a crash")

for i in range(run_duration):
    logger.info(f"Tick {i+1}/{run_duration} — app is healthy")
    time.sleep(1)

logger.error("Simulated crash! Exiting with code 1.")
sys.exit(1)

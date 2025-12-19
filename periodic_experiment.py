#!/usr/bin/env python3
import csv
import time
from datetime import datetime

import matplotlib.pyplot as plt
import requests

# ===================== CONFIG =====================

# Knative service info
SERVICE = "py-light"  # change to py-heavy / node-light / etc as needed
HOST = f"{SERVICE}.default.127.0.0.1.sslip.io"
GATEWAY = "http://127.0.0.1:8080"  # Kourier port-forward

URL = f"{GATEWAY}/"
HEADERS = {"Host": HOST}

# Experiment parameters
NUM_REQUESTS = 20
INTERVAL_SECONDS = 90  # time between requests
REQUEST_TIMEOUT_SECONDS = 30

# Cold-start threshold (in ms) for plotting/labeling
COLD_THRESHOLD_MS = 500

# Output files
CSV_PATH = "periodic_results.csv"
PLOT_PATH = "periodic_latency.png"

# ==================================================


def run_experiment():
    print(f"Running periodic experiment against {URL} with Host={HOST}")
    print(f"{NUM_REQUESTS} requests, interval {INTERVAL_SECONDS}s\n")

    records = []

    for i in range(1, NUM_REQUESTS + 1):
        ts = datetime.now().isoformat(timespec="seconds")
        print(f"Request {i}/{NUM_REQUESTS} at {ts}")

        start = time.perf_counter()
        try:
            resp = requests.get(URL, headers=HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
            ok = resp.status_code
        except Exception as e:
            ok = f"ERROR: {e}"
        end = time.perf_counter()

        latency_ms = (end - start) * 1000.0
        print(f"  Latency: {latency_ms:.1f} ms, status={ok}")

        records.append({
            "request_index": i,
            "timestamp": ts,
            "latency_ms": latency_ms,
            "status": ok,
        })

        if i < NUM_REQUESTS:
            time.sleep(INTERVAL_SECONDS)

    return records


def save_csv(records, path):
    fieldnames = ["request_index", "timestamp", "latency_ms", "status"]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    print(f"\nSaved CSV: {path}")


def summarize(records):
    latencies = [r["latency_ms"] for r in records if isinstance(r["status"], int) and r["status"] == 200]
    if not latencies:
        print("No successful requests to summarize.")
        return

    import statistics

    print("\n=== Summary (successful requests only) ===")
    print(f"Total successful: {len(latencies)}")
    print(f"Mean latency: {statistics.mean(latencies):.1f} ms")
    print(f"Median (p50): {statistics.median(latencies):.1f} ms")

    # percentiles without numpy
    qs = statistics.quantiles(latencies, n=100)
    print(f"p90: {qs[89]:.1f} ms")
    print(f"p99: {qs[98]:.1f} ms")

    cold = [x for x in latencies if x > COLD_THRESHOLD_MS]
    warm = [x for x in latencies if x <= COLD_THRESHOLD_MS]

    print(f"Cold starts (> {COLD_THRESHOLD_MS} ms): {len(cold)}")
    if warm:
        print(f"Warm avg: {statistics.mean(warm):.1f} ms")
    if cold:
        print(f"Cold avg: {statistics.mean(cold):.1f} ms")


def plot(records, path):
    req_idx = [r["request_index"] for r in records]
    latencies = [r["latency_ms"] for r in records]

    plt.figure(figsize=(10, 5))
    plt.plot(req_idx, latencies, marker="o", label="Latency (ms)")

    # highlight cold starts
    cold_x = [req_idx[i] for i in range(len(latencies)) if latencies[i] > COLD_THRESHOLD_MS]
    cold_y = [latencies[i] for i in range(len(latencies)) if latencies[i] > COLD_THRESHOLD_MS]
    if cold_x:
        plt.scatter(cold_x, cold_y, label="Cold start", zorder=5)

    plt.axhline(COLD_THRESHOLD_MS, linestyle="--", label="Cold threshold")

    plt.xlabel("Request number")
    plt.ylabel("Latency (ms)")
    plt.title(f"Periodic low-traffic latency over time ({SERVICE})")
    plt.legend()
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    print(f"Saved plot: {path}")


def main():
    records = run_experiment()
    save_csv(records, CSV_PATH)
    summarize(records)
    plot(records, PLOT_PATH)


if __name__ == "__main__":
    main()


#!/usr/bin/env python3
import csv
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime

import matplotlib.pyplot as plt
import requests


# ---------------- CONFIG ----------------
GATEWAY = "http://127.0.0.1:8080"
NAMESPACE = "default"

# Hey parameters
BURST_N = 200
BURST_C = 10

SUSTAINED_N = 3000
SUSTAINED_C = 50

COLD_WINDOW = 5          # first N requests treated as cold window in burst
COLD_THRESHOLD_MS = 500  # for classifying cold starts in periodic tests

REQUEST_TIMEOUT_SECONDS = 60  # allow slow cold starts
# ----------------------------------------


LATENCY_CANDIDATES = ["latency", "response-time", "response_time", "request_time", "req_time"]


def sh(cmd: list[str], check=True, capture=False) -> str:
    if capture:
        return subprocess.check_output(cmd, text=True).strip()
    subprocess.run(cmd, check=check)
    return ""


def kn_update_min_scale(service: str, min_scale: int):
    sh(["kn", "service", "update", service, "--annotation", f"autoscaling.knative.dev/minScale={min_scale}"])


def kn_update_max_scale(service: str, max_scale: int):
    sh(["kn", "service", "update", service, "--annotation", f"autoscaling.knative.dev/maxScale={max_scale}"])


def delete_service_pods(service: str):
    # Ignore errors if no pods
    subprocess.run(
        ["kubectl", "delete", "pod", "-n", NAMESPACE, "-l", f"serving.knative.dev/service={service}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def hey_to_csv(service: str, out_csv: str, n: int, c: int):
    host = f"{service}.{NAMESPACE}.127.0.0.1.sslip.io"
    cmd = [
        "hey", "-n", str(n), "-c", str(c),
        "-H", f"Host: {host}",
        "-o", "csv",
        f"{GATEWAY}/"
    ]
    with open(out_csv, "w") as f:
        subprocess.run(cmd, check=True, stdout=f)


def find_latency_column(headers):
    for cand in LATENCY_CANDIDATES:
        if cand in headers:
            return cand
    raise RuntimeError(f"No latency column found. Headers={headers}")


def parse_latency_ms(value: str) -> float:
    v = value.strip().lower()
    if v.endswith("s"):
        return float(v[:-1]) * 1000.0
    return float(v) * 1000.0


def load_hey_latencies(csv_path: str) -> list[float]:
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise RuntimeError(f"Empty CSV headers: {csv_path}")
        col = find_latency_column(reader.fieldnames)
        data = []
        for row in reader:
            data.append(parse_latency_ms(row[col]))
    return data


def percentile(sorted_data: list[float], p: float) -> float:
    if not sorted_data:
        return float("nan")
    k = (len(sorted_data) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_data) - 1)
    if f == c:
        return sorted_data[f]
    return sorted_data[f] + (sorted_data[c] - sorted_data[f]) * (k - f)


def summarize_latencies(lat_ms: list[float]) -> dict:
    s = sorted(lat_ms)
    return {
        "p50": percentile(s, 50),
        "p90": percentile(s, 90),
        "p95": percentile(s, 95),
        "p99": percentile(s, 99),
        "mean": sum(lat_ms) / len(lat_ms),
    }


# ---------- Experiment A: sustained load ----------
def experiment_sustained(service: str, tag: str):
    csv_out = f"sustained_{service}_{tag}.csv"
    hey_to_csv(service, csv_out, SUSTAINED_N, SUSTAINED_C)
    lat = load_hey_latencies(csv_out)
    stats = summarize_latencies(lat)
    # Rough RPS estimate from hey: N / total_time not directly in CSV; approximate using mean latency + concurrency is not accurate.
    # We’ll plot tail latency and compare distributions instead.
    return csv_out, stats, lat


def plot_latency_cdf(lat_sets: dict, out_png: str, title: str):
    plt.figure(figsize=(9, 5))
    for label, lat in lat_sets.items():
        s = sorted(lat)
        y = [(i + 1) / len(s) for i in range(len(s))]
        plt.plot(s, y, label=label)
    plt.xlabel("Latency (ms)")
    plt.ylabel("CDF")
    plt.title(title)
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_png, dpi=150)
    print(f"Saved: {out_png}")


def plot_tail_bars(stats_map: dict, out_png: str, title: str):
    labels = list(stats_map.keys())
    p50 = [stats_map[k]["p50"] for k in labels]
    p95 = [stats_map[k]["p95"] for k in labels]
    p99 = [stats_map[k]["p99"] for k in labels]

    x = list(range(len(labels)))
    w = 0.25

    plt.figure(figsize=(9, 5))
    plt.bar([i - w for i in x], p50, width=w, label="p50")
    plt.bar(x, p95, width=w, label="p95")
    plt.bar([i + w for i in x], p99, width=w, label="p99")

    plt.xticks(x, labels, rotation=15)
    plt.ylabel("Latency (ms)")
    plt.title(title)
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_png, dpi=150)
    print(f"Saved: {out_png}")


# ---------- Experiment B: idle interval sweep ----------
def periodic_run(service: str, interval_s: int, num_requests: int = 12) -> list[float]:
    host = f"{service}.{NAMESPACE}.127.0.0.1.sslip.io"
    latencies = []

    for i in range(1, num_requests + 1):
        start = time.perf_counter()
        try:
            requests.get(GATEWAY + "/", headers={"Host": host}, timeout=REQUEST_TIMEOUT_SECONDS)
        except Exception:
            # treat failure as timeout duration
            pass
        end = time.perf_counter()
        latencies.append((end - start) * 1000.0)
        if i < num_requests:
            time.sleep(interval_s)

    return latencies


def experiment_idle_sweep(service: str, intervals=(10, 30, 60, 120)):
    results = {}
    for interval in intervals:
        # ensure scale-to-zero enabled
        kn_update_min_scale(service, 0)
        # force cold start initially
        delete_service_pods(service)
        time.sleep(2)

        lat = periodic_run(service, interval_s=interval, num_requests=12)
        results[interval] = lat

    return results


def plot_idle_sweep(results: dict, out_png: str, title: str):
    # Compute cold-start frequency and mean latency by interval
    intervals = sorted(results.keys())
    cold_pct = []
    mean_lat = []
    for interval in intervals:
        lat = results[interval]
        cold = sum(1 for x in lat if x > COLD_THRESHOLD_MS)
        cold_pct.append(100.0 * cold / len(lat))
        mean_lat.append(sum(lat) / len(lat))

    plt.figure(figsize=(9, 5))
    plt.plot(intervals, cold_pct, marker="o", label="Cold-start frequency (%)")
    plt.xlabel("Inter-request interval (seconds)")
    plt.ylabel("Cold-start frequency (%)")
    plt.title(title + " (frequency)")
    plt.tight_layout()
    plt.savefig(out_png.replace(".png", "_freq.png"), dpi=150)
    print(f"Saved: {out_png.replace('.png','_freq.png')}")

    plt.figure(figsize=(9, 5))
    plt.plot(intervals, mean_lat, marker="o", label="Mean latency (ms)")
    plt.xlabel("Inter-request interval (seconds)")
    plt.ylabel("Mean latency (ms)")
    plt.title(title + " (mean latency)")
    plt.tight_layout()
    plt.savefig(out_png.replace(".png", "_mean.png"), dpi=150)
    print(f"Saved: {out_png.replace('.png','_mean.png')}")


# ---------- Experiment C: mitigation comparison ----------
def run_burst(service: str, tag: str) -> tuple[str, dict, list[float]]:
    out_csv = f"burst_{service}_{tag}.csv"
    hey_to_csv(service, out_csv, BURST_N, BURST_C)
    lat = load_hey_latencies(out_csv)
    stats = summarize_latencies(lat)
    return out_csv, stats, lat


def experiment_mitigations(service: str):
    stats_map = {}
    lat_sets = {}

    # 1) scale-to-zero baseline
    kn_update_min_scale(service, 0)
    delete_service_pods(service)
    time.sleep(2)
    _, st, lat = run_burst(service, "scale0")
    stats_map["scale0"] = st
    lat_sets["scale0"] = lat

    # 2) pre-warm
    kn_update_min_scale(service, 1)
    time.sleep(3)
    _, st, lat = run_burst(service, "min1")
    stats_map["minScale=1"] = st
    lat_sets["minScale=1"] = lat

    # 3) predictive (simulate): warm briefly before burst then allow scale-to-zero
    kn_update_min_scale(service, 1)
    time.sleep(3)
    kn_update_min_scale(service, 0)
    # burst happens while pod still warm
    _, st, lat = run_burst(service, "predictive")
    stats_map["predictive"] = st
    lat_sets["predictive"] = lat

    return stats_map, lat_sets


def main():
    service = os.environ.get("SERVICE", "py-light")

    # EXP 3: sustained warm vs scale-to-zero
    print("\n=== Experiment: Sustained load (warm vs scale-to-zero) ===")
    kn_update_min_scale(service, 1)
    _, warm_stats, warm_lat = experiment_sustained(service, "warm")

    kn_update_min_scale(service, 0)
    delete_service_pods(service)
    time.sleep(2)
    _, cold_stats, cold_lat = experiment_sustained(service, "scale0")

    plot_latency_cdf(
        {"warm(minScale=1)": warm_lat, "scale-to-zero": cold_lat},
        f"sustained_cdf_{service}.png",
        f"Sustained load latency CDF ({service})"
    )
    plot_tail_bars(
        {"warm(minScale=1)": warm_stats, "scale-to-zero": cold_stats},
        f"sustained_tail_{service}.png",
        f"Sustained load tail latency ({service})"
    )

    # EXP 4: idle interval sweep
    print("\n=== Experiment: Idle interval sweep (cold-start frequency) ===")
    sweep = experiment_idle_sweep(service, intervals=(10, 30, 60, 120))
    plot_idle_sweep(sweep, f"idle_sweep_{service}.png", f"Idle sweep ({service})")

    # EXP 5: mitigation comparison (burst)
    print("\n=== Experiment: Mitigation comparison (burst after idle) ===")
    stats_map, lat_sets = experiment_mitigations(service)
    plot_tail_bars(stats_map, f"mitigation_tail_{service}.png", f"Mitigation comparison ({service})")
    plot_latency_cdf(lat_sets, f"mitigation_cdf_{service}.png", f"Mitigation CDF ({service})")


if __name__ == "__main__":
    main()


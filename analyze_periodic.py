#!/usr/bin/env python3
import re
import statistics
import sys
import matplotlib.pyplot as plt

# Threshold for marking cold starts (ms)
COLD_THRESHOLD_MS = 500

# Matches formats like:
#   real 0m0.623s
#   real    0m1.302s
#   real 1.23s
#   0m0.923s
#   1.23s
#   0.932
LATENCY_REGEX = re.compile(
    r"(?:real\s*)?(?:(\d+)m)?\s*([0-9]*\.?[0-9]+)s?"
)

REQ_NUM_REGEX = re.compile(r"Request\s+(\d+)")


def parse_periodic_log(path):
    req_nums = []
    latencies = []

    current_req = None

    with open(path, "r") as f:
        for line in f:
            # Look for "Request N"
            m = REQ_NUM_REGEX.search(line)
            if m:
                current_req = int(m.group(1))
                continue

            # Try to parse latency from time output
            m = LATENCY_REGEX.search(line)
            if m and current_req is not None:
                minutes = m.group(1)
                seconds = float(m.group(2))

                total_seconds = seconds
                if minutes:
                    total_seconds += int(minutes) * 60.0

                ms = total_seconds * 1000
                req_nums.append(current_req)
                latencies.append(ms)

                # Clear for next block
                current_req = None

    return req_nums, latencies


def summarize(latencies):
    print("\n=== Summary ===")
    print(f"Total requests: {len(latencies)}")
    print(f"Mean latency: {statistics.mean(latencies):.1f} ms")
    print(f"Median: {statistics.median(latencies):.1f} ms")
    print(f"p90: {statistics.quantiles(latencies, n=100)[89]:.1f} ms")
    print(f"p99: {statistics.quantiles(latencies, n=100)[98]:.1f} ms")

    cold = [x for x in latencies if x > COLD_THRESHOLD_MS]
    warm = [x for x in latencies if x <= COLD_THRESHOLD_MS]

    print(f"Cold starts (> {COLD_THRESHOLD_MS} ms): {len(cold)}")
    if warm:
        print(f"Warm avg: {statistics.mean(warm):.1f} ms")
    if cold:
        print(f"Cold avg: {statistics.mean(cold):.1f} ms")


def plot(req_nums, latencies):
    plt.figure(figsize=(10, 5))
    plt.plot(req_nums, latencies, marker="o", label="Latency (ms)")

    cold_x = [req_nums[i] for i in range(len(latencies)) if latencies[i] > COLD_THRESHOLD_MS]
    cold_y = [latencies[i] for i in range(len(latencies)) if latencies[i] > COLD_THRESHOLD_MS]
    plt.scatter(cold_x, cold_y, color="red", label="Cold Start", zorder=5)

    plt.axhline(COLD_THRESHOLD_MS, linestyle="--", color="gray", label="Cold Threshold")

    plt.xlabel("Request Number")
    plt.ylabel("Latency (ms)")
    plt.title("Periodic Low-Traffic Latency Over Time")
    plt.legend()
    plt.tight_layout()
    plt.savefig("periodic_latency.png", dpi=150)
    print("\nSaved plot: periodic_latency.png")


def main():
    if len(sys.argv) != 2:
        print("Usage: python analyze_periodic.py periodic.log")
        sys.exit(1)

    req_nums, latencies = parse_periodic_log(sys.argv[1])

    if not latencies:
        print("ERROR: No latency entries parsed. Check log format.")
        sys.exit(1)

    summarize(latencies)
    plot(req_nums, latencies)


if __name__ == "__main__":
    main()


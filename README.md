# Zero-Scaling Penalties in Serverless Computing (Knative + Kubernetes)

This repository contains a reproducible artifact for a project studying **zero-scaling (scale-to-zero) penalties** in serverless environments. Using **Knative Serving** on a local **Kubernetes (kind)** cluster, we measure the impact of cold starts on **latency distributions**, **tail latency (p95/p99)**, and **cold-start frequency** under different traffic patterns. We also evaluate mitigation strategies including **pre-warming (minScale=1)** and a simple **predictive scaling** approach.

## What this artifact includes

- A local serverless environment based on:
  - Kubernetes in Docker (kind)
  - Knative Serving + Kourier ingress
  - Local container images loaded into kind (no external registry required)
- A lightweight test service (`py-light`) used to isolate platform overheads
- Python scripts that run experiments and generate **matplotlib** plots:
  - Sustained load comparison: warm vs scale-to-zero (CDF + tail bars)
  - Idle interval sweep: cold-start frequency vs inter-request gap
  - Mitigation comparison: baseline vs pre-warm vs predictive (CDF + tail bars)
- Output plots saved as `.png` files (slide/report ready)

---

## Dependencies

### System / CLI tools (WSL Ubuntu recommended)
- Docker Desktop (Windows) with WSL integration enabled
- WSL2 Ubuntu (22.04+)
- `kubectl`
- `kind`
- `kn` (Knative client)
- `hey` (load generator)
- `curl`

### Python
- Python 3.10+ (3.12 works)
- `python3-venv`

Python packages (installed via venv):
- `matplotlib`
- `requests`

---

## Environment setup (Windows + WSL2)

### 1) Verify Docker works inside WSL
```bash
docker version
docker ps

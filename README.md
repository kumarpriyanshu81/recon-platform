# recon-platform

![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20Docker-lightgrey)
![License](https://img.shields.io/badge/License-MIT-22c55e)
![Status](https://img.shields.io/badge/Status-Active-22c55e)
![Dependencies](https://img.shields.io/badge/Python%20deps-zero%20(stdlib%20only)-blue)
![Tests](https://img.shields.io/badge/Tests-pytest-orange)

A modular, extensible reconnaissance orchestration framework for structured and repeatable external attack surface mapping.

---

## Overview

recon-platform is an internal-style security engineering tool that orchestrates industry-standard recon tooling behind a clean Python pipeline. It produces consistent, structured output on every run and is designed to be extended privately — proprietary detection logic and methodology stay completely out of the public repository.

This is not a collection of scripts. It is a pipeline framework with a defined data model, an event-driven plugin system, and deliberate separation between public infrastructure and private research.

---

## Why recon-platform Exists

Ad-hoc recon has a structural problem: tool invocations are manual, output formats differ between tools, findings are saved inconsistently, and nothing is reproducible across targets or over time.

recon-platform addresses this by:

- Standardising how tools are invoked and how their output is parsed
- Producing identical output structure for every target, every run
- Assigning priority scores to findings so manual review is focused
- Allowing private extensions without touching or exposing public code
- Saving scan state so enumeration is never repeated unnecessarily

---

## Key Capabilities

| Capability | Detail |
|---|---|
| Subdomain enumeration | subfinder with configurable threads and timeout |
| HTTP probing | httpx-toolkit with title, status code, and tech detection |
| Chunked processing | Large host lists probed in configurable batches |
| Retry pass | Non-responding hosts re-probed with extended timeout |
| Deduplication | URL-level dedup across chunks and retry passes |
| Priority scoring | HIGH / MEDIUM / LOW assigned to each finding |
| Auto-categorisation | Login pages, admin panels, API endpoints, staging envs, dashboards |
| Resumable scans | Subdomain state saved after enumeration; `--resume` skips re-running |
| Structured output | JSON report with full metadata + categorised text files |
| Plugin system | Hook-based extensions at every pipeline stage boundary |
| Public/private separation | Private plugins and docs are git-ignored by design |
| Zero Python deps | Core framework requires only the standard library |
| Env-var configuration | Every default is overridable without touching source code |
| Docker support | Single-command containerised execution |

---

## Architecture

```
recon-platform/
│
├── main.py                    CLI entry point + pipeline orchestrator
│
├── core/
│   ├── subdomains.py          SubdomainEnumerator  — wraps subfinder
│   ├── probe.py               HTTPProber + HostResult — wraps httpx-toolkit
│   ├── filters.py             ResultFilter — categorisation + scoring
│   ├── output.py              OutputWriter — all result files + JSON report
│   ├── utils.py               subprocess wrapper, path helpers, dedup
│   └── logger.py              Centralised logging configuration
│
├── plugins/
│   ├── loader.py              PluginRegistry + PluginLoader
│   └── sample_plugin.py       Reference plugin showing all hook points
│
├── private_modules/           [git-ignored] drop proprietary plugins here
│
├── config/
│   └── settings.py            All tunables — env-var overridable
│
├── tests/
│   ├── test_utils.py
│   ├── test_probe.py
│   ├── test_filters.py
│   └── test_state.py
│
├── docs/
│   └── PRIVATE_NOTES.md       [git-ignored] internal methodology notes
│
└── output/                    [git-ignored] scan results written here
```

### Pipeline

```
CLI args
   |
   v
[ENUM]   SubdomainEnumerator (subfinder)
            -> subdomains: list[str]
            -> state saved: output/.state_<domain>.json
   |
[PROBE]  HTTPProber (httpx-toolkit)
            -> chunked processing (configurable batch size)
            -> retry pass for non-responding hosts
            -> URL-level deduplication
            -> results: list[HostResult]
   |
[FILTER] ResultFilter
            -> flags: is_login / is_admin / is_api / is_staging / is_dashboard
            -> score: HIGH / MEDIUM / LOW
   |
[OUTPUT] OutputWriter
            -> subdomains.txt, live_hosts.txt, login_pages.txt,
               api_endpoints.txt, interesting.txt, results.json
   |
Plugin hooks fire at each stage boundary
```

---

## Installation

### 1. Clone

```bash
git clone https://github.com/your-username/recon-platform.git
cd recon-platform
```

### 2. Install external tools

```bash
# Standard (Go install)
go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest
go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest

# Kali Linux (pre-packaged)
sudo apt install subfinder httpx-toolkit
```

The framework auto-detects `httpx-toolkit` vs `httpx` — no configuration needed.

### 3. Python environment (optional)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # only installs pytest for testing
```

---

## Usage

### Full scan

```bash
python main.py -d example.com
```

### Resume after interruption

```bash
# Subfinder state is saved automatically.
# --resume skips re-enumeration and reloads saved subdomains.
python main.py -d example.com --resume
```

### Load subdomains from a file

```bash
python main.py -d example.com --subdomains-file ./subs.txt
```

### Custom output directory

```bash
python main.py -d example.com --output-dir ./runs/2024-05-01
```

### Tune probing performance

```bash
python main.py -d example.com --chunk-size 250 --httpx-args "-t 100 -rl 300"
```

### Enumeration only (no probing)

```bash
python main.py -d example.com --skip-probe
```

### Verbose / debug output

```bash
python main.py -d example.com -v
```

### Docker

```bash
# Build
docker build -t recon-platform .

# Run
docker run --rm -v $(pwd)/output:/app/output recon-platform -d example.com

# With overrides
docker run --rm \
  -e HTTPX_THREADS=100 \
  -e SUBFINDER_TIMEOUT=180 \
  -v $(pwd)/output:/app/output \
  recon-platform -d example.com
```

### All options

```
usage: recon-platform [-h] -d DOMAIN [--output-dir DIR] [--resume]
                      [--skip-enum] [--subdomains-file FILE] [--skip-probe]
                      [--no-plugins] [--chunk-size N]
                      [--subfinder-args ARGS] [--httpx-args ARGS] [-v]
```

---

## Console Output

```
  +-------------------------------------------------+
  |   R E C O N - P L A T F O R M                  |
  |   Reconnaissance Orchestration Framework        |
  +-------------------------------------------------+

2024-05-15 10:14:03 [INFO ] plugins.loader: Plugins: 1 public, 0 private loaded.
2024-05-15 10:14:03 [INFO ] core.subdomains: [ENUM] Running subfinder against example.com ...
2024-05-15 10:15:01 [INFO ] core.subdomains: [ENUM] Found 1842 unique subdomains.
2024-05-15 10:15:01 [INFO ] core.probe: [PROBE] 1842 hosts | 4 chunk(s) | chunk=500 threads=50 rate=150/s timeout=10s
2024-05-15 10:15:01 [INFO ] core.probe: [PROBE] Chunk 1/4 — 500 hosts ...
2024-05-15 10:17:34 [INFO ] core.probe: [PROBE] Chunk 1/4 done — 118/500 responded.
...
2024-05-15 10:24:11 [INFO ] core.filters: [FILTER] Categorised 47/283 hosts — HIGH=8 MEDIUM=31 LOW=8
2024-05-15 10:24:11 [INFO ] core.output: [OUTPUT] results.json          283 entries

--------------------------------------------------------------
  SCAN COMPLETE  example.com
--------------------------------------------------------------
  Duration              : 10m 8s
  Subdomains discovered : 1842
  Live hosts            : 283  (15.4% live rate)
  Interesting findings  : 47
    HIGH                : 8
    MEDIUM              : 31
    LOW                 : 8
--------------------------------------------------------------
  Output files:
    subdomains         -> output/subdomains.txt
    live_hosts         -> output/live_hosts.txt
    login_pages        -> output/login_pages.txt
    api_endpoints      -> output/api_endpoints.txt
    interesting        -> output/interesting.txt
    results_json       -> output/results.json
--------------------------------------------------------------
```

---

## Output Reference

| File | Contents |
|---|---|
| `subdomains.txt` | All discovered subdomains |
| `live_hosts.txt` | URLs of hosts that responded to HTTP |
| `login_pages.txt` | Hosts matching login / auth patterns |
| `api_endpoints.txt` | Hosts matching API path patterns |
| `interesting.txt` | Union of all scored findings, sorted by priority |
| `results.json` | Canonical structured report (see schema below) |

### results.json schema

```json
{
  "meta": {
    "domain": "example.com",
    "scanned_at": "2024-05-15T10:24:11+00:00",
    "duration_seconds": 608.2,
    "stats": {
      "total_subdomains": 1842,
      "total_live": 283,
      "live_rate_pct": 15.4,
      "interesting_total": 47,
      "score_breakdown": { "HIGH": 8, "MEDIUM": 31, "LOW": 8 },
      "categories": {
        "login_pages": 14, "admin_panels": 8,
        "api_endpoints": 31, "staging_envs": 6, "dashboards": 2
      },
      "status_distribution": { "200": 201, "301": 44, "403": 38 },
      "top_technologies": { "nginx": 98, "React": 41, "Cloudflare": 38 }
    }
  },
  "subdomains": ["..."],
  "live_hosts": [
    {
      "url": "https://api.example.com",
      "host": "api.example.com",
      "status_code": 200,
      "title": "Example API",
      "tech": ["nginx", "React"],
      "score": "MEDIUM",
      "flags": {
        "login": false, "admin": false,
        "api": true, "staging": false, "dashboard": false
      }
    }
  ],
  "categories": {
    "login_pages": ["..."], "admin_panels": ["..."],
    "api_endpoints": ["..."], "staging_envs": ["..."], "dashboards": ["..."]
  }
}
```

---

## Priority Scoring

Every interesting finding is assigned a score by the `ResultFilter`:

| Score | Conditions |
|---|---|
| `HIGH` | Admin panel detected — OR — login portal with an interesting technology |
| `MEDIUM` | Login portal — OR — API endpoint |
| `LOW` | Staging / dev environment — OR — dashboard / monitoring surface |
| *(none)* | Live host, no category matched |

`interesting.txt` is sorted `HIGH -> MEDIUM -> LOW` for efficient manual triage.

The scoring logic is intentionally simple and fully overridable — private plugins can re-score results via the `post_filter` hook.

---

## Plugin System

### How it works

The framework fires events at each pipeline stage boundary. Plugins register Python functions against these events via a `PluginRegistry`. Exceptions in individual plugins are caught and logged — one failing plugin never aborts the pipeline.

### Hook events

| Event | Signature | When |
|---|---|---|
| `pre_enum` | `(domain: str)` | Before subfinder runs |
| `post_enum` | `(domain: str, subdomains: list[str])` | After enumeration |
| `pre_probe` | `(hosts: list[str])` | Before httpx runs |
| `post_probe` | `(results: list[HostResult])` | After probing |
| `post_filter` | `(results: list[HostResult])` | After scoring |
| `post_output` | `(written_paths: dict[str, Path])` | After all files written |

### Writing a plugin

```python
# plugins/my_plugin.py
from plugins.loader import PluginRegistry

def register(registry: PluginRegistry) -> None:
    registry.on("post_filter", _on_post_filter)

def _on_post_filter(results):
    for r in results:
        if r.score == "HIGH":
            print(f"[!] High priority: {r.url}  [{r.title}]")
```

---

## Public vs Private Plugin Model

| Location | Version controlled | Purpose |
|---|---|---|
| `plugins/` | Yes | Generic, shareable extensions |
| `private_modules/` | **No** (git-ignored) | Proprietary detection, internal workflows |
| `docs/PRIVATE_NOTES.md` | **No** (git-ignored) | Internal methodology notes |

Drop a `.py` file into `private_modules/` and it loads automatically on the next run. No configuration required.

The public repository demonstrates engineering architecture. Detection heuristics, scoring refinements, and operational methodology belong in `private_modules/`.

---

## Configuration

All defaults are in `config/settings.py`. Every value is overridable via environment variable — no code changes needed between environments.

| Variable | Default | Description |
|---|---|---|
| `SUBFINDER_BIN` | `subfinder` | subfinder binary name or path |
| `HTTPX_BIN` | auto-detected | `httpx-toolkit` (Kali) or `httpx` |
| `SUBFINDER_TIMEOUT` | `120` | subfinder wall-clock timeout (seconds) |
| `SUBFINDER_THREADS` | `10` | subfinder concurrent threads |
| `HTTPX_TIMEOUT` | `10` | httpx per-request timeout (seconds) |
| `HTTPX_THREADS` | `50` | httpx concurrent threads |
| `HTTPX_RATE_LIMIT` | `150` | httpx requests per second |
| `HTTPX_CHUNK_SIZE` | `500` | hosts per subprocess batch |
| `HTTPX_MAX_RETRIES` | `1` | retry passes for non-responding hosts |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` |

---

## Testing

```bash
pip install pytest
pytest tests/ -v
```

Test coverage:
- `test_utils.py` — domain sanitisation, deduplication
- `test_probe.py` — JSON parsing, chunking, deduplication, unprobed detection
- `test_filters.py` — categorisation flags, scoring rules
- `test_state.py` — state save/load, corruption handling, domain isolation

---

## Roadmap

- [ ] Parallel chunk processing (multiple subprocess workers)
- [ ] WaybackMachine / gau URL enumeration stage
- [ ] Nuclei template scanning integration
- [ ] Screenshot capture via gowitness
- [ ] SQLite result store for cross-scan diffing and trend tracking
- [ ] GitHub Actions workflow for scheduled scans

---

## Responsible Use

This framework is intended for:

- Authorised bug bounty programmes
- Penetration testing engagements with explicit written permission
- Internal security assessments of assets you own or are authorised to test

Do not run against systems without authorisation.

---

## License

MIT

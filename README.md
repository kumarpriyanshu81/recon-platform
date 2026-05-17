# recon-platform

A modular, extensible reconnaissance orchestration framework built for professional bug bounty and application security workflows.

---

## Features

- **Full passive recon pipeline** — subdomain enumeration → HTTP probing → categorisation → structured output
- **Modular architecture** — each pipeline stage is an isolated, independently testable module
- **Plugin system** — public and private plugins loaded dynamically at runtime
- **Private module support** — proprietary heuristics and methodology stay out of version control
- **Structured output** — JSON report + categorised text files for downstream tooling
- **Production-grade code** — type hints, logging, error handling, clean interfaces
- **Zero mandatory Python deps** — only the stdlib; external tools (subfinder, httpx) on PATH

---

## Architecture

```
recon-platform/
│
├── main.py                  # CLI entry point & pipeline orchestrator
│
├── core/
│   ├── subdomains.py        # SubdomainEnumerator  — wraps subfinder
│   ├── probe.py             # HTTPProber           — wraps httpx, parses JSON-lines
│   ├── filters.py           # ResultFilter         — pattern-based categorisation
│   ├── output.py            # OutputWriter         — serialises all result files
│   ├── utils.py             # Shared helpers (subprocess, path, dedup)
│   └── logger.py            # Centralised logging configuration
│
├── plugins/
│   ├── loader.py            # PluginRegistry + PluginLoader
│   └── sample_plugin.py     # Reference plugin demonstrating all hook points
│
├── private_modules/         # Git-ignored — place proprietary plugins here
│
├── config/
│   └── settings.py          # All tuneable parameters & detection patterns
│
└── output/                  # Git-ignored — scan results written here
```

### Data flow

```
CLI args
   │
   ▼
SubdomainEnumerator (subfinder)
   │   subdomains: list[str]
   ▼
HTTPProber (httpx)
   │   results: list[HostResult]
   ▼
ResultFilter
   │   results with flags: is_login / is_admin / is_api / is_staging
   ▼
OutputWriter
   │   live_hosts.txt, login_pages.txt, api_endpoints.txt,
   │   interesting.txt, subdomains.txt, results.json
   ▼
Plugin hooks fire at each stage boundary
```

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/your-username/recon-platform.git
cd recon-platform
```

### 2. Install external tools

The framework delegates to Go-based tools. Install them once:

```bash
go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest
go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest
```

Ensure `$GOPATH/bin` (typically `~/go/bin`) is on your `PATH`.

### 3. (Optional) Python virtual environment

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

No third-party Python packages are required for the core framework.

---

## Usage

### Basic scan

```bash
python main.py -d example.com
```

### Custom output directory

```bash
python main.py -d example.com --output-dir ./runs/example_20240515
```

### Load subdomains from a file (skip subfinder)

```bash
python main.py -d example.com --subdomains-file ./subs.txt
```

### Verbose / debug output

```bash
python main.py -d example.com -v
```

### Pass extra flags to the underlying tools

```bash
python main.py -d example.com \
  --subfinder-args "-sources shodan,censys" \
  --httpx-args "-follow-redirects"
```

### Disable plugins

```bash
python main.py -d example.com --no-plugins
```

### Full option reference

```
usage: recon-platform [-h] -d DOMAIN [--output-dir DIR] [--skip-enum]
                      [--subdomains-file FILE] [--skip-probe] [--no-plugins]
                      [--subfinder-args ARGS] [--httpx-args ARGS] [-v]
```

---

## Output files

| File | Contents |
|---|---|
| `subdomains.txt` | All discovered subdomains |
| `live_hosts.txt` | URLs of hosts that responded to HTTP |
| `login_pages.txt` | Hosts matching login/auth patterns |
| `api_endpoints.txt` | Hosts matching API path patterns |
| `interesting.txt` | Hosts matching **any** detection category |
| `results.json` | Full structured report with scan metadata |

### results.json structure

```json
{
  "meta": {
    "domain": "example.com",
    "scanned_at": "2024-05-15T10:30:00+00:00",
    "total_subdomains": 142,
    "total_live": 38
  },
  "subdomains": ["..."],
  "live_hosts": [
    {
      "url": "https://api.example.com",
      "host": "api.example.com",
      "status_code": 200,
      "title": "Example API",
      "tech": ["nginx", "React"],
      "flags": {
        "login": false,
        "admin": false,
        "api": true,
        "staging": false
      }
    }
  ],
  "categories": {
    "login_pages": ["..."],
    "admin_panels": ["..."],
    "api_endpoints": ["..."],
    "staging_envs": ["..."]
  }
}
```

---

## Plugin system

### How plugins work

The framework fires hook events at each pipeline stage. Plugins register callback functions against these events via a `PluginRegistry`.

**Supported events:**

| Event | When fired | Arguments |
|---|---|---|
| `pre_enum` | Before subfinder runs | `domain: str` |
| `post_enum` | After enumeration | `domain: str, subdomains: list[str]` |
| `pre_probe` | Before httpx runs | `hosts: list[str]` |
| `post_probe` | After probing | `results: list[HostResult]` |
| `post_filter` | After categorisation | `results: list[HostResult]` |
| `post_output` | After files written | `written_paths: dict[str, Path]` |

### Writing a plugin

Every plugin file must expose a `register(registry)` function:

```python
# plugins/my_plugin.py
from plugins.loader import PluginRegistry

def register(registry: PluginRegistry) -> None:
    registry.on("post_probe", on_post_probe)

def on_post_probe(results):
    for r in results:
        if "nginx/1.14" in r.webserver:
            print(f"[!] Old nginx on {r.url}")
```

### Public vs private plugins

| Location | Version controlled | Purpose |
|---|---|---|
| `plugins/` | Yes | Generic, shareable plugins |
| `private_modules/` | **No** (git-ignored) | Proprietary detection logic |

Drop any `.py` plugin file into `private_modules/` and it loads automatically on the next run — no configuration required.

---

## Configuration

All tunable parameters live in `config/settings.py`. Override any value with an environment variable:

```bash
export SUBFINDER_TIMEOUT=300
export HTTPX_THREADS=100
export LOG_LEVEL=DEBUG
python main.py -d example.com
```

Or use a `.env` file (git-ignored) with `python-dotenv` if desired.

---

## Screenshots

> *Screenshots placeholder — add terminal recordings here (e.g., asciinema).*

---

## Roadmap

- [ ] Nuclei integration for template-based vulnerability scanning
- [ ] WaybackMachine / gau URL enumeration stage
- [ ] Screenshot capture via gowitness
- [ ] Slack / webhook notification hook (reference private plugin)
- [ ] SQLite result store for cross-scan diffing
- [ ] GitHub Actions workflow for scheduled scans

---

## Security & responsible use

This tool is intended for:
- Authorised bug bounty programmes
- Penetration testing engagements with written permission
- Personal lab / CTF environments

Do not run against systems you do not have explicit permission to test.

---

## License

MIT

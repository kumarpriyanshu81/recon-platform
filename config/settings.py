"""
Global configuration and defaults for recon-platform.
Override any value via environment variables or a local .env file.
"""

import os
import shutil
from pathlib import Path


def _resolve_httpx_bin() -> str:
    """
    Auto-detect the ProjectDiscovery httpx binary name.

    Resolution order:
      1. HTTPX_BIN env var  — explicit override always wins
      2. httpx-toolkit      — Kali Linux package name
      3. httpx              — standard Go install / other distros
    """
    env = os.getenv("HTTPX_BIN")
    if env:
        return env
    for candidate in ("httpx-toolkit", "httpx"):
        if shutil.which(candidate):
            return candidate
    return "httpx-toolkit"  # fallback; error surface at runtime

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR: Path = Path(__file__).resolve().parent.parent
OUTPUT_DIR: Path = BASE_DIR / "output"
PRIVATE_MODULES_DIR: Path = BASE_DIR / "private_modules"
PLUGINS_DIR: Path = BASE_DIR / "plugins"

# ---------------------------------------------------------------------------
# External tool binaries
# Prefer explicit env-var overrides so CI/CD or custom installs just work.
# ---------------------------------------------------------------------------
SUBFINDER_BIN: str = os.getenv("SUBFINDER_BIN", "subfinder")
HTTPX_BIN: str = _resolve_httpx_bin()

# ---------------------------------------------------------------------------
# Subfinder options
# ---------------------------------------------------------------------------
SUBFINDER_TIMEOUT: int = int(os.getenv("SUBFINDER_TIMEOUT", "120"))  # seconds
SUBFINDER_THREADS: int = int(os.getenv("SUBFINDER_THREADS", "10"))

# ---------------------------------------------------------------------------
# HTTPX options
# ---------------------------------------------------------------------------
HTTPX_TIMEOUT: int = int(os.getenv("HTTPX_TIMEOUT", "10"))       # per-request
HTTPX_THREADS: int = int(os.getenv("HTTPX_THREADS", "50"))
HTTPX_RATE_LIMIT: int = int(os.getenv("HTTPX_RATE_LIMIT", "150"))  # req/s

# ---------------------------------------------------------------------------
# Detection heuristics
# Values are intentionally generic — proprietary lists live in private_modules/
# ---------------------------------------------------------------------------
LOGIN_PATTERNS: list[str] = [
    "login", "signin", "sign-in", "auth", "authenticate",
    "account/login", "user/login", "wp-login",
]

ADMIN_PATTERNS: list[str] = [
    "admin", "administrator", "dashboard", "panel",
    "manage", "management", "console", "cpanel",
]

API_PATTERNS: list[str] = [
    "/api/", "/api-", "/rest/", "/graphql", "/v1/", "/v2/", "/v3/",
    "/swagger", "/openapi", "/docs/api",
]

STAGING_PATTERNS: list[str] = [
    "staging", "stage", "dev", "develop", "development",
    "test", "testing", "qa", "uat", "sandbox", "preprod",
]

# ---------------------------------------------------------------------------
# Output filenames
# ---------------------------------------------------------------------------
OUTPUT_FILES: dict[str, str] = {
    "live_hosts":    "live_hosts.txt",
    "login_pages":   "login_pages.txt",
    "api_endpoints": "api_endpoints.txt",
    "interesting":   "interesting.txt",
    "results_json":  "results.json",
    "subdomains":    "subdomains.txt",
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"

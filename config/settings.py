"""
Global configuration and defaults for recon-platform.

All values can be overridden at runtime via environment variables.
No code changes are needed when moving between environments.
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
    return "httpx-toolkit"  # surfaced as FileNotFoundError at runtime


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR: Path           = Path(__file__).resolve().parent.parent
OUTPUT_DIR: Path         = BASE_DIR / "output"
PRIVATE_MODULES_DIR: Path = BASE_DIR / "private_modules"
PLUGINS_DIR: Path        = BASE_DIR / "plugins"

# ---------------------------------------------------------------------------
# External tool binaries
# ---------------------------------------------------------------------------
SUBFINDER_BIN: str = os.getenv("SUBFINDER_BIN", "subfinder")
HTTPX_BIN: str     = _resolve_httpx_bin()

# ---------------------------------------------------------------------------
# Subfinder
# ---------------------------------------------------------------------------
SUBFINDER_TIMEOUT: int = int(os.getenv("SUBFINDER_TIMEOUT", "120"))  # seconds
SUBFINDER_THREADS: int = int(os.getenv("SUBFINDER_THREADS", "10"))

# ---------------------------------------------------------------------------
# HTTPX
# ---------------------------------------------------------------------------
HTTPX_TIMEOUT: int    = int(os.getenv("HTTPX_TIMEOUT",    "10"))   # per-request (s)
HTTPX_THREADS: int    = int(os.getenv("HTTPX_THREADS",    "50"))
HTTPX_RATE_LIMIT: int = int(os.getenv("HTTPX_RATE_LIMIT", "150"))  # req/s
HTTPX_CHUNK_SIZE: int = int(os.getenv("HTTPX_CHUNK_SIZE", "500"))  # hosts per subprocess
HTTPX_MAX_RETRIES: int = int(os.getenv("HTTPX_MAX_RETRIES", "1"))  # retry passes

# ---------------------------------------------------------------------------
# Detection patterns — generic public defaults.
# Extend/override these in private_modules/ without touching this file.
# ---------------------------------------------------------------------------

LOGIN_PATTERNS: list[str] = [
    "login", "log in",
    "signin", "sign in", "sign-in",
    "logon", "log on",
    "auth", "authenticate", "authentication",
    "sso", "saml", "oauth", "portal",
    "account/login", "user/login", "wp-login",
    "session/new", "users/sign_in",
]

ADMIN_PATTERNS: list[str] = [
    "admin", "administrator", "superuser",
    "dashboard", "panel", "backoffice", "back-office",
    "manage", "management", "console", "cpanel", "plesk",
    "sysadmin", "ops", "supervisor",
]

API_PATTERNS: list[str] = [
    "/api/", "/api-", "/api.",
    "/rest/", "/restapi",
    "/graphql", "/gql",
    "/v1/", "/v2/", "/v3/", "/v4/",
    "/swagger", "/swagger-ui", "/openapi",
    "/docs/api", "/api-docs", "/redoc",
    "api.", "/service/",
]

STAGING_PATTERNS: list[str] = [
    "staging", "stage",
    "dev", "develop", "development",
    "test", "testing", "qa", "uat",
    "sandbox", "preprod", "pre-prod",
    "beta", "alpha", "preview",
    "canary", "internal", "corp", "intranet",
]

DASHBOARD_PATTERNS: list[str] = [
    "grafana", "kibana", "prometheus", "alertmanager",
    "jenkins", "gitlab", "sonarqube", "sonar",
    "jira", "confluence", "bitbucket",
    "monitor", "monitoring", "metrics",
    "analytics", "stats", "status",
    "portainer", "rancher", "argo", "airflow",
]

# Technologies that raise the interest level of a finding.
# Used for scoring — private_modules can append to this list.
INTERESTING_TECH: list[str] = [
    "Jenkins", "GitLab", "Grafana", "Kibana", "Prometheus",
    "Spring Boot", "Apache Tomcat", "Struts", "JBoss", "WebLogic",
    "Confluence", "Jira", "WordPress", "Drupal", "Magento",
    "Elasticsearch", "Hadoop", "Kubernetes", "Rancher",
]

# ---------------------------------------------------------------------------
# Scoring tiers — assigned by filters.py, readable by plugins/output
# ---------------------------------------------------------------------------
SCORE_HIGH:   str = "HIGH"
SCORE_MEDIUM: str = "MEDIUM"
SCORE_LOW:    str = "LOW"

# ---------------------------------------------------------------------------
# Output filenames
# ---------------------------------------------------------------------------
OUTPUT_FILES: dict[str, str] = {
    "subdomains":    "subdomains.txt",
    "live_hosts":    "live_hosts.txt",
    "login_pages":   "login_pages.txt",
    "api_endpoints": "api_endpoints.txt",
    "interesting":   "interesting.txt",
    "results_json":  "results.json",
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL:       str = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT:      str = "%(asctime)s [%(levelname)-5s] %(name)s: %(message)s"
LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"

"""
HTTP probing via httpx-toolkit / projectdiscovery httpx.

Large host lists are processed in configurable chunks so progress is
reported continuously and partial results survive an interruption.
After the main pass, hosts that produced no response are re-probed once
with an extended per-request timeout to recover slow or rate-limited targets.
"""

from __future__ import annotations

import json
import urllib.parse
from dataclasses import dataclass, field
from typing import Optional

from config import settings
from core.logger import get_logger
from core.utils import require_tool, run_command

log = get_logger(__name__)


@dataclass
class HostResult:
    """
    Structured representation of a single httpx probe result.

    Categorisation flags (is_login, is_admin, is_api, is_staging,
    is_dashboard) and the priority score are set by filters.py after
    probing completes.
    """

    url: str
    input_host: str       # original value fed to httpx (used for retry matching)
    host: str
    status_code: int
    title: str
    tech: list[str]       = field(default_factory=list)
    content_length: int   = 0
    webserver: str        = ""
    cdn: str              = ""
    raw: dict             = field(default_factory=dict)

    # --- Categorisation flags (set by ResultFilter) ---
    is_login:     bool = False
    is_admin:     bool = False
    is_api:       bool = False
    is_staging:   bool = False
    is_dashboard: bool = False

    # --- Priority score: HIGH / MEDIUM / LOW / "" ---
    score: str = ""

    # ------------------------------------------------------------------

    @classmethod
    def from_httpx_line(cls, data: dict) -> "HostResult":
        """
        Build a HostResult from a single httpx JSON-line dict.

        Handles key-name variance across httpx / httpx-toolkit versions:
          technologies  -> "tech" (older) | "technologies" (newer)
          status code   -> "status_code"  | "status-code"
          content-length-> "content_length"| "content-length"
          web server    -> "webserver"     | "web-server"
        """
        tech_list: list[str] = []
        for entry in data.get("tech", data.get("technologies", [])):
            if isinstance(entry, str):
                tech_list.append(entry)
            elif isinstance(entry, dict):
                name = entry.get("name", "")
                if name:
                    tech_list.append(name)

        return cls(
            url=data.get("url", ""),
            input_host=data.get("input", ""),
            host=data.get("host", ""),
            status_code=data.get("status_code", data.get("status-code", 0)),
            title=data.get("title", ""),
            tech=tech_list,
            content_length=data.get("content_length", data.get("content-length", 0)),
            webserver=data.get("webserver", data.get("web-server", "")),
            cdn=data.get("cdn", ""),
            raw=data,
        )

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "host": self.host,
            "status_code": self.status_code,
            "title": self.title,
            "tech": self.tech,
            "content_length": self.content_length,
            "webserver": self.webserver,
            "cdn": self.cdn,
            "score": self.score,
            "flags": {
                "login":     self.is_login,
                "admin":     self.is_admin,
                "api":       self.is_api,
                "staging":   self.is_staging,
                "dashboard": self.is_dashboard,
            },
        }

    def __repr__(self) -> str:
        return (
            f"HostResult(url={self.url!r}, status={self.status_code}, "
            f"score={self.score!r})"
        )


class HTTPProber:
    """
    Wraps httpx-toolkit to probe liveness, extract titles, and detect
    technologies for a provided list of hostnames/URLs.

    Chunked processing
    ------------------
    Hosts are split into batches of ``chunk_size``. Each batch is piped
    to a dedicated httpx subprocess via stdin.  Progress is logged after
    every chunk so long-running scans remain observable.

    Retry pass
    ----------
    After all chunks complete, hosts that produced no result are
    re-probed once with a doubled per-request timeout.  This recovers
    results from slow or rate-limited targets without re-scanning the
    full list.

    Usage::

        prober = HTTPProber(hosts=["sub.example.com"])
        results = prober.run()
    """

    def __init__(
        self,
        hosts: list[str],
        *,
        timeout: int         = settings.HTTPX_TIMEOUT,
        threads: int         = settings.HTTPX_THREADS,
        rate_limit: int      = settings.HTTPX_RATE_LIMIT,
        chunk_size: int      = settings.HTTPX_CHUNK_SIZE,
        max_retries: int     = settings.HTTPX_MAX_RETRIES,
        extra_args: Optional[list[str]] = None,
    ) -> None:
        self.hosts      = hosts
        self.timeout    = timeout
        self.threads    = threads
        self.rate_limit = rate_limit
        self.chunk_size = chunk_size
        self.max_retries = max_retries
        self.extra_args: list[str] = extra_args or []
        self._binary: Optional[str] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> list[HostResult]:
        """
        Probe all hosts in chunks and return a deduplicated list of
        HostResult objects. Returns an empty list on tool failure.
        """
        if not self.hosts:
            log.warning("[PROBE] No hosts provided.")
            return []

        try:
            self._binary = require_tool(settings.HTTPX_BIN)
        except FileNotFoundError as exc:
            log.error("[PROBE] %s", exc)
            return []

        chunks       = self._make_chunks()
        total_chunks = len(chunks)
        all_results: list[HostResult] = []

        log.info(
            "[PROBE] Probing %d hosts — %d chunk(s), %d threads, %d/s rate limit",
            len(self.hosts), total_chunks, self.threads, self.rate_limit,
        )

        for idx, chunk in enumerate(chunks, 1):
            chunk_results = self._probe_chunk(chunk, self.timeout)
            all_results.extend(chunk_results)
            log.info(
                "[PROBE] Chunk %d/%d complete (%d responsive)",
                idx, total_chunks, len(chunk_results),
            )

        # --- Retry pass ---
        if self.max_retries > 0:
            unprobed = self._find_unprobed(all_results)
            if unprobed:
                retry_timeout = self.timeout * 2
                log.info("[PROBE] Retrying %d unresolved hosts ...", len(unprobed))
                retry_results = self._probe_chunk(unprobed, retry_timeout)
                all_results.extend(retry_results)
                log.info("[PROBE] Retry recovered %d additional live hosts.", len(retry_results))

        # --- Deduplicate by URL (guards against retry overlap) ---
        all_results = self._deduplicate(all_results)

        live_rate = len(all_results) / len(self.hosts) * 100 if self.hosts else 0.0
        log.info(
            "[PROBE] Complete — %d/%d hosts live (%.1f%%).",
            len(all_results), len(self.hosts), live_rate,
        )
        return all_results

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _make_chunks(self) -> list[list[str]]:
        return [
            self.hosts[i : i + self.chunk_size]
            for i in range(0, len(self.hosts), self.chunk_size)
        ]

    def _probe_chunk(self, hosts: list[str], timeout: int) -> list[HostResult]:
        """Run httpx against *hosts* (piped via stdin) and parse JSON-line output."""
        host_input = "\n".join(hosts)
        cmd = self._build_command(timeout)

        try:
            # No subprocess-level timeout — httpx manages per-request timeouts
            # internally via -timeout. Killing the process early discards all
            # buffered results for the entire chunk.
            result = run_command(cmd, stdin_input=host_input, timeout=None)
        except Exception as exc:  # noqa: BLE001
            log.error("[PROBE] Chunk subprocess failed: %s", exc)
            return []

        if result.stderr:
            # Truncate long stderr (e.g. verbose httpx output) to keep logs readable
            log.warning("[PROBE] httpx stderr: %s", result.stderr.strip()[:300])
        if result.returncode != 0:
            log.warning("[PROBE] httpx exited with code %d", result.returncode)

        return self._parse_output(result.stdout)

    def _find_unprobed(self, results: list[HostResult]) -> list[str]:
        """
        Return entries from ``self.hosts`` that are absent from *results*.

        Uses three normalisation strategies to match original input against
        httpx output:
          1. ``input_host`` field — the value httpx echoes back
          2. URL hostname component — extracted from the probed URL
          3. Resolved ``host`` field — final IP / CNAME after resolution
        """
        responded: set[str] = set()
        for r in results:
            # Strategy 1: input_host (strips scheme and trailing slash)
            if r.input_host:
                raw = r.input_host.lower()
                for prefix in ("https://", "http://"):
                    if raw.startswith(prefix):
                        raw = raw[len(prefix):]
                responded.add(raw.rstrip("/"))

            # Strategy 2: hostname from the probed URL
            try:
                parsed = urllib.parse.urlparse(r.url)
                if parsed.hostname:
                    responded.add(parsed.hostname.lower())
            except ValueError:
                pass

            # Strategy 3: resolved host (IP or CNAME)
            if r.host:
                responded.add(r.host.lower())

        return [h for h in self.hosts if h.lower() not in responded]

    def _build_command(self, timeout: int) -> list[str]:
        # Hosts arrive via stdin — no URL argument or -l flag required.
        # Only flags verified compatible with httpx-toolkit v1.x are used.
        # content-length and webserver are included in JSON output by default.
        cmd = [
            self._binary,
            "-json",
            "-title",
            "-sc",                    # status-code
            "-td",                    # tech-detect
            "-timeout", str(timeout),
            "-t", str(self.threads),
            "-rl", str(self.rate_limit),
            "-silent",
        ]
        cmd.extend(self.extra_args)
        return cmd

    @staticmethod
    def _parse_output(raw: str) -> list[HostResult]:
        """
        Parse httpx JSON-line output into HostResult objects.

        Malformed lines are skipped with a debug log rather than raising,
        so a single corrupt line does not discard the rest of the chunk.
        """
        results: list[HostResult] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                results.append(HostResult.from_httpx_line(data))
            except json.JSONDecodeError as exc:
                log.debug("[PROBE] Skipping malformed JSON line (%s): %s", exc, line[:120])
        return results

    @staticmethod
    def _deduplicate(results: list[HostResult]) -> list[HostResult]:
        """Remove duplicate entries by URL, preserving first-seen order."""
        seen: set[str] = set()
        deduped: list[HostResult] = []
        for r in results:
            if r.url not in seen:
                seen.add(r.url)
                deduped.append(r)
        return deduped

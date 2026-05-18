"""
HTTP probing via httpx-toolkit.

Runs httpx against a list of hosts and parses its JSON-line output
into a list of structured HostResult objects.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

from config import settings
from core.logger import get_logger
from core.utils import require_tool, run_command

log = get_logger(__name__)


@dataclass
class HostResult:
    """Structured representation of a single httpx probe result."""

    url: str
    host: str
    status_code: int
    title: str
    tech: list[str] = field(default_factory=list)
    content_length: int = 0
    webserver: str = ""
    cdn: str = ""
    raw: dict = field(default_factory=dict)

    # Categorisation flags — populated by filters.py
    is_login: bool = False
    is_admin: bool = False
    is_api: bool = False
    is_staging: bool = False

    @classmethod
    def from_httpx_line(cls, data: dict) -> "HostResult":
        """
        Build a HostResult from a single httpx JSON-line dict.

        Key names vary across httpx versions:
          tech   -> "tech" (older) or "technologies" (newer)
          server -> "webserver" (older) or "webserver" / "web-server"
        """
        # Technology detection — handle both key names and entry shapes
        tech_list: list[str] = []
        for entry in data.get("tech", data.get("technologies", [])):
            if isinstance(entry, str):
                tech_list.append(entry)
            elif isinstance(entry, dict):
                tech_list.append(entry.get("name", ""))

        return cls(
            url=data.get("url", ""),
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
            "flags": {
                "login": self.is_login,
                "admin": self.is_admin,
                "api": self.is_api,
                "staging": self.is_staging,
            },
        }


class HTTPProber:
    """
    Wraps httpx to probe liveness, extract titles, and detect technologies
    for a provided list of hostnames/URLs.

    Usage::

        prober = HTTPProber(hosts=["sub1.example.com", "sub2.example.com"])
        results = prober.run()
    """

    def __init__(
        self,
        hosts: list[str],
        *,
        timeout: int = settings.HTTPX_TIMEOUT,
        threads: int = settings.HTTPX_THREADS,
        rate_limit: int = settings.HTTPX_RATE_LIMIT,
        extra_args: Optional[list[str]] = None,
    ) -> None:
        self.hosts = hosts
        self.timeout = timeout
        self.threads = threads
        self.rate_limit = rate_limit
        self.extra_args: list[str] = extra_args or []
        self._binary: Optional[str] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> list[HostResult]:
        """
        Probe all hosts and return a list of HostResult objects.
        Returns an empty list on tool/execution failure.
        """
        if not self.hosts:
            log.warning("No hosts provided to HTTPProber.")
            return []

        try:
            self._binary = require_tool(settings.HTTPX_BIN)
        except FileNotFoundError as exc:
            log.error("%s", exc)
            return []

        host_input = "\n".join(self.hosts)
        cmd = self._build_command()

        log.info("Probing %d hosts with httpx ...", len(self.hosts))
        try:
            # No subprocess-level timeout — httpx manages per-request timeouts
            # via the -timeout flag. Killing the process early loses all results.
            result = run_command(
                cmd,
                stdin_input=host_input,
                timeout=None,
            )
        except Exception as exc:  # noqa: BLE001
            log.error("httpx failed: %s", exc)
            return []

        if result.stderr:
            log.warning("httpx stderr: %s", result.stderr.strip()[:500])
        if result.returncode != 0:
            log.warning("httpx exited with code %d", result.returncode)

        parsed = self._parse_output(result.stdout)
        log.info("Received %d live host results.", len(parsed))
        return parsed

    def run_from_stdin(self, host_list: list[str]) -> list[HostResult]:
        """Convenience wrapper — identical to run() but accepts an explicit list."""
        self.hosts = host_list
        return self.run()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_command(self) -> list[str]:
        # Hosts are piped via stdin — no file/URL argument needed.
        # Only flags confirmed to work across httpx-toolkit / standard httpx builds.
        # content-length and webserver are included in JSON output by default.
        cmd = [
            self._binary,
            "-json",
            "-title",
            "-sc",              # status-code
            "-td",              # tech-detect
            "-timeout", str(self.timeout),
            "-t", str(self.threads),
            "-rl", str(self.rate_limit),
            "-silent",
        ]
        cmd.extend(self.extra_args)
        return cmd

    @staticmethod
    def _parse_output(raw: str) -> list[HostResult]:
        results: list[HostResult] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                results.append(HostResult.from_httpx_line(data))
            except json.JSONDecodeError:
                log.debug("Non-JSON httpx line skipped: %s", line[:120])
        return results

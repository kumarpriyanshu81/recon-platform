"""
Subdomain enumeration via subfinder.

Keeps all subprocess invocation details isolated here so the rest of
the framework never needs to know which external tool is used.
"""

from pathlib import Path
from typing import Optional

from config import settings
from core.logger import get_logger
from core.utils import deduplicate, require_tool, run_command

log = get_logger(__name__)


class SubdomainEnumerator:
    """
    Wraps subfinder to enumerate subdomains for a given target domain.

    Usage::

        enumerator = SubdomainEnumerator(domain="example.com")
        subdomains = enumerator.run()
    """

    def __init__(
        self,
        domain: str,
        *,
        timeout: int = settings.SUBFINDER_TIMEOUT,
        threads: int = settings.SUBFINDER_THREADS,
        extra_args: Optional[list[str]] = None,
    ) -> None:
        self.domain = domain
        self.timeout = timeout
        self.threads = threads
        self.extra_args: list[str] = extra_args or []
        self._binary: Optional[str] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> list[str]:
        """
        Execute subfinder and return a deduplicated list of subdomains.

        Returns an empty list (never raises) so callers can continue the
        pipeline even when subfinder is not installed or finds nothing.
        """
        try:
            self._binary = require_tool(settings.SUBFINDER_BIN)
        except FileNotFoundError as exc:
            log.error("%s", exc)
            return []

        cmd = self._build_command()
        log.info("Running subfinder against %s …", self.domain)

        try:
            result = run_command(cmd, timeout=self.timeout)
        except Exception as exc:  # noqa: BLE001
            log.error("subfinder failed: %s", exc)
            return []

        if result.returncode != 0 and result.stderr:
            log.warning("subfinder stderr: %s", result.stderr.strip())

        subdomains = self._parse_output(result.stdout)
        log.info("Found %d unique subdomains.", len(subdomains))
        return subdomains

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_command(self) -> list[str]:
        cmd = [
            self._binary,
            "-d", self.domain,
            "-silent",
            "-t", str(self.threads),
        ]
        cmd.extend(self.extra_args)
        return cmd

    @staticmethod
    def _parse_output(raw: str) -> list[str]:
        """Split stdout into a clean, deduplicated list of hostnames."""
        lines = [line.strip().lower() for line in raw.splitlines()]
        return deduplicate([l for l in lines if l])

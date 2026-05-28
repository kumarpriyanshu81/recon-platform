"""
Subdomain enumeration via subfinder.

Isolates all subprocess invocation details so the rest of the
framework has no dependency on which enumeration tool is used.
"""

from __future__ import annotations

import subprocess
from typing import Optional

from config import settings
from core.logger import get_logger
from core.utils import deduplicate, require_tool, run_command

log = get_logger(__name__)


class SubdomainEnumerator:
    """
    Wraps subfinder to enumerate subdomains for a given target domain.

    Returns a deduplicated list of hostnames. Never raises — callers
    receive an empty list on any failure so the pipeline can continue.

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
        self.domain     = domain
        self.timeout    = timeout
        self.threads    = threads
        self.extra_args: list[str] = extra_args or []
        self._binary: Optional[str] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> list[str]:
        """
        Execute subfinder and return a deduplicated list of subdomains.

        On timeout, partial stdout collected before the cutoff is parsed
        and returned so the rest of the pipeline can continue with whatever
        was discovered.  Returns [] only when the tool is not found or
        produces no output at all.
        """
        try:
            self._binary = require_tool(settings.SUBFINDER_BIN)
        except FileNotFoundError as exc:
            log.error("[ENUM] %s", exc)
            return []

        cmd = self._build_command()
        log.info(
            "[ENUM] Running subfinder against %s (timeout=%ds) ...",
            self.domain, self.timeout,
        )

        try:
            result = run_command(cmd, timeout=self.timeout)
        except subprocess.TimeoutExpired as exc:
            return self._handle_timeout(exc)
        except Exception as exc:  # noqa: BLE001
            log.error("[ENUM] subfinder failed: %s", exc)
            return []

        # Log stderr at DEBUG — subfinder emits API key warnings and
        # rate-limit notices at exit 0, which are noise at INFO level.
        if result.stderr:
            log.debug("[ENUM] subfinder stderr: %s", result.stderr.strip()[:500])
        if result.returncode not in (0, 1):
            # Exit 1 often means "no results found", not a crash.
            log.warning("[ENUM] subfinder exited with code %d", result.returncode)

        subdomains = self._parse_output(result.stdout)
        log.info("[ENUM] Found %d unique subdomains for %s.", len(subdomains), self.domain)
        return subdomains

    def _handle_timeout(self, exc: subprocess.TimeoutExpired) -> list[str]:
        """
        Recover partial results from a timed-out subfinder run.

        Python's subprocess.run() kills the process on timeout and then
        drains remaining pipe buffers back into exc.stdout (as bytes,
        regardless of the text=True setting).  Decoding and parsing that
        buffer gives us everything subfinder had already written.
        """
        partial_raw = ""
        if exc.stdout:
            # exc.stdout is always bytes here — decode with replacement so
            # a single bad byte never discards the entire partial output.
            if isinstance(exc.stdout, bytes):
                partial_raw = exc.stdout.decode("utf-8", errors="replace")
            else:
                partial_raw = exc.stdout

        partial = self._parse_output(partial_raw)

        if partial:
            log.warning(
                "[ENUM] subfinder timed out after %ds — "
                "returning %d partial results for %s. "
                "Use --enum-timeout to extend the limit.",
                self.timeout, len(partial), self.domain,
            )
        else:
            log.error(
                "[ENUM] subfinder timed out after %ds with no output for %s.",
                self.timeout, self.domain,
            )

        return partial

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
        """Split stdout into a clean, deduplicated, lowercased list of hostnames."""
        lines = [line.strip().lower() for line in raw.splitlines()]
        return deduplicate([line for line in lines if line])

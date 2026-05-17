"""
Output serialisation — writes all result files to the output/ directory.

Each public method is idempotent; calling it multiple times overwrites
the previous file cleanly.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from config import settings
from core.logger import get_logger
from core.probe import HostResult
from core.utils import ensure_dir

log = get_logger(__name__)


class OutputWriter:
    """
    Persists scan results to disk in multiple formats.

    Args:
        domain:     The scanned target domain (used in the JSON envelope).
        output_dir: Directory where files are written.
                    Defaults to settings.OUTPUT_DIR.
    """

    def __init__(
        self,
        domain: str,
        output_dir: Path | None = None,
    ) -> None:
        self.domain = domain
        self.output_dir = ensure_dir(output_dir or settings.OUTPUT_DIR)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def write_subdomains(self, subdomains: list[str]) -> Path:
        """Write the raw subdomain list."""
        return self._write_lines(
            subdomains,
            settings.OUTPUT_FILES["subdomains"],
        )

    def write_live_hosts(self, results: list[HostResult]) -> Path:
        """Write URLs of all live (probed) hosts."""
        return self._write_lines(
            [r.url for r in results],
            settings.OUTPUT_FILES["live_hosts"],
        )

    def write_login_pages(self, results: list[HostResult]) -> Path:
        return self._write_lines(
            [r.url for r in results if r.is_login],
            settings.OUTPUT_FILES["login_pages"],
        )

    def write_api_endpoints(self, results: list[HostResult]) -> Path:
        return self._write_lines(
            [r.url for r in results if r.is_api],
            settings.OUTPUT_FILES["api_endpoints"],
        )

    def write_interesting(self, results: list[HostResult]) -> Path:
        """Write URLs that matched *any* detection category."""
        interesting = [
            r.url for r in results
            if r.is_login or r.is_admin or r.is_api or r.is_staging
        ]
        return self._write_lines(interesting, settings.OUTPUT_FILES["interesting"])

    def write_json_report(
        self,
        subdomains: list[str],
        results: list[HostResult],
    ) -> Path:
        """
        Write a comprehensive JSON report bundling all findings.
        The envelope includes scan metadata for traceability.
        """
        report = {
            "meta": {
                "domain": self.domain,
                "scanned_at": datetime.now(timezone.utc).isoformat(),
                "total_subdomains": len(subdomains),
                "total_live": len(results),
            },
            "subdomains": subdomains,
            "live_hosts": [r.to_dict() for r in results],
            "categories": {
                "login_pages":   [r.url for r in results if r.is_login],
                "admin_panels":  [r.url for r in results if r.is_admin],
                "api_endpoints": [r.url for r in results if r.is_api],
                "staging_envs":  [r.url for r in results if r.is_staging],
            },
        }
        path = self.output_dir / settings.OUTPUT_FILES["results_json"]
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        log.info("JSON report -> %s", path)
        return path

    def write_all(
        self,
        subdomains: list[str],
        results: list[HostResult],
    ) -> dict[str, Path]:
        """
        Convenience method — write every output file in one call.
        Returns a mapping of label → Path for downstream consumers.
        """
        written: dict[str, Path] = {
            "subdomains":    self.write_subdomains(subdomains),
            "live_hosts":    self.write_live_hosts(results),
            "login_pages":   self.write_login_pages(results),
            "api_endpoints": self.write_api_endpoints(results),
            "interesting":   self.write_interesting(results),
            "results_json":  self.write_json_report(subdomains, results),
        }
        return written

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _write_lines(self, lines: list[str], filename: str) -> Path:
        path = self.output_dir / filename
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        log.info("Wrote %d entries -> %s", len(lines), path)
        return path

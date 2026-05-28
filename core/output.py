"""
Output serialisation — writes all result files to the output/ directory.

Each public method is idempotent; repeated calls overwrite cleanly.
The JSON report is the canonical record of a scan run and contains all
information present in the individual text files plus enriched metadata.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from config import settings
from core.logger import get_logger
from core.utils import ensure_dir

if TYPE_CHECKING:
    from core.probe import HostResult

log = get_logger(__name__)


class OutputWriter:
    """
    Persists scan results to disk in multiple formats.

    Args:
        domain:     Target domain (used in the JSON report envelope).
        output_dir: Directory to write files into.
                    Defaults to ``settings.OUTPUT_DIR``.
    """

    def __init__(
        self,
        domain: str,
        output_dir: Path | None = None,
    ) -> None:
        self.domain     = domain
        self.output_dir = ensure_dir(output_dir or settings.OUTPUT_DIR)

    # ------------------------------------------------------------------
    # Individual writers
    # ------------------------------------------------------------------

    def write_subdomains(self, subdomains: list[str]) -> Path:
        """Write the raw subdomain enumeration output."""
        return self._write_lines(subdomains, settings.OUTPUT_FILES["subdomains"])

    def write_live_hosts(self, results: list[HostResult]) -> Path:
        """Write URLs of all hosts that responded to HTTP probing."""
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
        """
        Write all URLs that matched at least one detection category,
        sorted by score descending (HIGH -> MEDIUM -> LOW -> unscored).
        """
        order = {settings.SCORE_HIGH: 0, settings.SCORE_MEDIUM: 1, settings.SCORE_LOW: 2}
        interesting = [r for r in results if r.score]
        interesting.sort(key=lambda r: order.get(r.score, 9))
        return self._write_lines(
            [r.url for r in interesting],
            settings.OUTPUT_FILES["interesting"],
        )

    def write_json_report(
        self,
        subdomains: list[str],
        results: list[HostResult],
        *,
        duration_seconds: float = 0.0,
    ) -> Path:
        """
        Write the canonical JSON report for a scan run.

        The report is self-describing: every field needed to understand
        the scan (timing, counts, distributions, all findings) is present
        in a single file.
        """
        # --- Category slices ---
        login_urls   = [r.url for r in results if r.is_login]
        admin_urls   = [r.url for r in results if r.is_admin]
        api_urls     = [r.url for r in results if r.is_api]
        staging_urls = [r.url for r in results if r.is_staging]
        dash_urls    = [r.url for r in results if r.is_dashboard]
        interesting  = [r.url for r in results if r.score]

        # --- Score breakdown ---
        score_counts = Counter(r.score for r in results if r.score)

        # --- Status code distribution ---
        status_dist = dict(
            sorted(Counter(str(r.status_code) for r in results).items())
        )

        # --- Technology summary (top 20) ---
        tech_counter: Counter = Counter()
        for r in results:
            tech_counter.update(r.tech)
        top_tech = dict(tech_counter.most_common(20))

        # --- Live rate ---
        live_rate = round(len(results) / len(subdomains) * 100, 1) if subdomains else 0.0

        report = {
            "meta": {
                "domain":           self.domain,
                "scanned_at":       datetime.now(timezone.utc).isoformat(),
                "duration_seconds": round(duration_seconds, 1),
                "stats": {
                    "total_subdomains":  len(subdomains),
                    "total_live":        len(results),
                    "live_rate_pct":     live_rate,
                    "interesting_total": len(interesting),
                    "score_breakdown": {
                        "HIGH":   score_counts.get(settings.SCORE_HIGH,   0),
                        "MEDIUM": score_counts.get(settings.SCORE_MEDIUM, 0),
                        "LOW":    score_counts.get(settings.SCORE_LOW,    0),
                    },
                    "categories": {
                        "login_pages":   len(login_urls),
                        "admin_panels":  len(admin_urls),
                        "api_endpoints": len(api_urls),
                        "staging_envs":  len(staging_urls),
                        "dashboards":    len(dash_urls),
                    },
                    "status_distribution": status_dist,
                    "top_technologies":    top_tech,
                },
            },
            "subdomains": subdomains,
            "live_hosts": [r.to_dict() for r in results],
            "categories": {
                "login_pages":   login_urls,
                "admin_panels":  admin_urls,
                "api_endpoints": api_urls,
                "staging_envs":  staging_urls,
                "dashboards":    dash_urls,
            },
        }

        path = self.output_dir / settings.OUTPUT_FILES["results_json"]
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        log.info("[OUTPUT] JSON report -> %s", path)
        return path

    def write_all(
        self,
        subdomains: list[str],
        results: list[HostResult],
        *,
        duration_seconds: float = 0.0,
    ) -> dict[str, Path]:
        """
        Write every output file in one call.
        Returns a mapping of label -> Path (consumed by plugins via post_output hook).
        """
        written: dict[str, Path] = {
            "subdomains":    self.write_subdomains(subdomains),
            "live_hosts":    self.write_live_hosts(results),
            "login_pages":   self.write_login_pages(results),
            "api_endpoints": self.write_api_endpoints(results),
            "interesting":   self.write_interesting(results),
            "results_json":  self.write_json_report(
                subdomains, results, duration_seconds=duration_seconds
            ),
        }
        log.info("[OUTPUT] Reports written to %s", self.output_dir)
        return written

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _write_lines(self, lines: list[str], filename: str) -> Path:
        path = self.output_dir / filename
        path.write_text(
            "\n".join(lines) + ("\n" if lines else ""),
            encoding="utf-8",
        )
        log.debug("[OUTPUT] %-18s %d entries", filename, len(lines))
        return path

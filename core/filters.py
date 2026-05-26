"""
Pattern-based categorisation and priority scoring of probed hosts.

Detection patterns and scoring constants live in config/settings.py.
Private/proprietary patterns are injected at runtime via private_modules/
without modifying this file.

Scoring tiers
-------------
HIGH    — admin panels, login portals with interesting tech stack
MEDIUM  — login pages, API endpoints
LOW     — staging environments, dashboards, monitoring surfaces
"""

from __future__ import annotations

from config import settings
from core.logger import get_logger
from core.probe import HostResult

log = get_logger(__name__)


class ResultFilter:
    """
    Classifies a list of HostResult objects by setting category flags
    (is_login, is_admin, is_api, is_staging, is_dashboard) and a
    priority score (HIGH / MEDIUM / LOW).

    Custom pattern lists can be injected at construction time, enabling
    private_modules to extend detection without modifying public code.

    Usage::

        rf = ResultFilter()
        rf.apply(results)
        high_priority = [r for r in results if r.score == "HIGH"]
    """

    def __init__(
        self,
        *,
        login_patterns:     list[str] | None = None,
        admin_patterns:     list[str] | None = None,
        api_patterns:       list[str] | None = None,
        staging_patterns:   list[str] | None = None,
        dashboard_patterns: list[str] | None = None,
        interesting_tech:   list[str] | None = None,
    ) -> None:
        self.login_patterns     = login_patterns     or settings.LOGIN_PATTERNS
        self.admin_patterns     = admin_patterns     or settings.ADMIN_PATTERNS
        self.api_patterns       = api_patterns       or settings.API_PATTERNS
        self.staging_patterns   = staging_patterns   or settings.STAGING_PATTERNS
        self.dashboard_patterns = dashboard_patterns or settings.DASHBOARD_PATTERNS
        self.interesting_tech   = {t.lower() for t in (interesting_tech or settings.INTERESTING_TECH)}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def apply(self, results: list[HostResult]) -> list[HostResult]:
        """
        Classify each result in-place (sets flags + score) and return
        the same list.
        """
        categorised = 0
        for result in results:
            self._classify(result)
            result.score = self._compute_score(result)
            if result.score:
                categorised += 1

        log.info(
            "[FILTER] Categorised %d/%d hosts — HIGH=%d MEDIUM=%d LOW=%d",
            categorised, len(results),
            sum(1 for r in results if r.score == settings.SCORE_HIGH),
            sum(1 for r in results if r.score == settings.SCORE_MEDIUM),
            sum(1 for r in results if r.score == settings.SCORE_LOW),
        )
        return results

    # --- Convenience accessors ---

    @staticmethod
    def get_login_pages(results: list[HostResult]) -> list[HostResult]:
        return [r for r in results if r.is_login]

    @staticmethod
    def get_admin_panels(results: list[HostResult]) -> list[HostResult]:
        return [r for r in results if r.is_admin]

    @staticmethod
    def get_api_endpoints(results: list[HostResult]) -> list[HostResult]:
        return [r for r in results if r.is_api]

    @staticmethod
    def get_staging_envs(results: list[HostResult]) -> list[HostResult]:
        return [r for r in results if r.is_staging]

    @staticmethod
    def get_dashboards(results: list[HostResult]) -> list[HostResult]:
        return [r for r in results if r.is_dashboard]

    @staticmethod
    def get_interesting(results: list[HostResult]) -> list[HostResult]:
        """All hosts that matched at least one category."""
        return [r for r in results if r.score]

    @staticmethod
    def get_by_score(results: list[HostResult], score: str) -> list[HostResult]:
        return [r for r in results if r.score == score]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _classify(self, result: HostResult) -> None:
        """Set all category flags on *result* based on URL, title, and host."""
        url_title  = (result.url + " " + result.title).lower()
        url_lower  = result.url.lower()
        host_lower = result.host.lower()
        # Also check input hostname for staging/dashboard — the subdomain
        # itself is often the clearest signal.
        fqdn_lower = result.input_host.lower()

        result.is_login     = self._matches_any(url_title, self.login_patterns)
        result.is_admin     = self._matches_any(url_title, self.admin_patterns)
        result.is_api       = self._matches_any(url_lower, self.api_patterns)
        result.is_staging   = self._matches_any(
            fqdn_lower + " " + host_lower, self.staging_patterns
        )
        result.is_dashboard = self._matches_any(
            url_title + " " + fqdn_lower, self.dashboard_patterns
        )

    def _compute_score(self, result: HostResult) -> str:
        """
        Assign a priority score based on the highest-signal category.

        Rules (evaluated in order — first match wins):
          HIGH    admin panel
          HIGH    login portal with an interesting technology detected
          MEDIUM  login portal
          MEDIUM  API endpoint
          LOW     staging / dev environment
          LOW     dashboard / monitoring surface
          ""      not categorised
        """
        if result.is_admin:
            return settings.SCORE_HIGH
        if result.is_login and self._has_interesting_tech(result):
            return settings.SCORE_HIGH
        if result.is_login:
            return settings.SCORE_MEDIUM
        if result.is_api:
            return settings.SCORE_MEDIUM
        if result.is_staging or result.is_dashboard:
            return settings.SCORE_LOW
        return ""

    def _has_interesting_tech(self, result: HostResult) -> bool:
        """Return True if the host runs any technology in the interesting_tech set."""
        return any(t.lower() in self.interesting_tech for t in result.tech)

    @staticmethod
    def _matches_any(text: str, patterns: list[str]) -> bool:
        return any(pat in text for pat in patterns)

"""
Pattern-based categorisation of probed hosts.

All heuristic patterns live in config/settings.py so they can be tuned
without touching this file. Private/proprietary patterns can be injected
at runtime by private_modules.
"""

from __future__ import annotations

from core.logger import get_logger
from core.probe import HostResult
from config import settings

log = get_logger(__name__)


class ResultFilter:
    """
    Applies pattern-based filters to a list of HostResult objects,
    setting boolean flags (is_login, is_admin, is_api, is_staging).

    Custom pattern lists can be injected at construction time, enabling
    private_modules to extend detection without modifying public code.

    Usage::

        rf = ResultFilter()
        categorised = rf.apply(results)
        login_pages = rf.get_login_pages(categorised)
    """

    def __init__(
        self,
        *,
        login_patterns: list[str] | None = None,
        admin_patterns: list[str] | None = None,
        api_patterns: list[str] | None = None,
        staging_patterns: list[str] | None = None,
    ) -> None:
        self.login_patterns = login_patterns or settings.LOGIN_PATTERNS
        self.admin_patterns = admin_patterns or settings.ADMIN_PATTERNS
        self.api_patterns = api_patterns or settings.API_PATTERNS
        self.staging_patterns = staging_patterns or settings.STAGING_PATTERNS

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def apply(self, results: list[HostResult]) -> list[HostResult]:
        """Classify each result in-place and return the same list."""
        for result in results:
            self._classify(result)
        return results

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
    def get_interesting(results: list[HostResult]) -> list[HostResult]:
        """Hosts that match *any* category."""
        return [
            r for r in results
            if r.is_login or r.is_admin or r.is_api or r.is_staging
        ]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _classify(self, result: HostResult) -> None:
        url_lower = result.url.lower()
        title_lower = result.title.lower()
        host_lower = result.host.lower()

        result.is_login = self._matches_any(
            url_lower + " " + title_lower, self.login_patterns
        )
        result.is_admin = self._matches_any(
            url_lower + " " + title_lower, self.admin_patterns
        )
        result.is_api = self._matches_any(url_lower, self.api_patterns)
        result.is_staging = self._matches_any(host_lower, self.staging_patterns)

    @staticmethod
    def _matches_any(text: str, patterns: list[str]) -> bool:
        return any(pat in text for pat in patterns)

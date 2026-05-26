"""
Tests for core.filters — categorisation flags and priority scoring.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.filters import ResultFilter
from core.probe import HostResult
from config import settings


def _make_result(
    url="https://example.com",
    title="",
    host="1.2.3.4",
    input_host="example.com",
    tech=None,
) -> HostResult:
    return HostResult(
        url=url,
        input_host=input_host,
        host=host,
        status_code=200,
        title=title,
        tech=tech or [],
    )


class TestCategorisation:
    """Flag assignment based on URL, title, and host patterns."""

    rf = ResultFilter()

    def test_login_by_url(self):
        r = _make_result(url="https://accounts.example.com/login")
        self.rf._classify(r)
        assert r.is_login

    def test_login_by_title(self):
        r = _make_result(title="Sign In to Your Account")
        self.rf._classify(r)
        assert r.is_login

    def test_admin_by_url(self):
        r = _make_result(url="https://example.com/admin/dashboard")
        self.rf._classify(r)
        assert r.is_admin

    def test_api_by_url(self):
        r = _make_result(url="https://api.example.com/v1/users")
        self.rf._classify(r)
        assert r.is_api

    def test_staging_by_subdomain(self):
        r = _make_result(
            url="https://staging.example.com",
            input_host="staging.example.com",
        )
        self.rf._classify(r)
        assert r.is_staging

    def test_staging_by_dev_subdomain(self):
        r = _make_result(
            url="https://dev.example.com",
            input_host="dev.example.com",
        )
        self.rf._classify(r)
        assert r.is_staging

    def test_dashboard_by_title(self):
        r = _make_result(title="Grafana - Home")
        self.rf._classify(r)
        assert r.is_dashboard

    def test_dashboard_by_url(self):
        r = _make_result(url="https://kibana.example.com")
        self.rf._classify(r)
        assert r.is_dashboard

    def test_plain_host_not_categorised(self):
        r = _make_result(url="https://www.example.com", title="Welcome")
        self.rf._classify(r)
        assert not any([r.is_login, r.is_admin, r.is_api, r.is_staging, r.is_dashboard])

    def test_multiple_flags_can_coexist(self):
        """A staging API endpoint should have both is_staging and is_api set."""
        r = _make_result(
            url="https://staging-api.example.com/v1/",
            input_host="staging-api.example.com",
        )
        self.rf._classify(r)
        assert r.is_api
        assert r.is_staging


class TestScoring:
    """Priority score assignment."""

    rf = ResultFilter()

    def _score(self, **kwargs) -> str:
        r = _make_result(**kwargs)
        self.rf._classify(r)
        return self.rf._compute_score(r)

    def test_admin_is_high(self):
        assert self._score(url="https://example.com/admin") == settings.SCORE_HIGH

    def test_login_with_interesting_tech_is_high(self):
        r = _make_result(
            url="https://example.com/login",
            tech=["Jenkins"],
        )
        self.rf._classify(r)
        score = self.rf._compute_score(r)
        assert score == settings.SCORE_HIGH

    def test_login_without_interesting_tech_is_medium(self):
        assert self._score(url="https://example.com/login") == settings.SCORE_MEDIUM

    def test_api_is_medium(self):
        assert self._score(url="https://api.example.com/v1/") == settings.SCORE_MEDIUM

    def test_staging_is_low(self):
        score = self._score(
            url="https://staging.example.com",
            input_host="staging.example.com",
        )
        assert score == settings.SCORE_LOW

    def test_dashboard_is_low(self):
        assert self._score(title="Grafana - Home") == settings.SCORE_LOW

    def test_plain_host_has_no_score(self):
        assert self._score(url="https://www.example.com", title="Welcome") == ""

    def test_admin_beats_staging(self):
        """Admin pattern takes priority over staging subdomain."""
        r = _make_result(
            url="https://staging.example.com/admin",
            input_host="staging.example.com",
        )
        self.rf._classify(r)
        score = self.rf._compute_score(r)
        assert score == settings.SCORE_HIGH


class TestApply:
    """Integration: apply() sets both flags and scores."""

    def test_apply_sets_score(self):
        r = _make_result(url="https://example.com/admin")
        ResultFilter().apply([r])
        assert r.score == settings.SCORE_HIGH
        assert r.is_admin

    def test_apply_returns_same_list(self):
        results = [_make_result(), _make_result()]
        rf = ResultFilter()
        out = rf.apply(results)
        assert out is results

    def test_get_interesting_returns_scored_only(self):
        r1 = _make_result(url="https://example.com/admin")
        r2 = _make_result(url="https://www.example.com", title="Welcome")
        ResultFilter().apply([r1, r2])
        interesting = ResultFilter.get_interesting([r1, r2])
        assert r1 in interesting
        assert r2 not in interesting

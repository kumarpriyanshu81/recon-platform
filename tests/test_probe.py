"""
Tests for core.probe — HostResult parsing, chunking, deduplication,
and unprobed-host detection.
"""

import json
import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.probe import HostResult, HTTPProber


# ---------------------------------------------------------------------------
# HostResult.from_httpx_line
# ---------------------------------------------------------------------------

class TestHostResultParsing:
    """Covers key-name variance between httpx versions and malformed data."""

    def _make_prober(self, hosts=None):
        return HTTPProber(hosts or ["example.com"])

    def test_basic_parse(self):
        data = {
            "url": "https://example.com",
            "input": "example.com",
            "host": "1.2.3.4",
            "status_code": 200,
            "title": "Example",
            "technologies": ["nginx"],
        }
        r = HostResult.from_httpx_line(data)
        assert r.url == "https://example.com"
        assert r.status_code == 200
        assert r.title == "Example"
        assert "nginx" in r.tech

    def test_old_tech_key(self):
        """Older httpx uses 'tech' instead of 'technologies'."""
        data = {
            "url": "https://a.com", "input": "a.com",
            "host": "1.1.1.1", "status_code": 200, "title": "",
            "tech": ["Apache"],
        }
        r = HostResult.from_httpx_line(data)
        assert "Apache" in r.tech

    def test_tech_as_dict_entries(self):
        """Some httpx builds emit tech as a list of dicts with 'name' key."""
        data = {
            "url": "https://b.com", "input": "b.com",
            "host": "2.2.2.2", "status_code": 200, "title": "",
            "technologies": [{"name": "React"}, {"name": "nginx"}],
        }
        r = HostResult.from_httpx_line(data)
        assert "React" in r.tech
        assert "nginx" in r.tech

    def test_hyphenated_keys(self):
        """Handles 'status-code' and 'content-length' with hyphens."""
        data = {
            "url": "https://c.com", "input": "c.com",
            "host": "3.3.3.3", "status-code": 301, "title": "",
            "content-length": 512, "web-server": "cloudflare",
        }
        r = HostResult.from_httpx_line(data)
        assert r.status_code == 301
        assert r.content_length == 512
        assert r.webserver == "cloudflare"

    def test_missing_fields_default(self):
        """Missing optional fields must not raise — fall back to defaults."""
        r = HostResult.from_httpx_line({"url": "https://d.com"})
        assert r.status_code == 0
        assert r.title == ""
        assert r.tech == []
        assert r.content_length == 0

    def test_to_dict_contains_score_and_flags(self):
        r = HostResult.from_httpx_line(
            {"url": "https://e.com", "input": "e.com", "host": "5.5.5.5",
             "status_code": 200, "title": ""}
        )
        r.score    = "HIGH"
        r.is_admin = True
        d = r.to_dict()
        assert d["score"] == "HIGH"
        assert d["flags"]["admin"] is True
        assert "dashboard" in d["flags"]


# ---------------------------------------------------------------------------
# HTTPProber._make_chunks
# ---------------------------------------------------------------------------

class TestChunking:
    def _prober(self, hosts, chunk_size=500):
        return HTTPProber(hosts, chunk_size=chunk_size)

    def test_exact_multiple(self):
        hosts = [f"h{i}" for i in range(1000)]
        chunks = self._prober(hosts, chunk_size=500)._make_chunks()
        assert len(chunks) == 2
        assert all(len(c) == 500 for c in chunks)

    def test_remainder_chunk(self):
        hosts = [f"h{i}" for i in range(1250)]
        chunks = self._prober(hosts, chunk_size=500)._make_chunks()
        assert len(chunks) == 3
        assert len(chunks[2]) == 250

    def test_single_chunk(self):
        hosts = ["a", "b", "c"]
        chunks = self._prober(hosts, chunk_size=500)._make_chunks()
        assert len(chunks) == 1
        assert chunks[0] == ["a", "b", "c"]

    def test_chunk_size_one(self):
        hosts = ["x", "y", "z"]
        chunks = self._prober(hosts, chunk_size=1)._make_chunks()
        assert len(chunks) == 3

    def test_empty_hosts(self):
        chunks = self._prober([], chunk_size=500)._make_chunks()
        assert chunks == []


# ---------------------------------------------------------------------------
# HTTPProber._parse_output
# ---------------------------------------------------------------------------

class TestParseOutput:
    def test_valid_json_line(self):
        line = json.dumps({
            "url": "https://x.com", "input": "x.com",
            "host": "1.1.1.1", "status_code": 200, "title": "X",
        })
        results = HTTPProber._parse_output(line)
        assert len(results) == 1
        assert results[0].url == "https://x.com"

    def test_multiple_lines(self):
        lines = "\n".join(
            json.dumps({"url": f"https://h{i}.com", "input": f"h{i}.com",
                        "host": "1.1.1.1", "status_code": 200, "title": ""})
            for i in range(5)
        )
        results = HTTPProber._parse_output(lines)
        assert len(results) == 5

    def test_skips_malformed_lines(self):
        good = json.dumps({"url": "https://ok.com", "status_code": 200, "title": ""})
        bad  = "this is not json {"
        results = HTTPProber._parse_output(f"{good}\n{bad}\n")
        assert len(results) == 1

    def test_empty_input(self):
        assert HTTPProber._parse_output("") == []

    def test_blank_lines_skipped(self):
        good = json.dumps({"url": "https://ok.com", "status_code": 200, "title": ""})
        assert len(HTTPProber._parse_output(f"\n\n{good}\n\n")) == 1


# ---------------------------------------------------------------------------
# HTTPProber._deduplicate
# ---------------------------------------------------------------------------

class TestDeduplication:
    def _result(self, url: str) -> HostResult:
        return HostResult.from_httpx_line(
            {"url": url, "input": url, "host": "1.1.1.1",
             "status_code": 200, "title": ""}
        )

    def test_removes_duplicate_urls(self):
        r1 = self._result("https://a.com")
        r2 = self._result("https://b.com")
        r3 = self._result("https://a.com")  # duplicate
        out = HTTPProber._deduplicate([r1, r2, r3])
        assert len(out) == 2
        assert out[0].url == "https://a.com"
        assert out[1].url == "https://b.com"

    def test_preserves_order(self):
        results = [self._result(f"https://h{i}.com") for i in range(5)]
        out = HTTPProber._deduplicate(results)
        assert [r.url for r in out] == [r.url for r in results]

    def test_empty_list(self):
        assert HTTPProber._deduplicate([]) == []


# ---------------------------------------------------------------------------
# HTTPProber._find_unprobed
# ---------------------------------------------------------------------------

class TestFindUnprobed:
    def _make_result(self, url, input_host, host="1.1.1.1"):
        return HostResult.from_httpx_line(
            {"url": url, "input": input_host, "host": host,
             "status_code": 200, "title": ""}
        )

    def test_responded_host_excluded(self):
        prober = HTTPProber(["sub.example.com", "other.example.com"])
        r = self._make_result("https://sub.example.com", "sub.example.com")
        unprobed = prober._find_unprobed([r])
        assert "other.example.com" in unprobed
        assert "sub.example.com" not in unprobed

    def test_all_responded(self):
        hosts = ["a.com", "b.com"]
        prober = HTTPProber(hosts)
        results = [
            self._make_result("https://a.com", "a.com"),
            self._make_result("https://b.com", "b.com"),
        ]
        assert prober._find_unprobed(results) == []

    def test_none_responded(self):
        hosts = ["a.com", "b.com"]
        prober = HTTPProber(hosts)
        assert prober._find_unprobed([]) == hosts

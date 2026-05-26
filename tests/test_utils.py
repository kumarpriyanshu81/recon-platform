"""Tests for core.utils — sanitise_domain and deduplicate."""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.utils import deduplicate, sanitise_domain


class TestSanitiseDomain:
    def test_strips_https(self):
        assert sanitise_domain("https://example.com") == "example.com"

    def test_strips_http(self):
        assert sanitise_domain("http://example.com") == "example.com"

    def test_strips_double_slash(self):
        assert sanitise_domain("//example.com") == "example.com"

    def test_strips_trailing_slash(self):
        assert sanitise_domain("example.com/") == "example.com"

    def test_lowercases(self):
        assert sanitise_domain("Example.COM") == "example.com"

    def test_plain_domain_unchanged(self):
        assert sanitise_domain("example.com") == "example.com"

    def test_strips_url_with_path(self):
        assert sanitise_domain("https://example.com/") == "example.com"

    def test_subdomain_preserved(self):
        assert sanitise_domain("https://sub.example.com") == "sub.example.com"


class TestDeduplicate:
    def test_removes_duplicates(self):
        assert deduplicate(["a", "b", "a", "c"]) == ["a", "b", "c"]

    def test_preserves_order(self):
        assert deduplicate(["c", "a", "b", "a"]) == ["c", "a", "b"]

    def test_empty_list(self):
        assert deduplicate([]) == []

    def test_no_duplicates(self):
        items = ["x", "y", "z"]
        assert deduplicate(items) == items

    def test_all_duplicates(self):
        assert deduplicate(["a", "a", "a"]) == ["a"]

    def test_single_item(self):
        assert deduplicate(["only"]) == ["only"]

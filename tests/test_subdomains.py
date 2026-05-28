"""
Tests for core.subdomains — timeout recovery and output parsing.
"""

import subprocess
import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.subdomains import SubdomainEnumerator


def _make_enumerator(domain="example.com", timeout=120):
    return SubdomainEnumerator(domain, timeout=timeout)


class TestParseOutput:
    def test_basic_lines(self):
        raw = "sub1.example.com\nsub2.example.com\nsub3.example.com\n"
        result = SubdomainEnumerator._parse_output(raw)
        assert result == ["sub1.example.com", "sub2.example.com", "sub3.example.com"]

    def test_deduplicates(self):
        raw = "a.example.com\nb.example.com\na.example.com\n"
        result = SubdomainEnumerator._parse_output(raw)
        assert result == ["a.example.com", "b.example.com"]

    def test_lowercases(self):
        raw = "SUB.Example.COM\n"
        result = SubdomainEnumerator._parse_output(raw)
        assert result == ["sub.example.com"]

    def test_strips_whitespace(self):
        raw = "  sub.example.com  \n\n  other.example.com\n"
        result = SubdomainEnumerator._parse_output(raw)
        assert result == ["sub.example.com", "other.example.com"]

    def test_empty_input(self):
        assert SubdomainEnumerator._parse_output("") == []

    def test_blank_lines_ignored(self):
        raw = "\n\nsub.example.com\n\n"
        assert SubdomainEnumerator._parse_output(raw) == ["sub.example.com"]


class TestHandleTimeout:
    """
    _handle_timeout() must salvage partial stdout from a TimeoutExpired
    exception and return whatever subdomains were collected before cutoff.
    """

    def _exc(self, stdout) -> subprocess.TimeoutExpired:
        """Build a minimal TimeoutExpired with the given stdout payload."""
        exc = subprocess.TimeoutExpired(cmd=["subfinder"], timeout=30)
        exc.stdout = stdout
        exc.stderr = None
        return exc

    def test_returns_partial_bytes(self):
        """Bytes payload (the normal case — subprocess always gives bytes here)."""
        partial_output = b"a.example.com\nb.example.com\n"
        enumerator = _make_enumerator()
        result = enumerator._handle_timeout(self._exc(partial_output))
        assert result == ["a.example.com", "b.example.com"]

    def test_returns_partial_str(self):
        """String payload — defensive handling for edge cases."""
        partial_output = "a.example.com\nb.example.com\n"
        enumerator = _make_enumerator()
        result = enumerator._handle_timeout(self._exc(partial_output))
        assert result == ["a.example.com", "b.example.com"]

    def test_returns_empty_on_no_output(self):
        """No output before timeout — should return empty list, not raise."""
        enumerator = _make_enumerator()
        result = enumerator._handle_timeout(self._exc(None))
        assert result == []

    def test_returns_empty_on_empty_bytes(self):
        enumerator = _make_enumerator()
        result = enumerator._handle_timeout(self._exc(b""))
        assert result == []

    def test_deduplicates_partial_output(self):
        """Partial stdout may contain duplicates if subfinder outputs them."""
        partial_output = b"sub.example.com\nsub.example.com\nother.example.com\n"
        enumerator = _make_enumerator()
        result = enumerator._handle_timeout(self._exc(partial_output))
        assert result == ["sub.example.com", "other.example.com"]

    def test_tolerates_bad_utf8(self):
        """A single corrupt byte must not discard the rest of the output."""
        partial_output = b"good.example.com\n\xff\nbad-byte.example.com\n"
        enumerator = _make_enumerator()
        result = enumerator._handle_timeout(self._exc(partial_output))
        # At minimum, the good line must be present
        assert "good.example.com" in result


class TestCLITimeout:
    """Verify --enum-timeout is plumbed through the arg parser correctly."""

    def test_enum_timeout_parsed(self):
        from main import build_arg_parser
        parser = build_arg_parser()
        args = parser.parse_args(["-d", "example.com", "--enum-timeout", "600"])
        assert args.enum_timeout == 600

    def test_enum_timeout_defaults_to_none(self):
        from main import build_arg_parser
        parser = build_arg_parser()
        args = parser.parse_args(["-d", "example.com"])
        assert args.enum_timeout is None

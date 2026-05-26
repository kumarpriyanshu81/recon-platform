"""
Tests for resumable scan state — save, load, corruption handling.
"""

import json
import sys
import os
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main import _save_state, _load_state


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


class TestSaveState:
    def test_creates_state_file(self, tmp_dir):
        _save_state("example.com", ["a.example.com", "b.example.com"], tmp_dir)
        state_file = tmp_dir / ".state_example.com.json"
        assert state_file.exists()

    def test_saved_content_is_valid_json(self, tmp_dir):
        subs = ["a.example.com", "b.example.com"]
        _save_state("example.com", subs, tmp_dir)
        state_file = tmp_dir / ".state_example.com.json"
        data = json.loads(state_file.read_text())
        assert data["domain"] == "example.com"
        assert data["subdomains"] == subs

    def test_overwrites_existing_state(self, tmp_dir):
        _save_state("example.com", ["old.example.com"], tmp_dir)
        _save_state("example.com", ["new.example.com"], tmp_dir)
        data = json.loads((tmp_dir / ".state_example.com.json").read_text())
        assert data["subdomains"] == ["new.example.com"]


class TestLoadState:
    def test_returns_none_when_no_state(self, tmp_dir):
        assert _load_state("example.com", tmp_dir) is None

    def test_loads_saved_subdomains(self, tmp_dir):
        subs = ["x.example.com", "y.example.com"]
        _save_state("example.com", subs, tmp_dir)
        loaded = _load_state("example.com", tmp_dir)
        assert loaded == subs

    def test_handles_corrupt_json(self, tmp_dir):
        state_file = tmp_dir / ".state_example.com.json"
        state_file.write_text("this is not valid json", encoding="utf-8")
        assert _load_state("example.com", tmp_dir) is None

    def test_handles_missing_subdomains_key(self, tmp_dir):
        state_file = tmp_dir / ".state_example.com.json"
        state_file.write_text(json.dumps({"domain": "example.com"}), encoding="utf-8")
        assert _load_state("example.com", tmp_dir) is None

    def test_handles_wrong_type_for_subdomains(self, tmp_dir):
        state_file = tmp_dir / ".state_example.com.json"
        state_file.write_text(
            json.dumps({"domain": "example.com", "subdomains": "not-a-list"}),
            encoding="utf-8",
        )
        assert _load_state("example.com", tmp_dir) is None

    def test_empty_subdomains_list_loads(self, tmp_dir):
        _save_state("example.com", [], tmp_dir)
        loaded = _load_state("example.com", tmp_dir)
        assert loaded == []

    def test_domain_isolation(self, tmp_dir):
        """State for different domains must not cross-contaminate."""
        _save_state("a.com", ["sub.a.com"], tmp_dir)
        _save_state("b.com", ["sub.b.com"], tmp_dir)
        assert _load_state("a.com", tmp_dir) == ["sub.a.com"]
        assert _load_state("b.com", tmp_dir) == ["sub.b.com"]

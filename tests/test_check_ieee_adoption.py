"""Unit tests for tools/check_ieee_adoption.py. No network in any test."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import check_ieee_adoption  # noqa: E402

from omh_shim import SCHEMA_IDS  # noqa: E402

# --- build_measure_index ---


def test_build_measure_index_parses_versioned_filename():
    index = check_ieee_adoption.build_measure_index(["schemas/sleep/sleep-episode-1.0.json"])
    assert index == {"sleep-episode": {"1.0"}}


def test_build_measure_index_skips_metadata_and_utility():
    index = check_ieee_adoption.build_measure_index([
        "schemas/metadata/header-1.0.json",
        "schemas/utility/time-frame-1.0.json",
    ])
    assert index == {}


def test_build_measure_index_ignores_unparseable_filename():
    index = check_ieee_adoption.build_measure_index(["schemas/README.md"])
    assert index == {}


def test_build_measure_index_merges_multiple_versions_of_same_measure():
    index = check_ieee_adoption.build_measure_index([
        "schemas/sleep/sleep-episode-1.0.json",
        "schemas/sleep/sleep-episode-2.0.json",
    ])
    assert index == {"sleep-episode": {"1.0", "2.0"}}


# --- find_findings: real current state ---


def test_find_findings_empty_for_real_current_state():
    index = {"physical-activity": {"1.0"}, "sleep-episode": {"1.0"}}
    assert check_ieee_adoption.find_findings(index, SCHEMA_IDS) == []


# --- find_findings: non-vacuity (tests 5 and 6 from the brief) ---


def test_find_findings_detects_adopt():
    # heart_rate resolves to omh:heart-rate:2.0; IEEE publishing heart-rate-1.0 must flag ADOPT.
    index = {"heart-rate": {"1.0"}}
    findings = check_ieee_adoption.find_findings(index, SCHEMA_IDS)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.data_type == "heart_rate"
    assert finding.kind == "ADOPT"
    assert finding.current == "omh:heart-rate:2.0"
    assert finding.versions == ("1.0",)


def test_find_findings_detects_newer():
    # sleep_episode resolves to ieee:sleep-episode:1.0; a published 2.0 must flag NEWER.
    index = {"sleep-episode": {"1.0", "2.0"}}
    findings = check_ieee_adoption.find_findings(index, SCHEMA_IDS)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.data_type == "sleep_episode"
    assert finding.kind == "NEWER"
    assert finding.current == "ieee:sleep-episode:1.0"


def test_find_findings_gutted_classification_would_fail_these():
    # A classifier that always returns [] (the vacuous "all clear" failure mode) fails both.
    index = {"heart-rate": {"1.0"}, "sleep-episode": {"1.0", "2.0"}}
    findings = check_ieee_adoption.find_findings(index, SCHEMA_IDS)
    kinds = {f.kind for f in findings}
    assert kinds == {"ADOPT", "NEWER"}


# --- version comparison ---


def test_version_comparison_is_numeric_not_lexicographic():
    schema_ids = {"heart_rate": "ieee:heart-rate:1.9"}
    index = {"heart-rate": {"1.10"}}
    findings = check_ieee_adoption.find_findings(index, schema_ids)
    assert len(findings) == 1
    assert findings[0].kind == "NEWER"


def test_version_comparison_does_not_flag_lexicographically_smaller_but_numerically_equal():
    schema_ids = {"heart_rate": "ieee:heart-rate:1.10"}
    index = {"heart-rate": {"1.9"}}
    assert check_ieee_adoption.find_findings(index, schema_ids) == []


# --- no finding when IEEE doesn't publish the measure ---


def test_find_findings_no_finding_for_unpublished_measure():
    index = {"some-other-measure": {"1.0"}}
    assert check_ieee_adoption.find_findings(index, SCHEMA_IDS) == []


# --- fetch_schema_paths: paging and error visibility, no network ---


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_fetch_schema_paths_pages_until_empty(monkeypatch):
    pages = [
        json.dumps([
            {"type": "blob", "path": "schemas/sleep/sleep-episode-1.0.json"},
            {"type": "tree", "path": "schemas/sleep"},
            {"type": "blob", "path": "schemas/README.md"},
        ]).encode(),
        json.dumps([]).encode(),
    ]

    def fake_urlopen(req):
        return _FakeResponse(pages.pop(0))

    monkeypatch.setattr(check_ieee_adoption.urllib.request, "urlopen", fake_urlopen)
    paths = check_ieee_adoption.fetch_schema_paths("omh%2F1752", "1.0.2")
    assert paths == ["schemas/sleep/sleep-episode-1.0.json"]


def test_fetch_schema_paths_raises_on_non_json(monkeypatch):
    # A WAF challenge answers 200 with HTML; this must surface as an error, never as [].
    monkeypatch.setattr(
        check_ieee_adoption.urllib.request, "urlopen",
        lambda req: _FakeResponse(b"<html>blocked</html>"),
    )
    with pytest.raises(RuntimeError, match="non-JSON"):
        check_ieee_adoption.fetch_schema_paths("omh%2F1752", "1.0.2")


def test_fetch_schema_paths_raises_on_request_failure(monkeypatch):
    def fake_urlopen(req):
        raise check_ieee_adoption.urllib.error.URLError("boom")

    monkeypatch.setattr(check_ieee_adoption.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="request failed"):
        check_ieee_adoption.fetch_schema_paths("omh%2F1752", "1.0.2")


# --- main(): exit codes ---


def test_main_returns_zero_with_findings(monkeypatch):
    monkeypatch.setattr(
        check_ieee_adoption, "fetch_schema_paths",
        lambda project, ref: ["schemas/heart_rate/heart-rate-1.0.json"],
    )
    assert check_ieee_adoption.main(["--ref", "1.0.2", "--json"]) == 0


def test_main_returns_nonzero_on_fetch_failure(monkeypatch, capsys):
    def fake_fetch(project, ref):
        raise RuntimeError("network is down")

    monkeypatch.setattr(check_ieee_adoption, "fetch_schema_paths", fake_fetch)
    assert check_ieee_adoption.main(["--ref", "1.0.2"]) == 1
    assert "network is down" in capsys.readouterr().err

"""Unit tests for tools/check_ieee_adoption.py. No network in any test."""

import io
import json
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import check_ieee_adoption  # noqa: E402

from omh_shim import SCHEMA_IDS  # noqa: E402

# --- build_measure_index ---


def test_build_measure_index_parses_versioned_filename():
    index, unparsed = check_ieee_adoption.build_measure_index(["schemas/sleep/sleep-episode-1.0.json"])
    assert index == {"sleep-episode": {"1.0"}}
    assert unparsed == []


def test_build_measure_index_skips_metadata_and_utility():
    index, unparsed = check_ieee_adoption.build_measure_index([
        "schemas/metadata/header-1.0.json",
        "schemas/utility/time-frame-1.0.json",
    ])
    assert index == {}
    assert unparsed == []


def test_build_measure_index_ignores_unparseable_filename():
    index, unparsed = check_ieee_adoption.build_measure_index(["schemas/README.md"])
    assert index == {}
    assert unparsed == ["README.md"]


def test_build_measure_index_merges_multiple_versions_of_same_measure():
    index, unparsed = check_ieee_adoption.build_measure_index([
        "schemas/sleep/sleep-episode-1.0.json",
        "schemas/sleep/sleep-episode-2.0.json",
    ])
    assert index == {"sleep-episode": {"1.0", "2.0"}}
    assert unparsed == []


# --- build_measure_index: finding 2 — non-<major>.<minor> filenames must surface, not vanish ---


@pytest.mark.parametrize("basename", [
    "heart-rate-1.0.1.json",
    "heart-rate-1.x.json",
    "heart-rate-2.json",
    "heart-rate-1.0-draft.json",
])
def test_build_measure_index_reports_unparseable_measure_filenames(basename):
    index, unparsed = check_ieee_adoption.build_measure_index([f"schemas/heart_rate/{basename}"])
    assert index == {}
    assert basename in unparsed


def test_main_warns_on_unparsed_filenames(monkeypatch, capsys):
    monkeypatch.setattr(
        check_ieee_adoption, "fetch_schema_paths",
        lambda project, ref, path=check_ieee_adoption.DEFAULT_PATH: [
            "schemas/physical_activity/physical-activity-1.0.json",
            "schemas/sleep/sleep-episode-1.0.json",
            "schemas/heart_rate/heart-rate-1.0.1.json",
        ],
    )
    status = check_ieee_adoption.main(["--ref", "1.0.2"])
    assert status == 0
    captured = capsys.readouterr()
    # stderr, like every other warning in this tool — stdout is reserved for --json's artifact.
    assert "::warning::" in captured.err
    assert "heart-rate-1.0.1.json" in captured.err
    assert "heart-rate-1.0.1.json" not in captured.out


def test_main_json_stdout_stays_pure_json_when_filenames_are_unparsed(monkeypatch, capsys):
    # NEW BREAKAGE 1: schema-drift.yml pipes --json's stdout straight into json.load(). A
    # warning leaking onto stdout there corrupts the artifact and kills the workflow step.
    monkeypatch.setattr(
        check_ieee_adoption, "fetch_schema_paths",
        lambda project, ref, path=check_ieee_adoption.DEFAULT_PATH: [
            "schemas/physical_activity/physical-activity-1.0.json",
            "schemas/sleep/sleep-episode-1.0.json",
            "schemas/heart_rate/heart-rate-1.0.1.json",
        ],
    )
    status = check_ieee_adoption.main(["--ref", "1.0.2", "--json"])
    assert status == 0
    captured = capsys.readouterr()
    findings = json.loads(captured.out)  # raises if the warning leaked onto stdout
    assert findings == []
    assert "::warning::" in captured.err
    assert "heart-rate-1.0.1.json" in captured.err
    assert "heart-rate-1.0.1.json" not in captured.out


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


def test_find_findings_raises_on_unparseable_current_version():
    schema_ids = {"heart_rate": "ieee:heart-rate:1.0-rc1"}
    index = {"heart-rate": {"1.0"}}
    with pytest.raises(RuntimeError, match="unparseable version"):
        check_ieee_adoption.find_findings(index, schema_ids)


def test_main_routes_unparseable_version_through_warning_path(monkeypatch, capsys):
    # heart-rate is present in the fetched index (so the finding-1 canary check passes) but the
    # patched SCHEMA_IDS entry has a version find_findings can't parse — that must still surface
    # as a ::warning:: exit, not an uncaught traceback.
    monkeypatch.setattr(
        check_ieee_adoption, "fetch_schema_paths",
        lambda project, ref, path=check_ieee_adoption.DEFAULT_PATH: [
            "schemas/physical_activity/physical-activity-1.0.json",
            "schemas/sleep/sleep-episode-1.0.json",
            "schemas/heart_rate/heart-rate-1.0.json",
        ],
    )
    monkeypatch.setattr(check_ieee_adoption, "SCHEMA_IDS", {**SCHEMA_IDS, "heart_rate": "ieee:heart-rate:1.0-rc1"})
    status = check_ieee_adoption.main(["--ref", "1.0.2"])
    assert status == 1
    assert "::warning::" in capsys.readouterr().err


# --- no finding when IEEE doesn't publish the measure ---


def test_find_findings_no_finding_for_unpublished_measure():
    index = {"some-other-measure": {"1.0"}}
    assert check_ieee_adoption.find_findings(index, SCHEMA_IDS) == []


# --- missing_canaries: finding 1 — a wrong/renamed path must not read as "all clear" ---


def test_missing_canaries_empty_when_ieee_resolved_types_are_present():
    index = {"physical-activity": {"1.0"}, "sleep-episode": {"1.0"}}
    assert check_ieee_adoption.missing_canaries(index, SCHEMA_IDS) == []


def test_missing_canaries_flags_absent_ieee_resolved_measure():
    # sleep-episode is missing even though sleep_episode already resolves to ieee:sleep-episode:1.0.
    index = {"physical-activity": {"1.0"}}
    assert check_ieee_adoption.missing_canaries(index, SCHEMA_IDS) == ["sleep-episode"]


def test_missing_canaries_flags_all_when_index_is_empty():
    assert sorted(check_ieee_adoption.missing_canaries({}, SCHEMA_IDS)) == [
        "physical-activity", "sleep-episode",
    ]


def test_main_errors_on_empty_index_instead_of_reporting_no_findings(monkeypatch, capsys):
    # Simulates a renamed/missing 'schemas/' path: GitLab answers HTTP 200 with an empty list.
    monkeypatch.setattr(
        check_ieee_adoption, "fetch_schema_paths",
        lambda project, ref, path=check_ieee_adoption.DEFAULT_PATH: [],
    )
    status = check_ieee_adoption.main(["--ref", "1.0.2"])
    assert status == 1
    captured = capsys.readouterr()
    assert "::warning::" in captured.err
    assert "No findings" not in captured.out
    assert "No findings" not in captured.err


def test_main_errors_when_canary_measures_missing(monkeypatch, capsys):
    # Path fetch "succeeds" but only returns unrelated measures — sleep-episode/physical-activity
    # (already vendored from this project+ref) are absent, so the fetch itself is suspect.
    monkeypatch.setattr(
        check_ieee_adoption, "fetch_schema_paths",
        lambda project, ref, path=check_ieee_adoption.DEFAULT_PATH: [
            "schemas/environment/ambient-light-1.0.json",
        ],
    )
    status = check_ieee_adoption.main(["--ref", "1.0.2"])
    assert status == 1
    captured = capsys.readouterr()
    assert "sleep-episode" in captured.err
    assert "physical-activity" in captured.err
    assert "No findings" not in captured.out


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
    responses = {
        1: [
            {"type": "blob", "path": "schemas/sleep/sleep-episode-1.0.json"},
            {"type": "tree", "path": "schemas/sleep"},
            {"type": "blob", "path": "schemas/README.md"},
        ],
        2: [],
    }
    requested_pages: list[int] = []

    def fake_urlopen(req):
        page = int(re.search(r"[?&]page=(\d+)", req.full_url).group(1))
        requested_pages.append(page)
        return _FakeResponse(json.dumps(responses[page]).encode())

    monkeypatch.setattr(check_ieee_adoption.urllib.request, "urlopen", fake_urlopen)
    paths = check_ieee_adoption.fetch_schema_paths("omh%2F1752", "1.0.2")
    assert paths == ["schemas/sleep/sleep-episode-1.0.json"]
    # Proves each request actually asked for the next page — a fixed page=1 implementation
    # (which would still pass a naive test popping a canned list) would fail this.
    assert requested_pages == [1, 2]


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


def test_fetch_schema_paths_raises_when_page_cap_exceeded(monkeypatch):
    # An API that ignores '?page=' and always returns the same non-empty page must not loop forever.
    monkeypatch.setattr(
        check_ieee_adoption.urllib.request, "urlopen",
        lambda req: _FakeResponse(json.dumps(
            [{"type": "blob", "path": "schemas/x/y-1.0.json"}]
        ).encode()),
    )
    with pytest.raises(RuntimeError, match="exceeded"):
        check_ieee_adoption.fetch_schema_paths("omh%2F1752", "1.0.2")


# --- main(): exit codes ---


def test_main_returns_zero_with_findings_and_reports_them(monkeypatch):
    monkeypatch.setattr(
        check_ieee_adoption, "fetch_schema_paths",
        lambda project, ref, path=check_ieee_adoption.DEFAULT_PATH: [
            "schemas/physical_activity/physical-activity-1.0.json",
            "schemas/sleep/sleep-episode-1.0.json",
            "schemas/heart_rate/heart-rate-1.0.json",
        ],
    )
    buf = io.StringIO()
    with redirect_stdout(buf):
        status = check_ieee_adoption.main(["--ref", "1.0.2", "--json"])
    assert status == 0
    findings = json.loads(buf.getvalue())
    assert findings == [
        {"data_type": "heart_rate", "measure": "heart-rate", "kind": "ADOPT",
         "versions": ["1.0"], "current": "omh:heart-rate:2.0"},
    ]


def test_main_returns_nonzero_on_fetch_failure(monkeypatch, capsys):
    def fake_fetch(project, ref, path=check_ieee_adoption.DEFAULT_PATH):
        raise RuntimeError("network is down")

    monkeypatch.setattr(check_ieee_adoption, "fetch_schema_paths", fake_fetch)
    assert check_ieee_adoption.main(["--ref", "1.0.2"]) == 1
    assert "network is down" in capsys.readouterr().err

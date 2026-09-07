#!/usr/bin/env python3
"""Check whether IEEE 1752.1 has published measures omh-shim still resolves to OMH,
or newer versions of measures it already resolves to IEEE.

Scoped to stable IEEE 1752.1 (``omh/1752``) only — ``omh/1752-2``'s draft metabolic
schemas live on an unmerged branch, and watching drafts would churn every commit.

The check is mechanical, not a judgment call: ``omh_shim._SCHEMA_CANDIDATES`` is
enforced at import to have each candidate's measure name equal
``data_type.replace("_", "-")`` (the no-inference rule), so IEEE coverage is a plain
dictionary lookup keyed by that same name.

Run from the repo root::

    python tools/check_ieee_adoption.py                  # check against the pinned IEEE ref
    python tools/check_ieee_adoption.py --ref 1.0.3       # check a different ref
    python tools/check_ieee_adoption.py --json            # machine-readable output

Exit 0 whether or not findings were reported — findings are informational, not a
build failure. Exit non-zero only when the check itself could not run (a network
failure, an unparseable IEEE response, or a fetch that fails the canary sanity
check below).

Standard library only — no extra deps.
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from refresh_schemas import PINNED_PATH, USER_AGENT, read_pinned  # noqa: E402

from omh_shim import SCHEMA_IDS  # noqa: E402

IEEE_API_BASE = "https://opensource.ieee.org/api/v4"
DEFAULT_PROJECT = "omh%2F1752"
DEFAULT_PATH = "schemas"
MAX_PAGES = 50  # a well-behaved API pages in single digits; this only guards against one that ignores ?page=

_MEASURE_RE = re.compile(r"^(?P<name>.+)-(?P<ver>\d+\.\d+)\.json$")


class Finding(NamedTuple):
    data_type: str
    measure: str
    kind: str  # "ADOPT" or "NEWER"
    versions: tuple[str, ...]
    current: str


def _parse_version(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError as e:
        raise RuntimeError(f"unparseable version segment in {version!r}: {e}") from e


def build_measure_index(paths: list[str]) -> tuple[dict[str, set[str]], list[str]]:
    """Measure name -> versions, from schemas/**.json paths. Skips metadata/ and utility/.

    Also returns the basenames the version regex didn't match, so a naming scheme it
    doesn't anticipate (e.g. a three-segment version, or a non-numeric one) becomes a
    visible warning instead of a silently dropped measure.
    """
    index: dict[str, set[str]] = {}
    unparsed: list[str] = []
    for path in paths:
        rel = path.removeprefix("schemas/")
        if rel.startswith(("metadata/", "utility/")):
            continue
        basename = rel.rsplit("/", 1)[-1]
        match = _MEASURE_RE.match(basename)
        if not match:
            unparsed.append(basename)
            continue
        index.setdefault(match.group("name"), set()).add(match.group("ver"))
    return index, unparsed


def missing_canaries(index: Mapping[str, set[str]], schema_ids: Mapping[str, str]) -> list[str]:
    """Canary measures already resolved to an ``ieee:`` id that are absent from ``index``.

    Every such data type was vendored from this exact IEEE project+ref (see
    ``tools/refresh_schemas.py``'s ``IEEE_DATA_TARGETS``), so its absence means the
    fetch or the ``schemas/`` path is wrong — not that IEEE deleted a published
    measure. A non-empty result means the index cannot be trusted. Pure, no network.
    """
    canaries = {dt.replace("_", "-") for dt, current in schema_ids.items() if current.startswith("ieee:")}
    return sorted(m for m in canaries if m not in index)


def find_findings(index: Mapping[str, set[str]], schema_ids: Mapping[str, str]) -> list[Finding]:
    """Pure. Returns ADOPT/NEWER findings; empty when the table is current."""
    findings: list[Finding] = []
    for data_type, current in schema_ids.items():
        measure = data_type.replace("_", "-")
        versions = index.get(measure)
        if not versions:
            continue
        sorted_versions = tuple(sorted(versions, key=_parse_version))
        if not current.startswith("ieee:"):
            findings.append(Finding(data_type, measure, "ADOPT", sorted_versions, current))
            continue
        current_version = current.rsplit(":", 1)[-1]
        newest = max(versions, key=_parse_version)
        if _parse_version(newest) > _parse_version(current_version):
            findings.append(Finding(data_type, measure, "NEWER", sorted_versions, current))
    return findings


def fetch_schema_paths(project: str, ref: str, *, path: str = DEFAULT_PATH) -> list[str]:
    """Page the GitLab tree API for every ``{path}/**.json`` blob path at ref."""
    paths: list[str] = []
    page = 1
    while True:
        if page > MAX_PAGES:
            raise RuntimeError(
                f"exceeded {MAX_PAGES} pages fetching the '{path}' tree for {project}@{ref} "
                f"— the API may not be honoring '?page='"
            )
        url = (
            f"{IEEE_API_BASE}/projects/{project}/repository/tree"
            f"?ref={ref}&path={path}&recursive=true&per_page=100&page={page}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req) as resp:
                text = resp.read().decode("utf-8")
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            raise RuntimeError(f"request failed for {url}: {e}") from e
        try:
            entries = json.loads(text)
        except json.JSONDecodeError as e:
            # A WAF challenge answers 200 with HTML; refuse to treat it as a tree listing.
            raise RuntimeError(f"non-JSON response from {url}: {text[:200]!r}") from e
        if not entries:
            break
        paths.extend(
            entry["path"] for entry in entries
            if entry.get("type") == "blob" and entry["path"].endswith(".json")
        )
        page += 1
    return paths


def _print_table(
    findings: list[Finding], index: Mapping[str, set[str]], schema_ids: Mapping[str, str]
) -> None:
    findings_by_type = {f.data_type: f for f in findings}
    header = f"{'data_type':<20} {'resolved id':<28} {'ieee versions':<18} verdict"
    print(header)
    print("-" * len(header))
    for data_type, current in sorted(schema_ids.items()):
        measure = data_type.replace("_", "-")
        versions = ", ".join(sorted(index.get(measure, set()), key=_parse_version)) or "-"
        finding = findings_by_type.get(data_type)
        verdict = finding.kind if finding else "ok"
        print(f"{data_type:<20} {current:<28} {versions:<18} {verdict}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check IEEE 1752.1 for measures omh-shim doesn't yet resolve to it."
    )
    parser.add_argument("--project", default=DEFAULT_PROJECT, help="IEEE GitLab project id (URL-encoded).")
    parser.add_argument("--ref", help="IEEE ref to check. Defaults to the pinned ref in _pinned.json.")
    parser.add_argument(
        "--path", default=DEFAULT_PATH,
        help=f"Tree path to fetch (default {DEFAULT_PATH!r}). For debugging path-drift only.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON instead of a table.")
    args = parser.parse_args(argv)

    ref = args.ref or read_pinned(PINNED_PATH, family="ieee")

    try:
        paths = fetch_schema_paths(args.project, ref, path=args.path)
    except RuntimeError as e:
        print(f"::warning::check_ieee_adoption could not run: {e}", file=sys.stderr)
        return 1

    index, unparsed = build_measure_index(paths)

    missing = missing_canaries(index, SCHEMA_IDS)
    if missing or not index:
        tree_url = (
            f"{IEEE_API_BASE}/projects/{args.project}/repository/tree"
            f"?ref={ref}&path={args.path}&recursive=true&per_page=100"
        )
        if not index:
            reason = "the fetched index is completely empty"
        else:
            reason = f"canary measure(s) already vendored from this project+ref are missing: {missing}"
        print(
            f"::warning::check_ieee_adoption could not run: {reason} — "
            f"the '{args.path}' path is likely wrong for {args.project}@{ref}. URL: {tree_url}",
            file=sys.stderr,
        )
        return 1

    if unparsed:
        print(
            f"::warning::check_ieee_adoption: {len(unparsed)} schema filename(s) did not match "
            f"the '<name>-<major>.<minor>.json' pattern and were skipped: {sorted(unparsed)}"
        )

    try:
        findings = find_findings(index, SCHEMA_IDS)
    except RuntimeError as e:
        print(f"::warning::check_ieee_adoption could not run: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps([f._asdict() for f in findings], indent=2))
    else:
        print(f"IEEE {args.project} @ {ref}")
        print()
        _print_table(findings, index, SCHEMA_IDS)
        print()
        if findings:
            print(f"{len(findings)} finding(s):")
            for f in findings:
                if f.kind == "ADOPT":
                    print(f"  ADOPT {f.data_type}: IEEE now publishes {f.measure} "
                          f"({', '.join(f.versions)}); currently resolved to {f.current}")
                else:
                    print(f"  NEWER {f.data_type}: IEEE publishes {f.measure} "
                          f"({', '.join(f.versions)}) newer than resolved {f.current}")
        else:
            print("No findings. The candidate table is current with IEEE.")

    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Authoritative, offline Plex advisory core, also vendored by Quickstart.

No application imports or network access. Edit this source in Logscan, then
run Quickstart's scripts/sync_plex_security.py against the committed checkout.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from collections.abc import Iterable
import re

_VERSION = re.compile(r"([0-9]+)\.([0-9]+)\.([0-9]+)\.([0-9]+)(?:-[0-9a-fA-F]+)?", re.ASCII)
_CONNECTION = re.compile(r"Connected to server\s+(.+?)\s+(\()?\s*version\s*:?\s*(.*?)\s*$", re.I)
LEGACY_LOW = (1, 41, 7, 0)
LEGACY_HIGH = (1, 42, 0, 99999)


def parse_pms_version(value: object) -> tuple[int, int, int, int] | None:
    """Require four numeric components and, optionally, a hexadecimal hash."""
    if not isinstance(value, str) or not (match := _VERSION.fullmatch(value.strip())):
        return None
    try:
        return int(match[1]), int(match[2]), int(match[3]), int(match[4])
    except ValueError:
        return None


def legacy_affected(value: object) -> bool:
    version = parse_pms_version(value)
    return version is not None and LEGACY_LOW <= version <= LEGACY_HIGH


@dataclass(frozen=True)
class Advisory:
    advisory_id: str
    product: str
    recommendation_severity: str
    minimum_patched_version: str
    published_date: str
    advisory_url: str
    remediation: str
    severity_source: str = "Kometa recommendation; not an official CVSS rating"


ADVISORIES = (
    Advisory(
        "PLEX-PMS-2026-09",
        "Plex Media Server",
        "critical",
        "1.43.3.10861",
        "2026-09-01",
        "https://forums.plex.tv/t/important-security-update-for-plex-media-server-v1-43-2-and-earlier/942319/1",
        "Update Plex Media Server to 1.43.3.10861 or newer, then validate the connection again.",
    ),
)


def evaluate_advisories(value: object) -> list[dict]:
    version = parse_pms_version(value)
    normalized = ".".join(map(str, version)) if version is not None else None
    assessments = []
    for advisory in ADVISORIES:
        patched = parse_pms_version(advisory.minimum_patched_version)
        if patched is None:
            raise ValueError(f"Invalid patched version in advisory {advisory.advisory_id}")
        assessments.append(
            {
                **asdict(advisory),
                "detected_version": value if isinstance(value, str) else None,
                "normalized_version": normalized,
                "status": "unknown" if version is None else "affected" if version < patched else "patched",
                "legacy_vulnerability_affected": legacy_affected(value),
            }
        )
    return assessments


def server_observation(line: str) -> tuple[str, str] | None:
    """Extract the entire version field, so malformed suffixes stay unknown."""
    # Kometa frames messages with a trailing pipe, and sometimes parentheses.
    message = line.rstrip().removesuffix("|").rstrip()
    match = _CONNECTION.search(message)
    if not match:
        return None
    server, opening, version = match.groups()
    return server.strip(), (version.removesuffix(")") if opening else version).strip()


def assess_log(lines: Iterable[tuple[int, str]], evidence_limit: int = 10_000) -> list[dict]:
    """Assess numbered candidate lines; one assessment per server/advisory.

    Any affected historical observation retains an affected assessment even
    if a later run is patched. Occurrence counts continue beyond evidence caps.
    Server names are the available identity; unnamed/missing versions are unknown.
    """
    groups: dict[tuple[str, str], dict] = {}
    observations: dict[tuple[str, str, str], dict] = {}
    for number, line in lines:
        observation = server_observation(line)
        if observation is None:
            continue
        server, raw = observation
        for assessment in evaluate_advisories(raw):
            key = (server, assessment["advisory_id"])
            if key not in groups:
                groups[key] = {
                    **assessment,
                    "server_name": server,
                    "source": "observed_in_log",
                    "observations": [],
                    "evidence_lines": [],
                    "occurrence_count": 0,
                    "evidence_truncated": False,
                }
            group = groups[key]
            group["occurrence_count"] += 1
            if len(group["evidence_lines"]) < evidence_limit:
                group["evidence_lines"].append(number)
            else:
                group["evidence_truncated"] = True
            if assessment["status"] == "affected" or group["status"] == "affected":
                group["status"] = "affected"
            elif assessment["status"] == "unknown" or group["status"] == "unknown":
                group["status"] = "unknown"
            group["legacy_vulnerability_affected"] |= assessment["legacy_vulnerability_affected"]
            # Keep version-specific traceability without copying every repeated line.
            entry = observations.get((*key, raw))
            if entry is None:
                entry = {k: assessment[k] for k in ("detected_version", "normalized_version", "status")}
                entry.update(evidence_lines=[], occurrence_count=0)
                group["observations"].append(entry)
                observations[(*key, raw)] = entry
            entry["occurrence_count"] += 1
            if len(entry["evidence_lines"]) < evidence_limit:
                entry["evidence_lines"].append(number)
    if not groups:
        return [
            dict(item, server_name=None, source="observed_in_log", observations=[], evidence_lines=[], occurrence_count=0, evidence_truncated=False)
            for item in evaluate_advisories(None)
        ]
    return list(groups.values())


def assessment_message(assessment: dict) -> str:
    """Plain text/Markdown accepted by both existing recommendation renderers."""
    server = assessment.get("server_name") or "Unknown server"
    versions = ", ".join(repr(item["detected_version"]) for item in assessment.get("observations", [])) or "unavailable"
    status = assessment["status"]
    title = "Plex Media Server security update required" if status == "affected" else f"Plex advisory assessment: {status}"
    return (
        f"{title}\nAdvisory: {assessment['advisory_id']}\n"
        f"Server: {server}\nVersion(s) observed in this log: {versions}\n"
        "This historical log does not establish the server's current version.\n"
        f"Minimum patched version: {assessment['minimum_patched_version']}\n"
        f"Kometa advisory priority: {assessment['recommendation_severity'].capitalize()} ({assessment['severity_source']}).\n"
        f"Proposed solution: {assessment['remediation'] if status == 'affected' else 'Validate the current server version to assess this advisory.'}\n"
        f"Official Plex advisory: {assessment['advisory_url']}"
    )

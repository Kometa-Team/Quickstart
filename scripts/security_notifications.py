"""Track urgent production advisories in a private GitHub repository only.

No dependency installation, public outputs, alert dismissal or production writes.
Unknown manifests/ranges remain open for review, never falsely marked resolved.
"""

from __future__ import annotations

import base64
import json
import os
import re
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class GitHub:
    def __init__(self, token):
        if not token:
            raise RuntimeError("Missing security notification credential")
        self.token = token

    def request(self, path, method="GET", body=None):
        request = Request(
            "https://api.github.com/" + path,
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json", "Content-Type": "application/json", "X-GitHub-Api-Version": "2022-11-28"},
        )
        with urlopen(request, timeout=30) as response:
            return json.load(response)

    def pages(self, path):
        result = []
        for page in range(1, 101):
            batch = self.request(path + ("&" if "?" in path else "?") + f"per_page=100&page={page}")
            result.extend(batch)
            if len(batch) < 100:
                return result
        raise RuntimeError("Security pagination incomplete")


def numeric(value):
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){0,3}", value):
        raise ValueError("Version needs manual review")
    values = tuple(map(int, value.split(".")))
    return values + (0,) * (4 - len(values))


def vulnerable(value, affected_range):
    try:
        installed = numeric(value)
        conditions = []
        for clause in affected_range.split(","):
            match = re.fullmatch(r"\s*(>=|<=|==|=|>|<)\s*([0-9]+(?:\.[0-9]+){0,3})\s*", clause)
            if not match:
                return None
            comparator, limit = match.groups()
            boundary = numeric(limit)
            conditions.append(
                {
                    ">=": installed >= boundary,
                    "<=": installed <= boundary,
                    "==": installed == boundary,
                    "=": installed == boundary,
                    ">": installed > boundary,
                    "<": installed < boundary,
                }[comparator]
            )
        return all(conditions)
    except ValueError:
        return None


def versions(text, path, ecosystem, package):
    if ecosystem == "npm" and path == "package-lock.json":
        packages = json.loads(text).get("packages")
        if not isinstance(packages, dict):
            return None
        return [info["version"] for name, info in packages.items() if name.endswith("node_modules/" + package) and "version" in info]
    if ecosystem == "pip" and re.fullmatch(r"requirements[^/]*\.txt", path):

        def canonical(name):
            return re.sub(r"[-_.]+", "-", name).lower()

        result = []
        for line in text.splitlines():
            match = re.match(r"\s*([A-Za-z0-9_.-]+)(?:\[[^]]+\])?==([^\s;]+)", line)
            if match and canonical(match[1]) == canonical(package):
                result.append(match[2])
        # Requirements do not describe every installed transitive package.
        # Absence here cannot establish absence from the production environment.
        return result or None
    return None


def affected(installed, affected_range):
    if installed is None:
        return None
    states = [vulnerable(value, affected_range) for value in installed]
    if True in states:
        return True
    return None if None in states else False


def notification(alert, production, integration, fix_prs):
    vulnerability = alert["security_vulnerability"]
    package = alert["dependency"]["package"]["name"]
    severity = vulnerability["severity"].lower()
    prod = affected(production, vulnerability["vulnerable_version_range"])
    dev = affected(integration, vulnerability["vulnerable_version_range"])
    if prod is False:
        status, closed = "Released to master: production dependency is verified outside the vulnerable range.", True
    elif prod is True and dev is False:
        status, closed = "URGENT: fix exists in develop but has NOT reached production. Perform a reviewed Master Release.", False
    elif prod is True:
        status, closed = "Production remains vulnerable; fix pending.", False
    else:
        status, closed = "Production applicability requires manual review; unsupported version range or dependency manifest. Do not treat this alert as resolved.", False
    advisory = alert["security_advisory"].get("ghsa_id", "Security advisory")
    body = "\n".join(
        [
            f"<!-- quickstart-production-alert:{alert['number']} -->",
            f"{severity.upper()}: {package}",
            status,
            f"Advisory: https://github.com/advisories/{advisory}",
            f"Dependabot alert: {alert['html_url']}",
            f"Affected range: {vulnerability['vulnerable_version_range']}",
            f"master versions: {', '.join(production) if production is not None else 'unverified'}",
            f"develop versions: {', '.join(integration) if integration is not None else 'unverified'}",
            "Fix PRs (candidate fixes verified outside the affected range): " + (", ".join(fix_prs) or "none identified"),
            "No automatic production promotion or alert dismissal is performed.",
        ]
    )
    return {"title": f"[{severity.upper()}] Production dependency: {package}", "body": body, "state": "closed" if closed else "open"}


def synchronize(reader, writer, source, tracker):
    for repository in (source, tracker):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise RuntimeError("Invalid repository setting")
    # Never send security data to a public tracker, even when the advisory seems public.
    if writer.request(f"repos/{tracker}").get("visibility") != "private":
        raise RuntimeError("Security notification tracker must be private")
    metadata = reader.request(f"repos/{source}")
    if metadata["default_branch"] != "master":
        raise RuntimeError("Production default branch changed; reassess alert applicability")
    heads = {branch: reader.request(f"repos/{source}/git/ref/heads/{branch}")["object"]["sha"] for branch in ("master", "develop")}
    alerts = []
    for state in ("open", "fixed", "dismissed"):
        alerts.extend(reader.pages(f"repos/{source}/dependabot/alerts?state={state}&severity=high,critical"))
    issues = writer.pages(f"repos/{tracker}/issues?state=all")
    cache = {}

    def installed(commit, alert):
        dependency = alert["dependency"]
        path = dependency["manifest_path"]
        if path == "package.json":
            path = "package-lock.json"
        if path != "package-lock.json" and not re.fullmatch(r"requirements[^/]*\.txt", path):
            return None
        key = (commit, path)
        if key not in cache:
            try:
                data = reader.request(f"repos/{source}/contents/{path}?ref={commit}")
            except HTTPError as error:
                if error.code == 404:
                    return None
                raise
            cache[key] = base64.b64decode(data["content"]).decode("utf-8")
        return versions(cache[key], path, dependency["package"]["ecosystem"], dependency["package"]["name"])

    for alert in alerts:
        if alert["security_vulnerability"]["severity"].lower() not in ("high", "critical"):
            continue
        production, integration = (installed(heads[branch], alert) for branch in ("master", "develop"))
        query = urlencode({"q": f"repo:{source} is:pr author:app/dependabot {alert['dependency']['package']['name']}", "per_page": 100})
        search = reader.request("search/issues?" + query)
        fix_prs = []
        for hit in search["items"]:
            pr = reader.request(f"repos/{source}/pulls/{hit['number']}")
            if pr["user"]["login"] == "dependabot[bot]" and affected(installed(pr["head"]["sha"], alert), alert["security_vulnerability"]["vulnerable_version_range"]) is False:
                fix_prs.append(f"{pr['html_url']} ({'merged into ' + pr['base']['ref'] if pr.get('merged_at') else pr['state']})")
        desired = notification(alert, production, integration, sorted(fix_prs))
        marker = f"<!-- quickstart-production-alert:{alert['number']} -->"
        matching = [issue for issue in issues if marker in (issue.get("body") or "")]
        if len(matching) > 1:
            raise RuntimeError("Duplicate private notifications need manual review")
        if matching:
            existing = matching[0]
            if any(existing.get(key) != value for key, value in desired.items()):
                writer.request(f"repos/{tracker}/issues/{existing['number']}", "PATCH", desired)
        elif desired["state"] == "open":
            writer.request(f"repos/{tracker}/issues", "POST", {key: value for key, value in desired.items() if key != "state"})


if __name__ == "__main__":
    try:
        synchronize(
            GitHub(os.environ["SECURITY_ALERTS_READ_TOKEN"]),
            GitHub(os.environ["SECURITY_TRACKER_WRITE_TOKEN"]),
            os.environ["GITHUB_REPOSITORY"],
            os.environ["SECURITY_TRACKER_REPOSITORY"],
        )
    except Exception:
        # HTTP errors and advisory payloads must never appear in public run logs.
        raise SystemExit("Security monitoring could not complete. An authorized maintainer must inspect its private configuration; no alert was assumed resolved.") from None

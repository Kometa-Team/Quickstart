#!/usr/bin/env python3
"""Forward-only release publication. Builds run elsewhere without these credentials."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

try:
    from scripts import release
except ModuleNotFoundError:
    import release

ARCHES = ("amd64", "arm64", "armv7")
REVISION = "org.opencontainers.image.revision"


def sha(value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("An exact approved commit SHA is required")
    return value


def environment_gate(repository: str, environment: str) -> None:
    data = release.api(f"repos/{repository}/environments/{environment}")[0]
    reviewers = [rule for rule in data["protection_rules"] if rule["type"] == "required_reviewers"]
    if not reviewers or not reviewers[0].get("reviewers") or not reviewers[0].get("prevent_self_review") or data.get("can_admins_bypass") is not False:
        raise RuntimeError("Administrator must configure required independent reviewers and disable environment admin bypass.")


def verify(repository: str, remote: str, approved: str) -> str:
    sha(approved)
    release.verify_remote(repository, remote)
    if release.git("rev-parse", "HEAD") != approved or release.git("status", "--porcelain"):
        raise RuntimeError("Publication requires the clean approved checkout")
    target, build = release.metadata(approved)
    release.version(target)
    if build != "0":
        raise RuntimeError("Stable publication requires BUILDNUM=0")
    if release.remote_refs(remote, f"refs/heads/release-candidates/{target}").get(f"refs/heads/release-candidates/{target}") != approved:
        raise RuntimeError("Published candidate is missing or approval is stale")
    tag, existing = release.release_tag(remote, target, approved)
    heads = release.snapshot(remote)
    # Initial tagging needs a fully completed promotion. After tagging, develop
    # may integrate new PRs; master and hotfix must still identify this release.
    if heads["master"] != approved or heads["hotfix"] != approved:
        raise RuntimeError("Incomplete or stale promotion")
    if existing == "0" * 40 and heads["develop"] != approved:
        raise RuntimeError("Missing tag requires all three branches at the approved SHA")
    if not release.ancestor(approved, heads["develop"]):
        raise RuntimeError("Develop no longer contains the approved release")
    release.check_protection(repository, approved)
    return tag.removeprefix("refs/tags/")


def ensure_tag(repository: str, remote: str, approved: str) -> str:
    tag = verify(repository, remote, approved)
    ref, old = release.release_tag(remote, tag[1:], approved)
    if old == "0" * 40:
        release.verify_remote(repository, remote)
        release.guarded_push(remote, {ref: old}, {ref: approved})
    if release.release_tag(remote, tag[1:], approved)[1] == "0" * 40:
        raise RuntimeError("Tag creation was not confirmed")
    return tag


def gh_json(repository: str, path: str, method: str = "GET", body: dict | None = None):
    # Structured JSON and fixed API paths: no user-controlled shell evaluation.
    args = ["gh", "api", f"repos/{repository}/{path}", "--method", method]
    if body is not None:
        args += ["--input", "-"]
    result = subprocess.run(args, input=json.dumps(body) if body is not None else None, text=True, capture_output=True)
    if result.returncode:
        if method == "GET" and "HTTP 404" in result.stderr:
            return None
        raise RuntimeError(f"GitHub {method} {path} failed: {result.stderr}")
    return json.loads(result.stdout) if result.stdout.strip() else None


def ensure_release(repository: str, tag: str, approved: str) -> dict:
    existing = gh_json(repository, f"releases/tags/{quote(tag, safe='')}")
    if existing is None:
        # A draft prevents notification of an incomplete set of assets/images.
        existing = gh_json(
            repository,
            "releases",
            "POST",
            {"tag_name": tag, "target_commitish": approved, "name": f"Quickstart {tag}", "body": f"Approved source: {approved}", "draft": True, "prerelease": False},
        )
    if existing["tag_name"] != tag or existing.get("prerelease") or existing.get("target_commitish") != approved:
        raise RuntimeError("Existing release identity conflicts; preserve it and request manual review")
    return existing


def upload_assets(repository: str, info: dict, directory: Path) -> None:
    files = sorted(directory.glob("Quickstart-*"))
    expected = ("-Windows.exe", "-Linux", "-macOS-x86_64", "-macOS-arm64")
    if len(files) != 4 or not all(any(file.name == f"Quickstart-{info['tag_name']}{suffix}" for file in files) for suffix in expected):
        raise RuntimeError("Exactly the four expected executable assets are required")
    current = {asset["name"]: asset for asset in gh_json(repository, f"releases/{info['id']}/assets?per_page=100")}
    for file in files:
        digest = "sha256:" + hashlib.sha256(file.read_bytes()).hexdigest()
        asset = current.get(file.name)
        if asset:
            # Reruns must use the original artifacts, not rebuild different bytes
            # under an existing filename. Unknown digests fail closed as well.
            if asset.get("state") != "uploaded" or asset.get("digest") != digest or asset.get("size") != file.stat().st_size:
                raise RuntimeError(f"Existing asset {file.name} differs or is incomplete; never overwrite it")
            continue
        if not info["draft"]:
            raise RuntimeError("Published release has missing assets; manual review required")
        release.run("gh", "release", "upload", info["tag_name"], str(file), "--repo", repository)
        uploaded = gh_json(repository, f"releases/{info['id']}/assets?per_page=100")
        if not any(a["name"] == file.name and a.get("digest") == digest and a.get("state") == "uploaded" for a in uploaded):
            raise RuntimeError("Uploaded asset digest was not confirmed; retry with the same artifact set")


class Registry:
    """Docker Hub read inspection. Only HTTP 404 is considered absent."""

    def __init__(self, image: str):
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*/[a-z0-9][a-z0-9_.-]*", image):
            raise ValueError("Unexpected registry repository")
        self.image = image

    def inspect(self, tag: str) -> dict | None:
        token_url = f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{self.image}:pull"
        with urlopen(token_url, timeout=30) as response:
            token = json.load(response)["token"]
        request = Request(
            f"https://registry-1.docker.io/v2/{self.image}/manifests/{tag}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json"},
        )
        try:
            with urlopen(request, timeout=30) as response:
                result = json.load(response)
                result["digest"] = response.headers["Docker-Content-Digest"]
                return result
        except HTTPError as error:
            if error.code == 404:
                return None
            raise

    def assemble(self, tag: str, sources: list[str], approved: str) -> None:
        release.run("docker", "buildx", "imagetools", "create", "--annotation", f"index:{REVISION}={approved}", "--tag", f"{self.image}:{tag}", *sources)


def verified_image(image: dict | None, approved: str) -> str:
    if not image or image.get("annotations", {}).get(REVISION) != approved:
        raise RuntimeError("Published version image conflicts; never overwrite it")
    platforms = [entry.get("platform", {}) for entry in image.get("manifests", [])]
    if len(platforms) != 3 or {p.get("architecture") for p in platforms} != {"amd64", "arm64", "arm"} or any(p.get("os") != "linux" for p in platforms):
        raise RuntimeError("Published version image has unexpected platforms")
    if any(p.get("architecture") == "arm" and p.get("variant") != "v7" for p in platforms):
        raise RuntimeError("Published ARM image is not arm/v7")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image.get("digest", "")):
        raise RuntimeError("Published image digest is missing or invalid")
    return image["digest"]


def publish_images(registry: Registry, tag: str, approved: str, directory: Path, attempt: str, still_current) -> str:
    sha(approved)
    release.version(tag.removeprefix("v"))
    if not re.fullmatch(r"[1-9][0-9]*-[1-9][0-9]*", attempt):
        raise ValueError("Expected run ID and attempt")
    still_current()
    existing = registry.inspect(tag)
    if existing:
        digest = verified_image(existing, approved)
    else:
        components = []
        for arch in ARCHES:
            file = directory / f"image-{arch}.tar"
            if not file.is_file():
                raise RuntimeError(f"Missing read-only image artifact: {file.name}")
            release.run("docker", "load", "--input", str(file))
            local = f"quickstart-build:{approved}-{arch}"
            revision = release.run("docker", "image", "inspect", local, "--format", '{{index .Config.Labels "org.opencontainers.image.revision"}}')
            if revision != approved:
                raise RuntimeError("Image artifact source label differs from approval")
            # No shared architecture tags, no deletion, no build in this job.
            component = f"{registry.image}:release-{approved}-{attempt}-{arch}"
            release.run("docker", "tag", local, component)
            release.run("docker", "push", component)
            components.append(component)
        still_current()
        # Reinspect after components: another publisher is never overwritten.
        existing = registry.inspect(tag)
        if existing:
            raise RuntimeError("Version image appeared during publication; retry inspection")
        registry.assemble(tag, components, approved)
        published = registry.inspect(tag)
        digest = verified_image(published, approved)
    for alias in ("latest", "develop"):
        if still_current(alias) is False:
            continue
        current = registry.inspect(alias)
        if not current or current.get("digest") != digest:
            registry.assemble(alias, [f"{registry.image}@{digest}"], approved)
            if registry.inspect(alias).get("digest") != digest:
                raise RuntimeError("Alias digest was not confirmed")
    return digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("verify", "tag", "images", "assets", "complete"))
    parser.add_argument("--approved-sha", required=True)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--image")
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--attempt", default="")
    args = parser.parse_args()
    tag = verify(args.repository, args.remote, args.approved_sha)
    if args.command == "verify":
        print(tag)
        return
    environment_gate(args.repository, "release-publication")
    if args.command == "tag":
        ensure_tag(args.repository, args.remote, args.approved_sha)
        return
    if release.release_tag(args.remote, tag[1:], args.approved_sha)[1] == "0" * 40:
        raise RuntimeError("Tag must be verified before external publication")
    if args.command == "images":

        def current(alias=None):
            heads = release.snapshot(args.remote)
            if heads["master"] != args.approved_sha or heads["hotfix"] != args.approved_sha:
                raise RuntimeError("Publication superseded by another release")
            return alias != "develop" or heads["develop"] == args.approved_sha

        publish_images(Registry(args.image), tag, args.approved_sha, args.directory, args.attempt, current)
    else:
        if args.command == "complete":
            verified_image(Registry(args.image).inspect(tag), args.approved_sha)
        info = ensure_release(args.repository, tag, args.approved_sha)
        upload_assets(args.repository, info, args.directory)
        if args.command == "complete" and info["draft"]:
            # No release delete, tag cleanup, prerelease replacement or clobber.
            gh_json(args.repository, f"releases/{info['id']}", "PATCH", {"draft": False})


if __name__ == "__main__":
    main()

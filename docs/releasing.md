# Release process

All application and dependency changes integrate through `develop`. `master` and
`hotfix` are release targets. Emergency fixes follow the same reviewed path through
`develop`; there is no automatic release when a hotfix PR closes.

## Prepare, review, promote

Run **Master Release** from `develop` with `stage=prepare`. Supply the starting
`base_version` and `release_type` (`major`, `minor`, or `patch`). Keep these inputs
unchanged on retries. The next version is calculated once from that fixed base,
never from an already incremented branch tip.

For an interrupted release that already has its version commit, choose
`release_type=resume` and set `base_version` to the existing release version. Resume
requires `BUILDNUM=0` and does not increment either file. For example, recovery of
0.10.15 uses `base_version=0.10.15` and `release_type=resume`.

Preparation snapshots all three remote heads, merges unique master and hotfix
commits into develop history using ordinary merges, and stops on conflicts. Resolve
conflicts in an isolated branch, review all dependency changes, and validate that
branch before publishing it. Never use an `ours` merge, force push, shared-branch
rebase, or history reset to reconcile a release.

The reconciled source and intended version files pass dependency installation,
dependency consistency and security audits, pre-commit, JavaScript tests, frontend
build and manifest checks, and the complete default Python test suite before the
release metadata commit is made. The default Python suite excludes browser E2E
tests, matching the repository test workflow. Container and platform executable
packaging are downstream workflows, not part of the default test gate.

Preparation publishes only `release-candidates/<version>` and opens a review PR
targeting develop. CI runs on the candidate SHA itself. Review the commit graph,
dependency resolution, complete validation results, and candidate SHA. Leave the
review PR open until atomic promotion; its purpose is review, not a squash merge.

After approval, rerun with the same version inputs, `stage=promote`, and the exact
`approved_sha`. The workflow revalidates that candidate, checks current effective
rules and required checks, and promotes it to develop, master, and hotfix in one
atomic fast-forward push. A changed head, changed candidate, conflict, unknown
rule, missing check, or rejected push stops promotion. Atomic pushes have no
sequential fallback. Git also rejects concurrent non-fast-forward updates at the
server. Normal writers share the `quickstart-release-writer` concurrency group.

## Retry and protection rules

The candidate ref is the durable retry record; retain it after promotion. Reusing
the same inputs reuses the exact commit, including after a legacy partial promotion
or a successful promotion whose workflow result was lost. A new release cannot
step over a previous version that has not reached both release targets.

If a branch acquires commits outside the published candidate, the workflow stops.
Preserve the candidate and branch histories, reconcile the new commits normally,
validate again, and obtain fresh approval for a replacement candidate. Do not
silently merge new changes into a previously approved release. Updating a candidate
must itself be a reviewed fast-forward; never replace its history.

The release App needs contents write and pull requests write to publish a candidate
and open its review PR, and metadata read to inspect rules/checks. Existing App
credentials allow downstream release/tag/container workflows to run when release
branches change. No protection bypass is required or requested. In this repository,
the active **Pull Request Validation** ruleset requires GitHub Actions `ci-status`
(integration 15368) on develop, master, and hotfix. It does not currently require
PR merges. Promotion verifies the latest successful required checks on the exact
candidate before pushing, even if the App has broader privileges.

The build-number workflow excludes release candidate review PRs. If GitHub marks
one merged after direct promotion, it must not increment BUILDNUM from zero.

If a new rule requires PRs, the workflow reports its type and full effective rule
and stops. Use reviewed normal merge PRs through develop, followed by release PRs
from develop to master and hotfix, without weakening rules. The normal CI guard
intentionally rejects application PRs to release branches: a maintainer must approve
a narrowly scoped release exception before enabling those PRs. Such PR merges
produce new commits and require new validation and approval; they cannot preserve
the single identical tip automatically. Do not claim atomic synchronization if the
configured protection rules prohibit it.

## Dependency updates

Dependabot version updates already specify `target-branch: develop`. GitHub security
updates use the repository default branch regardless of this option. While the
default branch remains master, **Route Dependency Updates** retargets Dependabot
PRs to develop using metadata only and never checks out their code. Retargeted
updates must pass normal develop CI. No bot PR may bypass the integration guard.

Reference: [GitHub's Dependabot target branch behavior](https://docs.github.com/en/code-security/tutorials/secure-your-dependencies/customizing-dependabot-prs).

A repository administrator may separately review changing the GitHub default branch
to develop, which routes security updates there at creation time. This is a settings
change with effects beyond dependency updates and is not performed by this repair.
The small existing `uv.lock` declares Python >=3.14 but contains no packages; current
runtime and CI dependencies are installed from requirements files on Python 3.13.
It is not a usable runtime lockfile. Replacing the dependency management system is
separate work; keep requirement updates flowing through develop in the meantime.

The retired hotfix workflow previously rebased and force-pushed develop. It now
provides instructions only. Copyright updates and build-number increments target
develop and share the release writer lock. The disabled legacy validate-pull
workflow remains manual; it is not an automatic integration route. The fork-PR
promotion workflow's force push targets temporary CI branches, not release branches.

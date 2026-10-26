# Release process

The normal route remains **develop → Master Release → master**. Master remains
the default branch. Dependency changes integrate through develop. Emergency fixes
use the same reviewed candidate path.

## History and hotfix baseline

The last successful Master Release was run 38343216447 on October 13, 2026.
It created 0.10.14 at 1bc389ff and sequentially pushed develop, master and hotfix.
The October 25 run 40186619705 used the same release logic, with only an App-action
version update. It committed 0.10.15 to develop, then failed because master had
three unique Dependabot commits (#1924, #1925, #1927). Sequential pushes left the
release incomplete. Neither a new version nor history replacement is needed.

The old CI also had a concrete enforcement gap: an unrelated label event skipped
guard, validation and tests, while ci-status accepted skipped jobs as successful.
All three dependency PR heads show an initial failed master guard followed by a
successful ci-status with the guard skipped. The new aggregator executes the guard
on every event and requires actual success for every mandatory job. A regression
runs the real Bash/jq gate against success, failure, cancellation and skipped-job
inputs. Windows contributors running these release tests need Git Bash and jq on
PATH; Ubuntu CI supplies both.

Legacy production Hotfix Release ran when any PR targeting hotfix closed, without
checking that it merged. It incremented hotfix's patch version, pushed hotfix to
master, rebased develop onto master, and force-pushed develop. Legacy Master
Release updated hotfix last so that its next emergency fix started at the stable
release. These behaviors are documented for history, not invoked by this repair.

The approved baseline is candidate 80e7b955. Its replacement Hotfix Release is
instruction-only: it does not change branches or release on PR closure. Master
Release still reconciles all three histories and atomically advances develop,
master and hotfix to the reviewed commit. **Phase 2 does not change that hotfix
workflow or synchronization model.** Do not restore the legacy hotfix workflow.

## Prepare, review and promote

Run Master Release on develop, stage=prepare, with a fixed base_version and
release_type (major, minor, patch, resume). Reuse those exact version inputs on
retry. Resume uses the existing version and requires BUILDNUM=0. Recovery uses
base_version=0.10.15 and release_type=resume; it never increments that version.

Preparation snapshots all three heads, performs ordinary merges of unique
commits, and stops on conflicts. Dependency installation, audits, pre-commit,
JavaScript tests, frontend build/manifest verification, the configured Python
suite and full-directory actionlint run with contents:read and no App token.
The configured Python suite excludes browser E2E, matching repository CI.
Validation must leave the prepared tree unchanged.

Candidate CI additionally builds all three Docker archives and all four executable
artifacts without write credentials. Its required ci-status includes these jobs;
failed, cancelled or skipped candidate builds block promotion. Ordinary integration
PRs may skip these candidate-only jobs, while their guard/tests/quality still must
succeed. Container and platform build validation therefore precede production
branch updates, even when the operator's local host cannot run those builders.

A separate job publishes the candidate and opens a draft develop PR. It runs no
dependency installation. Keep the review PR open; do not squash/rebase/merge it
as a substitute for identical-tip promotion. Review the graph, dependency fixes,
validation and exact SHA. Candidate changes require a reviewed descendant and
explicit previous-SHA approval; there is no automatic replacement.

Promotion revalidates the exact published SHA and uses the release-promotion
environment. Its stdlib-only job has explicit contents:write, no release App,
and no persisted checkout credentials. Git and protection queries use the same
GH_TOKEN identity. The helper refuses bypass-capable or unverifiable identities,
classic protection needing review, unsupported effective rules, failed/missing
checks, unexpected heads, changed metadata or a changed tree.

One non-forced atomic transaction advances all three branches and creates the
missing vVERSION tag at the approved SHA. Existing tags are resolved (including
annotated tags) and accepted only at that SHA. Tags are never moved. The guard
compares Git's advertised old IDs; the server then compares and swaps the updates.
No sequential fallback, reset or shared-history rebase is used.

An already completed promotion is a no-op retry. A legacy mixed partial promotion
with some branches already at the candidate needs a freshly reviewed descendant:
Git does not compare-and-swap no-op refs in a push. A new descendant makes all
three branch updates participate. Existing unique history must still be merged,
validated and approved; do not manufacture an unreviewed commit during promotion.

## Tags, images, releases and retries

Branch and tag pushes no longer start competing publication workflows. Master
Release prepare/failure never publishes Docker images. Tag New Version, Docker
Latest/Develop Build and Release Notification are instruction-only entry points.
The obsolete manual privileged PR formatter is retired.

After approved promotion, explicitly dispatch **Release Publication**
(docker-version.yml) on master with approved_sha equal to that ref's exact SHA.
A separately approved release-publication environment is required. The publisher
verifies the candidate, metadata, all histories, current master/hotfix and required
checks. Missing-tag repair additionally requires all three heads at that SHA.
Version tags do not depend on the immediate parent's VERSION.

Read-only reusable jobs build three Docker archives and four executable artifacts
from that immutable source. No registry or contents-write credential reaches npm,
pip, tests, Docker build steps or PyInstaller. Packaging uses canonical platform
names and a portable icon path. Release-critical actions use immutable commits.

Separate approved jobs create/verify the tag, load (never run) image archives,
push components under SHA/run/attempt-specific names, and assemble vVERSION.
No shared architecture tags are deleted. The existing version image must match
the approved revision and platforms, otherwise publication stops. Latest points
to the verified version digest. Develop is updated only while its head still
matches the release. Promotion and publication share the release writer lock;
stale releases fail before changing aliases. All normal automated release writers
use this lock. External writers must respect the release maintenance window.

A stable GitHub release is created as a draft at the approved SHA. Uploads require
explicit contents:write. Existing assets must match their size and GitHub SHA-256
digest; no clobber or stable-release deletion/recreation is allowed. Publish the
draft only after all four assets are confirmed and images have succeeded.
Release events do not recursively start packaging. Existing prereleases are
never deleted, retagged or replaced automatically.

For partial failures, retry with the same approved_sha and artifact_run_id from
the original Release Publication run. Run identity/path/SHA are verified. This
reuses original executable bytes rather than rebuilding a different binary over
an existing asset. Preserve those artifacts (images 14 days, executables 30 days).
Completed version images and matching assets are reused. A server-side incomplete
draft asset, conflicting bytes/tag/image, expired source artifacts, or an existing
release with unverifiable target needs manual review. Never delete a published
stable asset to make a retry pass.

GitHub cannot atomically transact Git refs, Docker aliases and release assets
together. After external partial success, recover forward using the same source
and retained artifacts. Do not move version tags or reset branches as rollback.
Mutable base images and transitive build tools still limit byte reproducibility;
artifact reuse is required for retries. Cross-platform/container builds must also
pass their read-only GitHub jobs before publication.

## Dependabot enforcement

Version-update configuration targets develop for pip, npm and GitHub Actions.
GitHub security updates originate from the default branch, which remains master.
Route Dependency Updates is metadata-only. It disables auto-merge on a misplaced
Dependabot PR before attempting retargeting, verifies the new base, and leaves
normal develop CI to validate the fix. If GitHub rejects retargeting, the master
gate remains blocked. Do not fall back to merging it into master.

Master Dependency Policy creates the check **master-dependency-policy** on the
exact PR head using GitHub Actions integration 15368. It reads trusted base code,
fetches PR Git objects without executing them, and checks every unique commit
for dependency files, including net-zero changes. Dependabot PRs and other PRs
introducing dependency changes cannot target master. The message is:

> Dependency updates must first merge into develop. Perform a Master Release to propagate approved dependency changes to master.

The master-specific check is never granted just because a dependency PR targets
develop. Retargeting therefore cannot reuse develop's ci-status to satisfy it.
A complete release candidate can receive the master gate after its version,
published ref and ancestry of all three branches are verified. Unrelated PRs
without dependency commits are allowed by this policy.

**Administrator prerequisite:** add an active, non-bypassable master-only required
status rule for master-dependency-policy from integration 15368, retaining the
existing ci-status rule on all three branches. Do not require the master-only
policy on ordinary develop PRs. Protect workflow/policy changes with trusted
maintainer review; check names must remain unique. The release helper requires
both checks even before server configuration. Repository files alone cannot make
a new check mandatory. No ruleset or default-branch changes are performed here.

Build-number changes now open a draft metadata-only PR to develop. They cannot
bypass ci-status with the release App, rebase after competing updates, increment
on a stale merge event, or recurse on their own review PR. Release candidate PRs
remain excluded, preserving BUILDNUM=0. Automatic moving-prerelease replacement
and development-image publication are removed from that writer; future development
publication needs a separately reviewed immutable-source procedure.

Development build notes use `scripts/build_changelog.py`. The old prerelease
writer failed after the interrupted release because it assumed `vVERSION`
already existed. The helper selects the latest reachable stable version tag
at or below VERSION; if none exists, it includes the source's complete history.
It ignores prerelease tags and unrelated histories, pins the requested source,
and never creates tags. The build-number review includes these notes without
restoring the retired prerelease publisher. Any future prerelease caller can use
`python scripts/build_changelog.py --repository Kometa-Team/Quickstart --version 0.10.15 --source HEAD --output changelog.md`
before publication; an existing tag for that version is not a prerequisite.

## Urgent production security notifications

Production Security Notifications runs twice hourly, on master pushes, and on
manual dispatch. It uses GitHub-native Dependabot alerts and a **private GitHub
issue tracker**, never public issues or advisory details in public Actions logs.
Native Dependabot security notifications should also be enabled for maintainers
for immediate delivery; scheduled Actions are best effort.

For high/critical alerts, the monitor reads master and develop at pinned snapshots,
checks pinned requirements or every matching package-lock entry against the
vulnerable range, links the alert/advisory and verified candidate fix PRs, and
distinguishes pending, integrated-but-unreleased and verified production fixes.
It updates one issue per alert only when the state changes and closes it only
after production dependency versions prove the fix. Unknown manifests, transitive
Python dependencies or unsupported version syntax require manual review. Alert
dismissal alone is never proof of a production fix. Monitoring does not dismiss
alerts or publish security fixes.

Administrator setup (not performed by this repair):

* Set SECURITY_TRACKER_REPOSITORY to an authorized private repository and arrange
  maintainer watches/assignees there. Public/internal trackers are rejected.
* Configure environment security-monitor for master only. Store
  SECURITY_ALERTS_READ_TOKEN with source Dependabot alerts:read, contents:read
  and pull requests:read; store SECURITY_TRACKER_WRITE_TOKEN with issues:write
  only on the private tracker. No source contents-write scope is needed.
* Configure release-promotion and release-publication with required independent
  reviewers, prevent self-review, disable administrator bypass, and restrict
  permitted branches to develop and master respectively. The code verifies these
  review/bypass settings and fails closed on unreadable configuration.
* Configure release-candidate for reviewed candidate publication. Permit explicit
  per-job Actions contents/pull-request write where shown; confirm repository
  policy permits draft PR creation and release asset uploads. The old default
  workflow-token permissions endpoint was unreadable to the maintainer account.
* Remove release-App bypass grants from required protections or select a verified
  non-bypassing identity. No workflow in the new release path uses that App.
* Restrict Docker Hub production publishing to this approved path and protect
  immutable v* tags. Registry aliases have no cross-service compare-and-swap:
  keep other production writers quiescent through publication.

If protection requires a PR path or any prerequisite is unavailable, stop.
Do not weaken protections. A PR-based installation creates different commit SHAs
and needs fresh validation/approval; it cannot be called identical-tip atomic
promotion. Bootstrap 0.10.15 uses the reviewed local helper after separate approval,
because current production develop still contains the legacy release workflow.

References:
[Dependabot target branches](https://docs.github.com/en/code-security/tutorials/secure-your-dependencies/customizing-dependabot-prs),
[required checks](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches),
[environment approvals](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments),
[Dependabot alert permissions](https://docs.github.com/en/rest/dependabot/alerts).

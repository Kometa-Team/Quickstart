# Plex security advisory integration

The Plex page displays advisory assessments returned by a successful Plex API
validation. It shows a red update warning for affected versions, a small status
for versions addressing this advisory, and a neutral unknown status when a full
version is unavailable. The assessment does not block saving configuration and
does not claim that the entire server is secure.

Explicit `/validate_plex` requests refresh the validated connection and discard
its validation, metadata and library refresh cache entries. Security assessment
uses the version on that freshly validated Plex object, even if a separate
telemetry request fails. Other discovery consumers retain their cache behavior.
The page refreshes assessments when revisited, clears them on credential edits
or validation failure, ignores outdated responses, and permits revalidation
without changing credentials after a Plex upgrade.

Local log recommendations use the same advisory evaluator. They group evidence
by server and advisory, retain historical versions and line references, and add
the semantic `plex_security` finding count. Overlapping legacy range evidence
is retained in the assessment without a second warning. Existing raw log-level
counts and the compatibility version parser API retain their meaning. Strict
advisory parsing never substitutes zeros for missing or malformed components.

## Source ownership and updates

The audit found independent Quickstart and online Logscan analyzers. There is no
shared installable Python core between these repositories. Logscan now owns
`logscan_web/plex_security.py`, a standard library module containing definitions,
parsing, numeric evaluation and historical observation grouping. Quickstart
vendors an identical copy in `modules/_vendor/plex_security.py`, with source
repository, commit and SHA-256 in `plex_security.json`.

Commit changes to the authoritative Logscan source, then sync from its local
checkout:

```powershell
py -3.13 scripts/sync_plex_security.py ../Logscan
py -3.13 scripts/sync_plex_security.py ../Logscan --check
```

The sync command rejects source that differs from its recorded commit. Tests
verify the generated copy's checksum. Update the authoritative source and sync
it; do not maintain a separate implementation here. Shipping updates still
requires a change in each repository. There are no advisory network requests,
additional services or new runtime dependencies.

`PLEX-PMS-2026-09` uses `1.43.3.10861` as the minimum patched version. Critical
is Kometa's recommendation priority and is not an official CVSS rating. Logs
describe versions observed historically. Server names are the available log
identity, so two servers sharing a name cannot reliably be distinguished.

# Blank defaults in generated Kometa configs

Kometa adds missing optional attributes to existing global config sections.
For attributes with a `None` default, it writes a blank YAML value and logs a
warning. Removing that key during Quickstart's next export makes Kometa add
it again on the next run.

Quickstart now fills these nullable defaults after its normal YAML cleanup.
For example, a configured Radarr connection includes blank `radarr_path` and
`plex_path` keys when no path mapping is needed. The same applies to Sonarr
and to settings such as `custom_repo`, `default_collection_order`, and
`playlist_sync_to_users`. Existing values take precedence over defaults.

Defaults apply only to global sections being exported. Unconfigured optional
services remain absent, and library overrides continue to inherit global
settings when their keys are omitted. Ordinary empty template variables still
receive normal cleanup. Defaults are added to generated YAML, without changing
saved form values or requiring a configuration migration.

The section/key list in `modules/output_dump.py` follows Kometa's
`check_for_attribute(self.data, ..., parent=..., default_is_none=True)` calls
that allow config writes. Calls with `save=False` are excluded. These are
blank YAML values, not the text `None`.

Kometa's current schema declares the legacy Sonarr `language_profile` as text
even though its config reader inserts a null default. Quickstart allows text
or null for that global field during validation. Other types and library
override validation keep their existing constraints.

Offline regression tests execute Kometa's actual attribute checker from
commit `1ec206b4c9dd0e9f9ea7b9e7a4e2e56b349e68d0`, the version in the reported
log. Its extracted function, source provenance, checksum, and nullable call
metadata are under `tests/fixtures/kometa/check_for_attribute.*`. The fixture
retains Kometa's MIT license under the repository's existing `LICENSE`.
Tests reproduce the reported insertions, then verify that generated defaults
cause no warnings or config writes for all audited nullable attributes. When
updating the list for a new Kometa version, audit the upstream call sites and
refresh this fixture from the same committed source.

Regenerate the config from Quickstart before running Kometa to apply the fix.

# Library scheduling and processing modes

Open **Libraries**, choose a movie or show library, and expand **Scheduling**. Each library has its own schedule. Choose:

- **No library schedule** to process the library whenever Kometa runs.
- **Basic schedules** to retain Kometa's existing text or list-of-text schedules with full processing.
- **Ordered schedules with processing modes** to choose an item scope for each scheduling rule.

Add, edit, remove, or move rules with the buttons in each row. Ordered rules use the **first matching rule**. A library is skipped if none match. The YAML preview shows the configuration for that library. Imported legacy schedules retain their existing format until edited; imported ordered rules retain their order and values. Unsupported imported structures are preserved and shown for repair instead of being replaced with defaults.

## When Kometa starts

Library schedules do **not** launch Kometa. Use the Docker scheduler, Windows Task Scheduler, cron, or another launcher to start it regularly. Quickstart's final page can start an immediate run or let Kometa wait for its scheduled time.

See the official [scheduling guide](https://kometa.wiki/en/latest/kometa/guides/scheduling/) for launch setup and the [schedule reference](https://kometa.wiki/en/latest/config/schedule/#library-schedule-modes) for configuration syntax.

## Frequencies and modes

The editor provides daily, weekly, and monthly controls, including weekly and monthly exclusions with `.not`. Monthly values accept days 1–31, `last`, and ranges such as `1-7` or `21-last`; days missing from a month are skipped. The advanced field accepts other supported expressions, including `hourly`, `yearly`, `date`, `range`, `never`, and `all[...]`. Invalid expressions produce validation errors.

| Mode | Scope |
| --- | --- |
| `full` | Every top-level library item. |
| `added(7)` | Items added within the last seven days. Bare numbers mean days. |
| `added(30m)`, `added(1h)`, `added(12d)` | Items added within minutes, hours, or explicit 24-hour days. Shows with recently added episodes are included. |
| `diff` | Items absent from the previous cached snapshot; show libraries also compare season update times. Requires a persistent Kometa cache. |
| `index(A-F)` | Plex Sort Titles beginning with letters A through F, inclusive, falling back to the title. Single letters are also supported. |
| `index(A-F#)` | The alphabetical range plus titles beginning with numbers, symbols, or other non-alphabetical characters. |
| `items(imdb:tt0133093\|tmdb:550\|tvdb:350396\|plex:42)` | Matching items already in the library, using pipe-separated provider IDs or top-level Plex rating keys. Unmatched IDs select nothing. |

Durations and numeric IDs must be positive; alphabetical ranges must be ascending. TMDb show IDs are converted to TVDb IDs by Kometa. Selecting a show includes its seasons and episodes.

Schedule regular `full` runs to reconcile the whole library. Scoped runs update metadata, overlays, item operations, and collection additions only within the selected scope. Existing collection members and custom ordering are preserved; members that no longer qualify and overlays outside the scope can remain stale.

```yaml
libraries:
  Movies:
    schedule:
      - schedule: weekly(monday)
        mode: added(7)
      - schedule: weekly(tuesday)
        mode: index(A-F#)
      - schedule: weekly.not(monday|tuesday)
        mode: full
```

## One-time override

On the **Kometa** final page, expand **Optional Mode Flags** and use **Item processing override (one run)**. Select **Run Specific Libraries** in the run options to target one or more libraries.

For example, choosing Movies and Recently added items with one day builds:

```sh
python kometa.py --run-libraries "Movies" --mode 'added(1)'
```

This does not modify saved library rules. `--mode` (or Kometa's `KOMETA_MODE` environment variable) supersedes configured library processing modes, including unmatched library schedules. Individual collection schedules and `schedule_overlays` still apply unless `--ignore-schedules` is used. Without a processing override, explicitly selecting libraries with `--run-libraries` or using `--ignore-schedules` bypasses library scheduling and uses full processing. The processing override is omitted from validate-and-exit commands.

## Compatibility

Ordered rules, `.not` exclusions, and `--mode` require Kometa's finalized library scheduling support, introduced by [Kometa PR #3700](https://github.com/Kometa-Team/Kometa/pull/3700). Quickstart checks the selected managed or existing runtime's actual implementation instead of assuming that a version or branch name guarantees support. Older runtimes receive an export or launch error; saved rules are retained. External runtimes require explicit compatibility confirmation before exporting these features. An older local schema cache is extended only for library schedule mappings; runtime compatibility checks remain enforced.

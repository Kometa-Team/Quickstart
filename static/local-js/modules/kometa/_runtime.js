// Kometa runtime configuration readers.
//
// The Kometa-run/update page has a hidden `#run-command-output` element
// whose data-* attributes carry the server's authoritative view of:
//
//   - How Kometa is installed (managed / existing / external)
//   - Where the Kometa root is (as both a POSIX path for the backend
//     and a user-facing display path)
//   - What runtime capabilities exist for the current config
//     (can we launch it? can we validate it? can we read its logs?)
//
// This module owns the seven small readers that consult those
// dataset fields. They're the "first line" of every runtime-related
// operation -- validateKometaRoot, buildCommand, syncKometaRollupBadge,
// probeKometaRoot, and the update flow all start by asking these
// helpers "what mode are we in?" and "where does Kometa live?".
//
// DESIGN NOTES:
//
//   1. Each reader is a PURE DOM read -- no mutation, no side effects,
//      no module-scoped state. Callers get a fresh snapshot every
//      time. This matches the pre-extraction behavior (the dataset
//      is treated as the single source of truth and re-read on every
//      access).
//
//   2. All seven read the SAME element (#run-command-output). Rather
//      than exporting a single "get everything" helper (which would
//      be a temptation to cache), we kept the API split by concern
//      so callers can express intent clearly:
//
//         if (kometaCanProbeRuntime()) { validateKometaRoot(...) }
//         if (kometaCanReadLogs())     { fetchLogTail(...) }
//
//      is more readable than
//
//         const runtime = getKometaRuntime()
//         if (runtime.canProbe) { ... }
//         if (runtime.canReadLogs) { ... }
//
//      and it lets each helper own its own dataset key mapping.
//
//   3. Every helper returns a SAFE default when the element or
//      attribute is missing (empty string, false, or 'managed'). This
//      matches how ES module load order interacts with the DOM: if
//      code imports this module before DOMContentLoaded, calls
//      wouldn't throw -- they'd just report the conservative "nothing
//      is available" state until the DOM catches up.

/**
 * Get the install mode configured on the current wizard page.
 *
 * @returns {'managed' | 'existing' | 'external'}
 *   'managed'  = Quickstart manages the Kometa install (git clone into
 *                a folder Quickstart owns)
 *   'existing' = user has an existing Kometa install on disk that
 *                Quickstart will sync config to and launch
 *   'external' = Kometa runs outside of Quickstart's reach entirely
 *                (Docker container, remote machine, ...); Quickstart
 *                only writes config here. No launch, no probe, no logs.
 *
 * Default (missing element or unknown value) is 'managed' to match
 * the historic pre-extraction fallback.
 */
export function getConfiguredKometaInstallMode () {
  const out = document.getElementById('run-command-output')
  const raw = ((out && out.dataset.kometaInstallMode) || 'managed').toString().trim().toLowerCase()
  if (raw === 'existing' || raw === 'external') return raw
  return 'managed'
}

/**
 * Get the Kometa root path as a POSIX string, suitable for sending
 * to the backend / embedding in JSON payloads.
 *
 * The three data-* attributes we consult:
 *   kometaRootSelected   -- user-chosen root (highest priority)
 *   kometaRootDefault    -- fallback when nothing is chosen
 *   kometaConfigDir      -- returned instead when mode is 'external'
 *                            (config dir is the only thing Quickstart
 *                            has visibility into in that mode)
 *
 * @returns {string} POSIX path, or empty string if nothing is set.
 */
export function getConfiguredKometaRootPosix () {
  const out = document.getElementById('run-command-output')
  if (!out) return ''
  const selected = (out.dataset.kometaRootSelected || '').toString().trim()
  const fallback = (out.dataset.kometaRootDefault || '').toString().trim()
  const configDir = (out.dataset.kometaConfigDir || '').toString().trim()
  if (getConfiguredKometaInstallMode() === 'external') return configDir
  return selected || fallback
}

/**
 * Get the Kometa root path as a user-facing display string.
 *
 * Same priority order as getConfiguredKometaRootPosix, but reading
 * the *Display variants of each dataset key. Falls back to the
 * POSIX version if no display-specific value was provided.
 *
 * @returns {string}
 */
export function getConfiguredKometaRootDisplay () {
  const out = document.getElementById('run-command-output')
  if (!out) return getConfiguredKometaRootPosix()
  const selected = (out.dataset.kometaRootSelectedDisplay || '').toString().trim()
  const fallback = (out.dataset.kometaRootDefaultDisplay || getConfiguredKometaRootPosix())
  const configDir = (out.dataset.kometaConfigDirDisplay || '').toString().trim()
  if (getConfiguredKometaInstallMode() === 'external') return configDir || getConfiguredKometaRootPosix()
  return selected || fallback
}

// ---------------------------------------------------------------------
// Runtime capability flags
// ---------------------------------------------------------------------
//
// Server-computed booleans that gate which runtime operations are
// even attempted for the current config. Each one keys off a separate
// data-* attribute so the server can independently disable, e.g.,
// launch (for read-only remote Kometa) or logs (for a non-mounted
// external volume).

/**
 * True iff Quickstart can invoke Kometa to run (as opposed to only
 * being able to write config files). Gates the "Run Now" button.
 *
 * @returns {boolean}
 */
export function kometaCanLaunch () {
  const el = document.getElementById('run-command-output')
  return ((el && el.dataset.kometaCanLaunch) || '').toString().toLowerCase() === 'true'
}

/**
 * True iff Quickstart can probe the Kometa install to determine
 * what version is installed and whether an update is available.
 * Gates the "check for updates" background flow.
 *
 * External Kometa mode disables this because Quickstart has no
 * filesystem access to the install directory.
 *
 * @returns {boolean}
 */
export function kometaCanCheckUpdateStatus () {
  return getConfiguredKometaInstallMode() !== 'external' && kometaCanProbeRuntime()
}

/**
 * True iff Quickstart can run validateKometaRoot / probeKometaRoot
 * against the current install (i.e., we have filesystem access to
 * the root). Gates all runtime-validation flows.
 *
 * @returns {boolean}
 */
export function kometaCanProbeRuntime () {
  const el = document.getElementById('run-command-output')
  return ((el && el.dataset.kometaCanProbeRuntime) || '').toString().toLowerCase() === 'true'
}

/**
 * True iff Quickstart can tail the Kometa log file. Gates the
 * live-log polling on the Run screen.
 *
 * @returns {boolean}
 */
export function kometaCanReadLogs () {
  const el = document.getElementById('run-command-output')
  return ((el && el.dataset.kometaCanReadLogs) || '').toString().toLowerCase() === 'true'
}

// CLI flag labels + library-visibility toggle for the Kometa run panel.
//
// The Kometa "Run Kometa" panel shows a bunch of checkbox/toggle
// options that map to Kometa's CLI flags. This module provides:
//
//   KOMETA_CLI_FLAGS
//     A frozen catalog of every CLI flag Kometa supports, with a
//     friendly label + long description. Consumed by
//     updateFlagLabels() to render the panel labels either as
//     friendly text ("Debug Logging") or as raw CLI flags ("--debug"),
//     depending on the "show CLI" toggle.
//
//   updateFlagLabels(showCli, opts)
//     Re-render every flag <label> in the panel. Two modes:
//       showCli=false  -> friendly labels (default)
//       showCli=true   -> raw --flag names
//     Each label gets an info-icon <span> with a Bootstrap tooltip
//     showing the description. After rendering, invokes two side-
//     effect callbacks:
//       - onInitTooltips(document)  to attach Bootstrap tooltips
//       - onLabelsUpdated()         to notify the header-badge rollup
//
//   updateLibraryVisibility(mainOption)
//     Show/hide the "select libraries" multiselect based on the
//     currently-selected run-option radio value. Only visible when
//     the "Run Specific Libraries" radio is picked.
//
// DEPENDENCY-INVERSION PATTERN
//
// Rather than importing initBootstrapTooltips and
// syncFinalAccordionRollups directly, updateFlagLabels takes them
// as callbacks. Same pattern used elsewhere in the split
// (_logscan.js, _validationDisplay.js) -- keeps the module graph
// one-directional and lets tests use spies.

/**
 * Frozen catalog of Kometa CLI flags. Extending Kometa's CLI means
 * adding an entry here (label + description) and wiring the new
 * flag into the appropriate flag-group array in updateFlagLabels.
 *
 * Descriptions may contain HTML (used inside a `title="..."` attr
 * which then gets Bootstrap-tooltip-rendered as HTML). Escape user-
 * facing text carefully -- these strings are dropped into markup
 * without sanitization.
 */
export const KOMETA_CLI_FLAGS = Object.freeze({
  '--run': {
    label: 'Run Immediately',
    description: 'If you want Kometa to run immediately rather than waiting until 5AM, set this flag'
  },
  '--run-libraries': {
    label: 'Run Specific Libraries',
    description: 'Run Kometa only on selected libraries.'
  },
  '--times': {
    label: 'Time to Run',
    description: 'Run at these times. Kometa wakes up at 5:00 AM to process the config file. If you want to change that time, or tell Kometa to wake up at multiple times, use this flag.'
  },
  '--operations-only': {
    label: 'Operations Only',
    description: 'Only perform operations (e.g., rating/poster updates).'
  },
  '--metadata-only': {
    label: 'Metadata Only',
    description: 'Only run metadata files.'
  },
  '--collections-only': {
    label: 'Collections Only',
    description: 'Only build collections.'
  },
  '--playlists-only': {
    label: 'Playlists Only',
    description: 'Only build playlists, skip everything else.'
  },
  '--overlays-only': {
    label: 'Overlays Only',
    description: 'Only apply overlays to media posters.'
  },
  '--debug': {
    label: 'Debug Logging',
    description: 'Enable debug-level logging.'
  },
  '--trace': {
    label: 'Trace Logging',
    description: 'Enable trace-level (very verbose) logging.'
  },
  '--log-requests': {
    label: 'Log Requests Logging',
    description: 'Most verbose logging. If you enable this, every external network request made by Kometa will be logged, along with the data that is returned. This will add a lot of data to the logs, and will probably contain things like tokens, since the auto-redaction of such things is not generalized enough to catch any token that may be in any URL.<br><strong>WARNING</strong>:<br><code>This can potentially have personal information in it.</code>'
  },
  '--validate': {
    label: 'Validate Generated Config',
    description: 'Parse and validate the generated config.yml and linked YAML files, print a structured report, then exit without performing a normal run. Environment variable: <code>KOMETA_VALIDATE</code>.'
  },
  '--validate-file': {
    label: 'Validate File',
    description: 'Validate one YAML file against its auto-detected JSON schema and print any errors or schema gaps. Environment variable: <code>KOMETA_VALIDATE_FILE</code>.'
  },
  '--validate-dir': {
    label: 'Validate Directory',
    description: 'Recursively validate YAML files in a directory and print a combined schema-gap report. Environment variable: <code>KOMETA_VALIDATE_DIR</code>.'
  },
  '--validate-level': {
    label: 'Validate Level',
    description: 'Controls how deep config validation goes. Accepted values: <code>syntax</code>, <code>structure</code>, or <code>full</code>. Environment variable: <code>KOMETA_VALIDATE_LEVEL</code>.'
  },
  '--validate-schema': {
    label: 'Validate Schema',
    description: 'When set with config validation, also check YAML files against JSON schemas. Environment variable: <code>KOMETA_VALIDATE_SCHEMA</code>.'
  },
  '--schema-path': {
    label: 'Schema Path',
    description: 'Override the path to the json-schema directory used by schema validation. Environment variable: <code>KOMETA_SCHEMA_PATH</code>.'
  },
  '--delete-collections': {
    label: 'Delete Collections',
    description: 'Delete all collections in each library as the first step in the run.<br><strong>WARNING</strong>:<br><code>You will lose all collections in the library - this will delete all collections, including ones not created or maintained by Kometa.</code>'
  },
  '--delete-labels': {
    label: 'Delete Labels',
    description: 'Delete all labels [except one, see below] on every item in a Library prior to running collections/operations.<br><strong>WARNING</strong>:<br><code>To preserve functionality of Kometa, this will not remove the Overlay label, which is required for Kometa to know which items have Overlays applied. This will impact any Smart Label Collections that you have in your library. We do not recommend using this on a regular basis if you also use any operations or collections that update labels, as you are effectively deleting and adding labels on each run.</code>'
  },
  '--read-only-config': {
    label: 'Read Only Config',
    description: 'Kometa reads in and then writes out a properly formatted version of your config.yml on each run;this makes the formatting consistent and ensures that you have visibility into new settings that get added. If you want to disable this behavior and tell Kometa to leave your config.yml as-is, use this flag.'
  },
  '--low-priority': {
    label: 'Priority',
    description: 'Run the Kometa process at a lower priority. Will default to normal priority if not specified.'
  },
  '--no-report': {
    label: 'No Report',
    description: 'Kometa can produce a report of missing items, collections, and other information. If you have this report enabled but want to disable it for a specific run, use this flag.'
  },
  '--no-missing': {
    label: 'No Missing',
    description: 'Kometa can take various actions on missing items, such as sending them to Radarr, listing them in the log, or saving a report. If you want to disable all of these actions, use this flag.'
  },
  '--no-countdown': {
    label: 'No Countdown',
    description: 'Typically, when not doing an immediate run, Kometa displays a countdown in the terminal where it is running. If you want to hide this countdown, use this flag.'
  },
  '--ignore-ghost': {
    label: 'Ignore Ghost',
    description: 'Kometa prints some things to the log that do not actually go into the log file on disk. Typically these are things like status messages while loading and/or filtering. If you want to hide all ghost logging for the run, use this flag.'
  },
  '--ignore-schedules': {
    label: 'Ignore Schedules',
    description: 'Ignore all schedules for the run. Range Scheduled collections (such as Christmas movies) will still be ignored.'
  },
  '--no-verify-ssl': {
    label: 'No Verify SSL',
    description: 'Turn SSL Verification off.<br><strong>NOTE</strong>:<br>Set this if your log file shows any errors similar to <code>SSL: CERTIFICATE_VERIFY_FAILED</code>'
  },
  '--tests': {
    label: 'Run Tests',
    description: 'If you set this flag to true, Kometa will run only collections that you have marked as test immediately, like KOMETA_RUN.<br><strong>NOTE</strong>:<br>This will only run collections with <code>test: true</code> in the definition.'
  },
  '--timeout': {
    label: 'Timeout',
    description: 'Change the timeout in seconds for all non-Plex services (such as TMDb, Radarr, and Trakt). This will default to <code>180</code> when not specified and is overwritten by any timeouts mentioned for specific services in the Configuration File.'
  },
  '--divider': {
    label: 'Divider Character',
    description: 'Customize the divider shown between repeated output elements (e.g., <code>></code>) Default is <code>=</code>'
  },
  '--width': {
    label: 'Screen Width',
    description: 'The log is formatted to fit within a certain width. If you wish to change that width, you can do that with this flag. Not that long lines are not wrapped or truncated to this width; this controls the minimum width of the log. Default is <code>100</code>'
  }
})

// Flag groups. Each corresponds to a chunk of the "Run Kometa" panel
// UI. Keeping them as module-scoped constants (rather than inline
// arrays inside updateFlagLabels) makes it obvious which flags are
// missing from the panel if someone adds a new one to KOMETA_CLI_FLAGS
// but forgets to render it.
const RUN_OPTION_FLAGS = ['--run', '--run-libraries', '--times']
const MODE_FLAGS = [
  '--operations-only', '--metadata-only', '--collections-only',
  '--overlays-only', '--playlists-only'
]
const LOG_FLAGS = ['--debug', '--trace', '--log-requests']
const VALIDATION_FLAGS = [
  '--validate', '--validate-file', '--validate-dir',
  '--validate-level', '--validate-schema', '--schema-path'
]
const OTHER_FLAGS = [
  '--delete-collections', '--delete-labels', '--read-only-config', '--low-priority',
  '--no-report', '--no-missing', '--no-countdown', '--ignore-ghost',
  '--ignore-schedules', '--no-verify-ssl', '--tests', '--timeout', '--divider', '--width'
]

/**
 * Refresh every flag <label> in the "Run Kometa" panel.
 *
 * Each flag has a corresponding <label for="opt-XXX"> where XXX is
 * the flag name with the leading "--" stripped. Rendered content:
 *
 *   {label-text} <span class="text-info"
 *                       data-bs-toggle="tooltip"
 *                       title="{description}">
 *     <i class="bi bi-info-circle-fill ms-1"></i>
 *   </span>
 *
 * @param {boolean} showCli  When true, use raw "--flag" text as the
 *                            label instead of the friendly label.
 * @param {object} [opts]
 * @param {(root:Document|Element) => void} [opts.onInitTooltips]
 *   Called after re-rendering to (re)attach Bootstrap tooltips.
 *   Receives the document root as its only arg.
 * @param {() => void} [opts.onLabelsUpdated]
 *   Called after rendering + tooltip init. Used by the header-badge
 *   rollup to refresh any label-derived display state.
 */
export function updateFlagLabels (showCli, opts = {}) {
  const { onInitTooltips, onLabelsUpdated } = opts

  function updateLabels (group, prefix = '') {
    group.forEach(flag => {
      const id = `${prefix}${flag.replace(/^--/, '')}`
      const label = document.querySelector(`label[for="${id}"]`)
      if (!label) return
      const spec = KOMETA_CLI_FLAGS[flag]
      const content = showCli ? flag : (spec?.label || flag)
      const desc = spec?.description || ''
      label.innerHTML = `${content} <span class="text-info" data-bs-toggle="tooltip" title="${desc}"><i class="bi bi-info-circle-fill ms-1"></i></span>`
    })
  }

  updateLabels(RUN_OPTION_FLAGS, 'opt-')
  updateLabels(MODE_FLAGS, 'opt-')
  updateLabels(LOG_FLAGS, 'opt-')
  updateLabels(VALIDATION_FLAGS, 'opt-')
  updateLabels(OTHER_FLAGS, 'opt-')

  if (onInitTooltips) onInitTooltips(document)
  if (onLabelsUpdated) onLabelsUpdated()
}

/**
 * Show/hide the library multiselect based on the current run-option.
 *
 * When the user picks "Run Specific Libraries", the multiselect
 * needs to be visible. All other run options hide it.
 *
 * @param {string} mainOption  The value of the currently-selected
 *                              run-option radio (e.g. '--run-libraries').
 */
export function updateLibraryVisibility (mainOption) {
  const libSelect = document.getElementById('library-multiselect')
  const librarySection = libSelect ? libSelect.closest('.mb-2') : null
  if (!librarySection) return
  if (mainOption === '--run-libraries') {
    librarySection.classList.remove('d-none')
  } else {
    librarySection.classList.add('d-none')
  }
}

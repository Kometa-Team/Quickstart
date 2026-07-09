// "Prepare Kometa" running-state toggler.
//
// While Kometa is executing, we want to:
//   - dim the accordion (visual "locked" state)
//   - collapse it if currently expanded
//   - disable the toggle button + add a tooltip explaining why
//
// When the run finishes, we undo all of that so the user can
// re-open the actions and edit the run command.
//
// This module owns THAT one lifecycle transition. It does not own
// the accordion's DOM elements themselves (they're rendered by
// Jinja templates and the ids are shared with several other event
// handlers in 900-kometa.js). Instead, the function lazy-resolves
// its DOM references via document.getElementById each call. That
// keeps this module stateless and cheap to import.
//
// PUBLIC API:
//
//   setKometaPrepareRunningState(isRunning)
//     No-op if the accordion elements are missing (e.g. on a page
//     where the "Prepare Kometa" section wasn't rendered). Requires
//     Bootstrap's Collapse global to collapse a currently-expanded
//     accordion; falls back to a no-collapse toggle when Bootstrap
//     isn't loaded (still applies the disabled + dimmed styling).
//
// ELEMENT IDS (resolved lazily each call):
//   #kometa-actions-accordion   - outer wrapper, gets .opacity-50 dim
//   #kometa-actions-collapse    - the collapsible body
//   #kometa-actions-toggle      - the toggle button

/**
 * Toggle the "Prepare Kometa" accordion between running/idle states.
 *
 * @param {boolean} isRunning  true while Kometa is running; false
 *                              when the run finishes (or on a fresh
 *                              page that isn't running).
 */
export function setKometaPrepareRunningState (isRunning) {
  const accordion = document.getElementById('kometa-actions-accordion')
  const collapse = document.getElementById('kometa-actions-collapse')
  const toggle = document.getElementById('kometa-actions-toggle')

  if (accordion) {
    accordion.classList.toggle('opacity-50', Boolean(isRunning))
  }

  // Everything below needs both the collapse + toggle. If either is
  // missing (unusual page layout), silently no-op.
  if (!collapse || !toggle) return

  // Hide the accordion body if it's currently open. Bootstrap's
  // Collapse.hide() animates it out; without Bootstrap loaded we
  // just skip the animation (the disabled styling below still
  // applies).
  const bootstrapAvailable = typeof bootstrap !== 'undefined' && bootstrap.Collapse
  if (isRunning && collapse.classList.contains('show') && bootstrapAvailable) {
    bootstrap.Collapse.getOrCreateInstance(collapse, { toggle: false }).hide()
  }

  if (isRunning) {
    toggle.classList.add('collapsed')
    toggle.setAttribute('aria-expanded', 'false')
    toggle.setAttribute('title', 'Kometa is running. Prepare Kometa is locked until the run finishes.')
    toggle.disabled = true
    toggle.classList.add('disabled')
  } else {
    toggle.removeAttribute('title')
    toggle.disabled = false
    toggle.classList.remove('disabled')
  }
}

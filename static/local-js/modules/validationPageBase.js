// Shared helpers used by every credential-style wizard page.
//
// Eliminates the 13x duplication of setToggleButtonIcon and the 15x
// duplication of refreshValidationCallout that grew because the codebase
// had no module system. Page scripts import these as needed.

export function setToggleButtonIcon (button, showPlainText) {
  if (!button) return
  const icon = document.createElement('i')
  icon.className = showPlainText ? 'fas fa-eye-slash' : 'fas fa-eye'
  button.replaceChildren(icon)
}

export function refreshValidationCallout (fieldName) {
  if (window.QSValidationCallouts && typeof window.QSValidationCallouts.refresh === 'function') {
    window.QSValidationCallouts.refresh(fieldName)
  }
}

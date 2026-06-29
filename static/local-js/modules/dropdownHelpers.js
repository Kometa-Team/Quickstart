// Shared DOM helpers for wizards that populate <select> dropdowns from
// validate-endpoint responses (Radarr, Sonarr). Kept separate from
// createApiKeyValidator because dropdown population is orthogonal to
// credential validation -- some wizards do one, some do both, some
// do neither.
//
// These are pure utility functions: they take elements and data,
// mutate the DOM, return nothing. No assumption about wizard state,
// validation flags, etc.

/**
 * Replace a dropdown's children with a single placeholder option.
 *
 * @param {HTMLSelectElement|null} dropdown
 * @param {string} placeholderText
 */
export function resetDropdown (dropdown, placeholderText) {
  if (!dropdown) return
  const option = document.createElement('option')
  option.value = ''
  option.textContent = placeholderText
  dropdown.replaceChildren(option)
}

/**
 * Populate a dropdown from an array of plain objects, optionally
 * pre-selecting one value.
 *
 * @param {string} elementId          Id of the <select> to populate.
 * @param {Array<object>} data        Items to render. Falsy data is a no-op.
 * @param {string} valueField         Key on each item used for option.value.
 * @param {string} textField          Key on each item used for option.textContent.
 * @param {string} [selectedValue=''] If truthy and matches an option.value,
 *                                    that option is pre-selected.
 * @param {string} [placeholderText='Select an option']
 */
export function populateDropdown (elementId, data, valueField, textField, selectedValue = '', placeholderText = 'Select an option') {
  const dropdown = document.getElementById(elementId)
  if (!dropdown) return
  resetDropdown(dropdown, placeholderText)
  if (!Array.isArray(data)) return

  for (const item of data) {
    const option = document.createElement('option')
    option.value = item[valueField]
    option.textContent = item[textField]
    dropdown.appendChild(option)
  }

  if (selectedValue) {
    dropdown.value = selectedValue
  }
}

/**
 * Set multi-line text on a status element using <br> separators.
 * Used by wizards that report multiple validation errors at once
 * (e.g. "missing root folder" + "missing quality profile").
 *
 * @param {HTMLElement|null} element
 * @param {string[]} messages
 */
export function setStatusMessageLines (element, messages) {
  if (!element) return
  element.textContent = ''
  messages.forEach((message, index) => {
    if (index > 0) element.appendChild(document.createElement('br'))
    element.appendChild(document.createTextNode(message))
  })
}

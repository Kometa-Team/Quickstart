/* global confirm */

document.getElementById('clearSessionButton').addEventListener('click', function (event) {
  event.preventDefault()
  if (confirm('Are you sure you want to clear the session data? This action cannot be undone.')) {
    document.getElementById('clearSessionForm').submit()
  }
})

/* eslint-disable no-unused-vars, camelcase */
function validate_name (select) {
  let text = select.value

  text = text.toLowerCase()

  text = text.replace(/[^a-z0-9_]/g, '')

  select.value = text
}
/* eslint-enable no-unused-vars, camelcase */

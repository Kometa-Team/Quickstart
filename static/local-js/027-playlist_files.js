import { refreshValidationCallout } from './modules/validationPageBase.js'

const validatedAtInput = document.getElementById('playlist_files_validated_at')
const plexValidEl = document.getElementById('plex_valid')
const plexValid = !!plexValidEl && plexValidEl.dataset.plexValid === 'True'
console.log('Plex Valid:', plexValid)

const librariesContainer = document.getElementById('libraries-container')
const validationMessages = document.getElementById('validation-messages')

if (!plexValid) {
  if (librariesContainer) librariesContainer.style.display = 'none'
  if (validationMessages) {
    // The <a data-jumpto-page="010-plex"> link is picked up by the
    // delegated click listener in 000-base.js. Same message text is
    // duplicated in static/local-js/validationHandler.js (line ~60);
    // they can't share a module-level constant yet because
    // validationHandler.js is loaded as a classic script (no imports).
    validationMessages.innerHTML =
      'Plex settings have not been validated successfully. Please <a href="javascript:void(0);" data-jumpto-page="010-plex">return to the Plex page</a> and hit the validate button and ensure success before returning here.<br>'
    validationMessages.style.display = ''
  }
} else {
  if (librariesContainer) librariesContainer.style.display = ''
  if (validationMessages) validationMessages.style.display = 'none'
}

const librariesInput = document.getElementById('libraries')
const validatedField = document.getElementById('playlist_files_validated')

// Initialize checkboxes based on preselected libraries
const initialLibrariesRaw = librariesInput && librariesInput.value ? librariesInput.value : ''
const selectedLibraries = initialLibrariesRaw.split(',').map(item => item.trim())
console.log('Preselected Libraries:', selectedLibraries)

const libraryCheckboxes = document.querySelectorAll('.library-checkbox')
libraryCheckboxes.forEach(checkbox => {
  if (selectedLibraries.includes(checkbox.value)) {
    checkbox.checked = true
  }
})

// Update validation state
function updateValidationState (isValid) {
  if (validatedField) validatedField.value = isValid ? 'true' : 'false'
  if (validatedAtInput) {
    validatedAtInput.value = isValid ? new Date().toISOString() : ''
  }
  refreshValidationCallout('playlist_files_validated')
  console.log('Validation State Updated:', isValid)
}

// Update hidden input field when checkboxes are changed
libraryCheckboxes.forEach(checkbox => {
  checkbox.addEventListener('change', function () {
    const updatedLibraries = Array.from(document.querySelectorAll('.library-checkbox:checked'))
      .map(box => box.value)
    if (librariesInput) librariesInput.value = updatedLibraries.join(', ')
    updateValidationState(updatedLibraries.length > 0)
    console.log('Updated Libraries:', updatedLibraries)
  })
})

// Preserve data on form submission for backend processing
const configForm = document.getElementById('configForm')
if (configForm) {
  configForm.addEventListener('submit', function () {
    const defaultEl = document.getElementById('default')
    const templateVariables = document.getElementById('template_variables')
    console.log('Form Submitted:')
    console.log('Default:', defaultEl ? defaultEl.value : '')
    console.log('Libraries:', librariesInput ? librariesInput.value : '')
    console.log('Validated:', validatedField ? validatedField.value : '')
    console.log('Template Variables:', templateVariables ? templateVariables.value : '')
  })
}

function loading (action) {
  console.log('action:', action)

  let spinnerIcon
  switch (action) {
    case 'prev':
      spinnerIcon = document.getElementById('prev-spinner-icon')
      break
    case 'next':
      spinnerIcon = document.getElementById('next-spinner-icon')
      break
    case 'jump':
      spinnerIcon = document.getElementById('next-spinner-icon') || document.getElementById('prev-spinner-icon')
      break
    default:
      console.error('Unsupported action:', action)
      return
  }

  if (spinnerIcon) {
    spinnerIcon.classList.remove('fa-arrow-left', 'fa-arrow-right')
    // spinnerIcon.classList.add('fa-spinner', 'fa-pulse', 'fa-fw');
    spinnerIcon.classList.add('spinner-border', 'spinner-border-sm')
  } else {
    console.error('Spinner icon not found for action:', action)
  }
}

/* eslint-disable no-unused-vars */
// Function to show the spinner on validate
function showSpinner (webhookType) {
  document.getElementById(`spinner_${webhookType}`).style.display = 'inline-block'
}

// Function to hide the spinner on validate
function hideSpinner (webhookType) {
  document.getElementById(`spinner_${webhookType}`).style.display = 'none'
}

// Function to handle jump to action
function jumpTo (targetPage) {
  const form = document.getElementById('configForm') || document.getElementById('final-form')

  if (!form) {
    console.error('Form not found')
    return
  }

  // Check form validity
  if (!form.checkValidity()) {
    form.reportValidity()
    return
  }

  // Create FormData object from the form
  const formData = new FormData(form)

  // Show loading spinner
  loading('jump')

  // Append the targetPage to the form data
  formData.append('jump_to', targetPage)

  // Submit the form data via fetch without the jumpTo field
  fetch(form.action, {
    method: 'POST',
    body: formData
  }).then(response => {
    if (response.ok) {
      // Redirect to the target page after successful form submission
      window.location.href = '/step/' + targetPage
    } else {
      console.error('Form submission failed:', response.statusText)
    }
  }).catch(error => {
    console.error('Error during form submission:', error)
  })
}
/* eslint-enable no-unused-vars */

document.addEventListener('DOMContentLoaded', function () {
  const cardFooters = document.querySelectorAll('.card-footer')

  cardFooters.forEach(cardFooter => {
    const checkbox = cardFooter.querySelector('input[type="checkbox"]')
    const button = cardFooter.querySelector('button')

    if (checkbox && button) { // Ensure both elements exist
      checkbox.addEventListener('change', function () {
        button.disabled = !this.checked
      })

      // Initial State: Check if the button should be disabled on load
      button.disabled = !checkbox.checked
    }
  })
})

/* eslint-disable no-unused-vars */
function librarySelect () {
  const T = document.getElementById('library_select')
  T.style.display = 'block' // <-- Set it to block
}
/* eslint-enable no-unused-vars */

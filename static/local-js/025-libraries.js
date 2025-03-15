/* global EventHandler, ValidationHandler */

function loadScriptsSequentially (scripts, callback) {
  let index = 0

  function loadNext () {
    if (index >= scripts.length) {
      console.log('[DEBUG] All scripts loaded.')
      if (callback) callback()
      return
    }

    const script = document.createElement('script')
    script.src = scripts[index]
    script.type = 'text/javascript'
    script.onload = function () {
      console.log(`[DEBUG] Loaded script: ${scripts[index]}`)
      index++
      loadNext() // Load the next script
    }
    script.onerror = function () {
      console.error(`[ERROR] Failed to load script: ${scripts[index]}`)
    }

    document.head.appendChild(script)
  }

  loadNext() // Start loading scripts
}

document.addEventListener('DOMContentLoaded', function () {
  console.log('[DEBUG] Initializing Libraries...')

  const scriptsToLoad = [
    '/static/local-js/imageHandler.js',
    '/static/local-js/overlayHandler.js',
    '/static/local-js/validationHandler.js', // Renamed
    '/static/local-js/eventHandler.js'
  ]

  loadScriptsSequentially(scriptsToLoad, function () {
    console.log('[DEBUG] All dependencies loaded. Running Library Initialization...')

    // Ensure EventHandler is loaded before using it
    if (typeof EventHandler !== 'undefined' && EventHandler.attachLibraryListeners) {
      console.log('[DEBUG] Calling EventHandler.attachLibraryListeners()')
      EventHandler.attachLibraryListeners()
    } else {
      console.error('[ERROR] EventHandler is not loaded properly. Check script paths.')
    }

    // Ensure ValidationHandler is loaded before calling updateValidationState()
    if (typeof ValidationHandler !== 'undefined' && ValidationHandler.updateValidationState) {
      console.log('[DEBUG] Calling ValidationHandler.updateValidationState() after script load')
      ValidationHandler.updateValidationState()
    } else {
      console.error('[ERROR] ValidationHandler is not loaded properly. Check script paths.')
    }
  })
})

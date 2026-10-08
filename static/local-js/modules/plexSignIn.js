import { setToggleButtonIcon } from './validationPageBase.js'

export function setupPlexSignIn () {
  const signIn = document.getElementById('plexSignIn')
  const cancel = document.getElementById('plexSignInCancel')
  const openPlex = document.getElementById('plexSignInOpen')
  const spinner = document.getElementById('plexSignInSpinner')
  const status = document.getElementById('plexAuthStatus')
  const token = document.getElementById('plex_token')
  const url = document.getElementById('plex_url')
  const validate = document.getElementById('validateButton')
  const config = document.getElementById('qs-active-config-input')
  if (!signIn || !cancel || !openPlex || !status || !token || !url || !validate || !config) return

  let active = null

  function showStatus (message, failed = false) {
    status.textContent = message
    status.style.display = 'block'
    status.classList.toggle('status-warning', failed)
    status.classList.toggle('status-success', !failed)
  }

  function showPending (pending) {
    signIn.disabled = pending
    token.readOnly = pending
    cancel.classList.toggle('d-none', !pending)
    spinner?.classList.toggle('d-none', !pending)
    validate.disabled = pending || document.getElementById('plex_validated')?.value === 'true'
    if (!pending) {
      openPlex.classList.add('d-none')
      openPlex.removeAttribute('href')
    }
  }

  function closePopup (state) {
    try { state.popup?.close() } catch { /* Browser isolation can detach the popup. */ }
  }

  function cleanupAttempt (state) {
    if (!state.attemptId) return
    fetch('/plex-auth/cancel', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ attempt_id: state.attemptId }),
      keepalive: true
    }).catch(() => {})
  }

  function finish (state) {
    if (active !== state) return
    active = null
    clearTimeout(state.timer)
    state.controller?.abort()
    closePopup(state)
    cleanupAttempt(state)
    showPending(false)
  }

  async function requestAuth (endpoint, state) {
    const controller = new AbortController()
    // Let a cancelled start finish so its returned attempt ID can be cleaned up.
    if (endpoint === 'check') state.controller = controller
    const timeout = setTimeout(() => controller.abort(), 25000)
    try {
      const response = await fetch(`/plex-auth/${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ config_name: state.configName, attempt_id: state.attemptId }),
        signal: controller.signal
      })
      const data = await response.json()
      return { response, data }
    } finally {
      clearTimeout(timeout)
      if (state.controller === controller) state.controller = null
    }
  }

  async function poll (state) {
    if (active !== state || state.controller) return
    if (config.value !== state.configName) {
      finish(state)
      showStatus('The selected configuration changed. Please start Plex sign-in again.', true)
      return
    }
    if (Date.now() >= state.expiresAt) {
      finish(state)
      showStatus('Plex sign-in expired. Please try again.', true)
      return
    }
    try {
      const { response, data } = await requestAuth('check', state)
      if (active !== state) return
      if (config.value !== state.configName) {
        finish(state)
        showStatus('The selected configuration changed. Please start Plex sign-in again.', true)
        return
      }
      if (!response.ok) {
        showStatus(data.error || 'Unable to check Plex approval.', true)
        if (response.status <= 500) {
          finish(state)
          return
        }
      } else if (data.authenticated && data.token) {
        finish(state)
        token.value = data.token
        token.type = 'password'
        setToggleButtonIcon(document.getElementById('toggleApikeyVisibility'), false)
        token.dispatchEvent(new Event('input', { bubbles: true }))
        const ready = !!url.value.trim()
        showStatus(`Signed in as ${data.username || 'Plex account'}.${ready ? '' : ' Enter your Plex server URL, then validate.'}`)
        if (ready) validate.click()
        else url.focus()
        return
      } else {
        showStatus('Waiting for Plex approval...')
      }
    } catch {
      if (active !== state) return
      showStatus('Unable to check Plex approval. Retrying...', true)
    }
    if (active === state) state.timer = setTimeout(() => poll(state), 2000)
  }

  signIn.addEventListener('click', async () => {
    if (active) return
    // Open synchronously within the click so popup blockers allow it.
    const popup = window.open('about:blank', '_blank', 'popup,width=600,height=720')
    if (popup) popup.opener = null
    const state = { popup, configName: config.value, attemptId: null }
    active = state
    showPending(true)
    showStatus('Starting Plex sign-in...')
    try {
      const { response, data } = await requestAuth('start', state)
      state.attemptId = data.attempt_id
      if (active !== state) {
        cleanupAttempt(state)
        return
      }
      if (!response.ok || !data.auth_url || !state.attemptId) {
        finish(state)
        showStatus(data.error || 'Unable to start Plex sign-in. Please try again.', true)
        return
      }
      state.expiresAt = Date.now() + data.expires_in * 1000
      openPlex.href = data.auth_url
      openPlex.classList.remove('d-none')
      if (popup && !popup.closed) popup.location = data.auth_url
      showStatus('Waiting for Plex approval...')
      state.timer = setTimeout(() => poll(state), 2000)
    } catch {
      if (active !== state) return
      finish(state)
      showStatus('Unable to start Plex sign-in. Please try again.', true)
    }
  })

  cancel.addEventListener('click', () => {
    if (active) finish(active)
    showStatus('Plex sign-in cancelled.')
  })
  url.addEventListener('input', () => { if (active) validate.disabled = true })
  validate.addEventListener('click', event => {
    if (active) event.stopImmediatePropagation()
  }, true)
  function resumePolling () {
    if (!active || !active.attemptId || active.controller) return
    clearTimeout(active.timer)
    poll(active)
  }
  window.addEventListener('focus', resumePolling)
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') resumePolling()
  })
  window.addEventListener('pagehide', () => { if (active) finish(active) })
  document.getElementById('configForm')?.addEventListener('submit', () => {
    if (active) finish(active)
  })
}

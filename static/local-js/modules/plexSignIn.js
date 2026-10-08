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
  const serverPicker = document.getElementById('plexServerPicker')
  const serverSelect = document.getElementById('plexServerSelect')
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
      serverPicker?.classList.add('d-none')
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

  async function requestAuth (endpoint, state, extra = {}) {
    const controller = new AbortController()
    // Let a cancelled start finish so its returned attempt ID can be cleaned up.
    if (endpoint !== 'start') state.controller = controller
    const timeout = setTimeout(() => controller.abort(), 25000)
    try {
      const response = await fetch(`/plex-auth/${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ config_name: state.configName, attempt_id: state.attemptId, ...extra }),
        signal: controller.signal
      })
      const data = await response.json()
      return { response, data }
    } finally {
      clearTimeout(timeout)
      if (state.controller === controller) state.controller = null
    }
  }

  function isCurrent (state) {
    if (active !== state) return false
    if (config.value !== state.configName) {
      finish(state)
      showStatus('The selected configuration changed. Please start Plex sign-in again.', true)
      return false
    }
    return true
  }

  function completeSignIn (state, message, discoveredUrl) {
    finish(state)
    if (discoveredUrl && !url.value.trim()) {
      url.value = discoveredUrl
      url.dispatchEvent(new Event('input', { bubbles: true }))
    }
    showStatus(message || `Signed in as ${state.username}.`)
    if (url.value.trim()) validate.click()
    else url.focus()
  }

  async function connectServer (state, serverId) {
    if (!isCurrent(state)) return
    if (serverSelect) serverSelect.disabled = true
    spinner?.classList.remove('d-none')
    showStatus('Connecting to Plex server...')
    try {
      const { response, data } = await requestAuth('connect', state, { server_id: serverId })
      if (!isCurrent(state)) return
      if (!response.ok || !data.url) throw new Error(data.error)
      completeSignIn(state, null, data.url)
    } catch {
      if (!isCurrent(state)) return
      finish(state)
      showStatus(`Signed in as ${state.username}. Quickstart could not connect to the server. Enter your Plex server URL, then validate.`, true)
      url.focus()
    }
  }

  async function discoverServers (state) {
    showStatus('Finding Plex servers...')
    try {
      const { response, data } = await requestAuth('servers', state)
      if (!isCurrent(state)) return
      if (url.value.trim()) {
        completeSignIn(state)
        return
      }
      if (!response.ok || !Array.isArray(data.servers)) throw new Error(data.error)
      if (data.servers.length === 1) {
        await connectServer(state, data.servers[0].id)
      } else if (data.servers.length > 1 && serverPicker && serverSelect) {
        serverSelect.replaceChildren(new window.Option('Select a server', ''))
        for (const server of data.servers) serverSelect.add(new window.Option(server.name, server.id))
        serverSelect.disabled = false
        serverPicker.classList.remove('d-none')
        spinner?.classList.add('d-none')
        showStatus(`Signed in as ${state.username}. Select your Plex server.`)
        serverSelect.focus()
        state.timer = setTimeout(() => {
          if (!isCurrent(state)) return
          finish(state)
          showStatus('Server selection expired. Enter your Plex server URL, then validate.', true)
        }, Math.max(0, state.expiresAt - Date.now()))
      } else {
        completeSignIn(state, `Signed in as ${state.username}. No owned Plex servers found. Enter your Plex server URL, then validate.`)
      }
    } catch {
      if (!isCurrent(state)) return
      finish(state)
      showStatus(`Signed in as ${state.username}. Server discovery is unavailable. Enter your Plex server URL, then validate.`, true)
      url.focus()
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
        state.authenticated = true
        state.username = data.username || 'Plex account'
        closePopup(state)
        openPlex.classList.add('d-none')
        token.value = data.token
        token.type = 'password'
        setToggleButtonIcon(document.getElementById('toggleApikeyVisibility'), false)
        token.dispatchEvent(new Event('input', { bubbles: true }))
        validate.disabled = true
        if (url.value.trim()) completeSignIn(state)
        else await discoverServers(state)
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
    const authenticated = active?.authenticated
    if (active) finish(active)
    showStatus(authenticated ? 'Server discovery cancelled. Enter your Plex server URL, then validate.' : 'Plex sign-in cancelled.')
  })
  serverSelect?.addEventListener('change', () => {
    if (active?.authenticated && serverSelect.value) connectServer(active, serverSelect.value)
  })
  url.addEventListener('input', () => {
    if (active?.authenticated) {
      finish(active)
      showStatus('Signed in. Validate your Plex server URL.')
    } else if (active) validate.disabled = true
  })
  validate.addEventListener('click', event => {
    if (active) event.stopImmediatePropagation()
  }, true)
  function resumePolling () {
    if (!active || active.authenticated || !active.attemptId || active.controller) return
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

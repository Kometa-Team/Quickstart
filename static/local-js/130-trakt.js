const TRAKT_UTILITIES_URL = 'https://utilities.kometa.wiki/trakt-oauth/'
function setTraktAuthFields (traktPayload) {
  if (!traktPayload) return
  const auth = traktPayload.authorization || {}
  const clientIdInput = document.getElementById('trakt_client_id')
  const clientSecretInput = document.getElementById('trakt_client_secret')
  const accessTokenInput = document.getElementById('access_token')
  const tokenTypeInput = document.getElementById('token_type')
  const expiresInInput = document.getElementById('expires_in')
  const refreshTokenInput = document.getElementById('refresh_token')
  const scopeInput = document.getElementById('scope')
  const createdAtInput = document.getElementById('created_at')

  if (clientIdInput) clientIdInput.value = traktPayload.client_id || ''
  if (clientSecretInput) clientSecretInput.value = traktPayload.client_secret || ''
  if (accessTokenInput) accessTokenInput.value = auth.access_token || ''
  if (tokenTypeInput) tokenTypeInput.value = auth.token_type || ''
  if (expiresInInput) expiresInInput.value = auth.expires_in || ''
  if (refreshTokenInput) refreshTokenInput.value = auth.refresh_token || ''
  if (scopeInput) scopeInput.value = auth.scope || ''
  if (createdAtInput) createdAtInput.value = auth.created_at || ''
}

function showTraktStatus (message, type = 'info') {
  const statusEl = document.getElementById('traktYamlImportStatus')
  if (!statusEl) return
  statusEl.className = `alert alert-${type} py-2 small mt-3`
  statusEl.textContent = message
  statusEl.classList.remove('d-none')
}

function wireYamlImportFlow () {
  const importButton = document.getElementById('traktYamlImportSubmit')
  const importText = document.getElementById('traktYamlImportText')
  const openUtilitiesButton = document.getElementById('trakt_open_url')
  const checkTokenButton = document.getElementById('trakt_check_token')

  if (openUtilitiesButton) {
    openUtilitiesButton.addEventListener('click', () => {
      window.open(TRAKT_UTILITIES_URL, '_blank', 'noopener,noreferrer')
    })
  }

  if (!importButton || !importText) {
    console.error('[Trakt] Cannot wire import flow: button=' + !!importButton + ', text=' + !!importText)
    return
  }

  if (importButton && importText) {
    importButton.addEventListener('click', async () => {
      const yaml = importText.value.trim()
      if (!yaml) {
        showTraktStatus('Paste the YAML export before importing.', 'danger')
        return
      }

      showTraktStatus('Importing Trakt credentials...', 'info')

      try {
        const response = await fetch('/import_trakt_yaml', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ yaml })
        })
        const data = await response.json()
        if (!response.ok || !data.valid) {
          showTraktStatus(data.error || 'The YAML import failed.', 'danger')
          return
        }

        setTraktAuthFields(data.trakt)
        showTraktStatus('Trakt credentials imported successfully.', 'success')
        const modalEl = document.getElementById('traktYamlImportModal')
        if (modalEl && window.bootstrap) {
          const modal = window.bootstrap.Modal.getOrCreateInstance(modalEl)
          modal.hide()
        }
      } catch {
        showTraktStatus('Unable to import the Trakt YAML right now.', 'danger')
      }
    })
  }

  if (checkTokenButton) {
    checkTokenButton.addEventListener('click', async () => {
      const accessToken = document.getElementById('access_token')?.value || ''
      const clientId = document.getElementById('trakt_client_id')?.value || ''
      const clientSecret = document.getElementById('trakt_client_secret')?.value || ''
      const refreshToken = document.getElementById('refresh_token')?.value || ''

      if (!accessToken || !clientId || !clientSecret || !refreshToken) {
        showTraktStatus('Missing access token, client ID, client secret, or refresh token.', 'danger')
        return
      }

      showTraktStatus('Checking Trakt token...', 'info')

      try {
        const response = await fetch('/validate_trakt_token', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            access_token: accessToken,
            client_id: clientId,
            client_secret: clientSecret,
            refresh_token: refreshToken,
            debug: true
          })
        })
        const data = await response.json()
        if (!response.ok || !data.valid) {
          showTraktStatus(data.error || 'Token check failed.', 'danger')
          return
        }

        if (data.authorization) {
          setTraktAuthFields({ client_id: clientId, client_secret: clientSecret, authorization: data.authorization })
        }
        showTraktStatus('Trakt token is valid.', 'success')
      } catch {
        showTraktStatus('Unable to validate the Trakt token right now.', 'danger')
      }
    })
  }
}

wireYamlImportFlow()

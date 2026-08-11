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

  if (clientIdInput) {
    clientIdInput.value = traktPayload.client_id || ''
  }

  if (clientSecretInput) {
    clientSecretInput.value = traktPayload.client_secret || ''
  }

  if (accessTokenInput) {
    accessTokenInput.value = auth.access_token || ''
  }

  if (tokenTypeInput) {
    tokenTypeInput.value = auth.token_type || ''
  }

  if (expiresInInput) {
    expiresInInput.value = auth.expires_in || ''
  }

  if (refreshTokenInput) {
    refreshTokenInput.value = auth.refresh_token || ''
  }

  if (scopeInput) {
    scopeInput.value = auth.scope || ''
  }

  if (createdAtInput) {
    createdAtInput.value = auth.created_at || ''
  }
}

function showTraktStatus (message, type = 'info') {
  const statusEl = document.getElementById('traktYamlImportStatus')

  if (!statusEl) {
    console.error('[Trakt] Status element not found')
    return
  }

  statusEl.className = `alert alert-${type} py-2 small mt-3`
  statusEl.textContent = message
  statusEl.classList.remove('d-none')
}

async function importTraktYaml () {
  console.log('[Trakt] Import YAML handler called')

  const importText = document.getElementById('traktYamlImportText')

  if (!importText) {
    console.error('[Trakt] traktYamlImportText was not found')
    return
  }

  const yaml = importText.value.trim()

  if (!yaml) {
    showTraktStatus(
      'Paste the YAML export before importing.',
      'danger'
    )
    return
  }

  showTraktStatus(
    'Importing Trakt credentials...',
    'info'
  )

  try {
    console.log('[Trakt] POST /import_trakt_yaml')

    const response = await fetch('/import_trakt_yaml', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        yaml
      })
    })

    console.log(
      '[Trakt] Import response status:',
      response.status
    )

    let data

    try {
      data = await response.json()
    } catch (error) {
      console.error(
        '[Trakt] Unable to parse import response:',
        error
      )

      showTraktStatus(
        `The server returned an invalid response (${response.status}).`,
        'danger'
      )
      return
    }

    console.log(
      '[Trakt] Import response:',
      data
    )

    if (!response.ok || !data.valid) {
      showTraktStatus(
        data.error || 'The YAML import failed.',
        'danger'
      )
      return
    }

    setTraktAuthFields(data.trakt)

    showTraktStatus(
      'Trakt credentials imported successfully.',
      'success'
    )

    const modalEl =
      document.getElementById('traktYamlImportModal')

    if (modalEl && window.bootstrap) {
      const modal =
        window.bootstrap.Modal.getOrCreateInstance(modalEl)

      modal.hide()
    }
  } catch (error) {
    console.error(
      '[Trakt] YAML import request failed:',
      error
    )

    showTraktStatus(
      'Unable to import the Trakt YAML right now.',
      'danger'
    )
  }
}

async function checkTraktToken () {
  console.log('[Trakt] Check Token handler called')

  const accessToken =
    document.getElementById('access_token')?.value || ''

  const clientId =
    document.getElementById('trakt_client_id')?.value || ''

  const clientSecret =
    document.getElementById('trakt_client_secret')?.value || ''

  const refreshToken =
    document.getElementById('refresh_token')?.value || ''

  if (
    !accessToken ||
    !clientId ||
    !clientSecret ||
    !refreshToken
  ) {
    showTraktStatus(
      'Missing access token, client ID, client secret, or refresh token.',
      'danger'
    )
    return
  }

  showTraktStatus(
    'Checking Trakt token...',
    'info'
  )

  try {
    console.log('[Trakt] POST /validate_trakt_token')

    const response = await fetch(
      '/validate_trakt_token',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          access_token: accessToken,
          client_id: clientId,
          client_secret: clientSecret,
          refresh_token: refreshToken,
          debug: true
        })
      }
    )

    console.log(
      '[Trakt] Token response status:',
      response.status
    )

    let data

    try {
      data = await response.json()
    } catch (error) {
      console.error(
        '[Trakt] Unable to parse token response:',
        error
      )

      showTraktStatus(
        `The server returned an invalid response (${response.status}).`,
        'danger'
      )
      return
    }

    console.log(
      '[Trakt] Token response:',
      data
    )

    if (!response.ok || !data.valid) {
      showTraktStatus(
        data.error || 'Token check failed.',
        'danger'
      )
      return
    }

    if (data.authorization) {
      setTraktAuthFields({
        client_id: clientId,
        client_secret: clientSecret,
        authorization: data.authorization
      })
    }

    showTraktStatus(
      'Trakt token is valid.',
      'success'
    )
  } catch (error) {
    console.error(
      '[Trakt] Token validation request failed:',
      error
    )

    showTraktStatus(
      'Unable to validate the Trakt token right now.',
      'danger'
    )
  }
}

console.log('[Trakt] 130-trakt.js loaded')

document.addEventListener('click', async (event) => {
  const importButton =
    event.target.closest('#traktYamlImportSubmit')

  if (importButton) {
    event.preventDefault()

    console.log('[Trakt] Import YAML button clicked')

    await importTraktYaml()
    return
  }

  const checkTokenButton =
    event.target.closest('#trakt_check_token')

  if (checkTokenButton) {
    event.preventDefault()

    console.log('[Trakt] Check Token button clicked')

    await checkTraktToken()
  }
})

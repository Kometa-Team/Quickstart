import { refreshValidationCallout } from './modules/validationPageBase.js'
import {
  STATUS_COLOR_SUCCESS,
  STATUS_COLOR_ERROR,
  wireSecretToggle,
  showStatusMessage,
  performValidationRequest
} from './modules/oauthValidationHelpers.js'

console.log('[Trakt] 130-trakt.js loaded')

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

function markTraktValidated () {
  const validatedField = document.getElementById('trakt_validated')
  const validatedAtField = document.getElementById('trakt_validated_at')

  if (validatedField) {
    validatedField.value = 'true'
  }

  if (validatedAtField) {
    validatedAtField.value = new Date().toISOString()
  }

  refreshValidationCallout('trakt_validated')
}

function markTraktInvalid () {
  const validatedField = document.getElementById('trakt_validated')
  const validatedAtField = document.getElementById('trakt_validated_at')

  if (validatedField) {
    validatedField.value = 'false'
  }

  if (validatedAtField) {
    validatedAtField.value = ''
  }

  refreshValidationCallout('trakt_validated')
}

function showYamlImportStatus (message, type = 'info') {
  const statusElement = document.getElementById('traktYamlImportStatus')

  if (!statusElement) {
    console.error('[Trakt] YAML import status element not found')
    return
  }

  statusElement.className = `alert alert-${type} py-2 small mt-3`
  statusElement.textContent = message
  statusElement.classList.remove('d-none')
}

function resetYamlImportStatus () {
  const statusElement = document.getElementById('traktYamlImportStatus')

  if (!statusElement) return

  statusElement.textContent = ''
  statusElement.className = 'alert alert-info py-2 small mt-3 d-none'
}

async function importTraktYaml () {
  const importText = document.getElementById('traktYamlImportText')
  const importButton = document.getElementById('traktYamlImportSubmit')

  console.log('[Trakt] Import YAML handler called')

  if (!importText) {
    console.error('[Trakt] traktYamlImportText not found')
    return
  }

  const yaml = importText.value.trim()

  if (!yaml) {
    showYamlImportStatus(
      'Paste the YAML export before importing.',
      'danger'
    )
    return
  }

  if (importButton) {
    importButton.disabled = true
  }

  showYamlImportStatus(
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
        '[Trakt] Unable to parse YAML import response:',
        error
      )

      showYamlImportStatus(
        `The server returned an invalid response (${response.status}).`,
        'danger'
      )
      return
    }

    console.log('[Trakt] Import response:', data)

    if (!response.ok || !data.valid) {
      showYamlImportStatus(
        data.error || 'The YAML import failed.',
        'danger'
      )
      return
    }

    setTraktAuthFields(data.trakt)
    markTraktValidated()

    showYamlImportStatus(
      'Trakt credentials imported successfully.',
      'success'
    )

    const checkTokenButton =
      document.getElementById('trakt_check_token')

    if (checkTokenButton) {
      checkTokenButton.disabled = false
    }

    /*
     * Keep the success message visible briefly in the modal rather than
     * immediately hiding it. The user can close the modal manually.
     *
     * We intentionally do not call modal.hide() here because hiding the
     * modal immediately makes a successful import appear as though
     * nothing happened.
     */
  } catch (error) {
    console.error(
      '[Trakt] YAML import request failed:',
      error
    )

    showYamlImportStatus(
      'Unable to import the Trakt YAML right now.',
      'danger'
    )
  } finally {
    if (importButton) {
      importButton.disabled = false
    }
  }
}

function checkTraktToken () {
  const statusMessage =
    document.getElementById('statusMessage')

  const accessToken =
    document.getElementById('access_token')?.value || ''

  const clientId =
    document.getElementById('trakt_client_id')?.value || ''

  const clientSecret =
    document.getElementById('trakt_client_secret')?.value || ''

  const refreshToken =
    document.getElementById('refresh_token')?.value || ''

  if (
    !accessToken.trim() ||
    !clientId.trim() ||
    !clientSecret.trim() ||
    !refreshToken.trim()
  ) {
    showStatusMessage(
      statusMessage,
      'Missing access token, client ID, client secret, or refresh token.',
      STATUS_COLOR_ERROR
    )
    return
  }

  console.log('[Trakt] POST /validate_trakt_token')

  performValidationRequest({
    endpoint: '/validate_trakt_token',
    payload: {
      access_token: accessToken,
      client_id: clientId,
      client_secret: clientSecret,
      refresh_token: refreshToken,
      debug: true
    },
    spinnerKey: 'check_trakt',
    statusElement: statusMessage,

    onSuccess: (data) => {
      console.log('[Trakt] Token validation succeeded:', data)

      if (data.authorization) {
        setTraktAuthFields({
          client_id: clientId,
          client_secret: clientSecret,
          authorization: data.authorization
        })
      }

      markTraktValidated()

      showStatusMessage(
        statusMessage,
        'Trakt token is valid.',
        STATUS_COLOR_SUCCESS
      )
    },

    onFailure: (data) => {
      console.error(
        '[Trakt] Token validation failed:',
        data
      )

      markTraktInvalid()
    },

    onError: (error) => {
      console.error(
        '[Trakt] Token validation request error:',
        error
      )

      markTraktInvalid()

      showStatusMessage(
        statusMessage,
        'An error occurred while validating the Trakt token.',
        STATUS_COLOR_ERROR
      )
    }
  })
}

function wireTraktPage () {
  const clientSecretInput =
    document.getElementById('trakt_client_secret')

  const secretToggleButton =
    document.getElementById('toggleClientSecretVisibility')

  const importButton =
    document.getElementById('traktYamlImportSubmit')

  const importText =
    document.getElementById('traktYamlImportText')

  const importModal =
    document.getElementById('traktYamlImportModal')

  const checkTokenButton =
    document.getElementById('trakt_check_token')

  console.log('[Trakt] Wiring page', {
    clientSecretInput: !!clientSecretInput,
    importButton: !!importButton,
    importText: !!importText,
    importModal: !!importModal,
    checkTokenButton: !!checkTokenButton
  })

  if (clientSecretInput) {
    wireSecretToggle(
      clientSecretInput,
      secretToggleButton
    )
  }

  if (importButton) {
    importButton.addEventListener(
      'click',
      importTraktYaml
    )
  } else {
    console.error(
      '[Trakt] traktYamlImportSubmit not found'
    )
  }

  if (importModal) {
    importModal.addEventListener(
      'show.bs.modal',
      resetYamlImportStatus
    )
  }

  if (checkTokenButton) {
    checkTokenButton.addEventListener(
      'click',
      checkTraktToken
    )

    const accessToken =
      document.getElementById('access_token')?.value || ''

    checkTokenButton.disabled =
      !accessToken.trim()
  }
}

wireTraktPage()

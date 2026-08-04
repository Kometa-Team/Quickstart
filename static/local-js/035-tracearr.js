import { createApiKeyValidator } from './modules/createApiKeyValidator.js'

const serverSelect = document.getElementById('tracearr_server_id')

serverSelect?.addEventListener('change', () => {
  const validated = document.getElementById('tracearr_validated')
  const validatedAt = document.getElementById('tracearr_validated_at')
  const validateButton = document.getElementById('validateButton')
  const statusMessage = document.getElementById('statusMessage')
  if (validated) validated.value = 'false'
  if (validatedAt) validatedAt.value = ''
  if (validateButton) validateButton.disabled = false
  if (statusMessage) statusMessage.textContent = 'Plex server selection changed. Validate Tracearr again.'
})

function renderServers (servers = []) {
  if (!serverSelect) return
  const selected = serverSelect.value || serverSelect.dataset.currentValue || ''
  serverSelect.replaceChildren(new Option('Auto-detect by Plex server name', ''))
  servers.forEach(server => {
    const id = String(server?.id || '')
    if (!id) return
    const name = String(server?.name || 'Unnamed Plex server')
    serverSelect.add(new Option(`${name} (${id})`, id, false, id === selected))
  })
  if (selected && !Array.from(serverSelect.options).some(option => option.value === selected)) {
    serverSelect.add(new Option(selected, selected, true, true))
  }
}

createApiKeyValidator({
  fieldId: 'tracearr_apikey',
  additionalFieldIds: ['tracearr_url'],
  validatedFieldId: 'tracearr_validated',
  validatedAtFieldId: 'tracearr_validated_at',
  endpoint: '/validate_tracearr',
  buildPayload: (apiKey, extras) => ({
    tracearr_url: extras.tracearr_url,
    tracearr_apikey: apiKey,
    tracearr_server_id: serverSelect?.value || ''
  }),
  onValidationSuccess: payload => renderServers(payload.servers),
  revalidateOnLoad: true,
  messages: {
    empty: 'Please enter both Tracearr URL and Public API Key.',
    success: 'Tracearr validated successfully.',
    failure: 'Failed to validate Tracearr. Check the URL, Public API key, and Plex server selection.',
    networkError: 'An error occurred while validating Tracearr.'
  }
})

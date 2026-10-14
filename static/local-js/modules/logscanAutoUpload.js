import { getAppConfig, setAppConfig } from './appConfig.js'

export function initLogscanAutoUpload () {
  document.querySelectorAll('[data-logscan-auto-upload]').forEach(input => {
    if (input.dataset.logscanAutoUploadBound) return
    const tool = input.dataset.logscanAutoUpload
    if (!['kometa', 'imagemaid'].includes(tool)) return
    input.dataset.logscanAutoUploadBound = 'true'
    const key = `QS_LOGSCAN_AUTO_UPLOAD_${tool.toUpperCase()}`
    const field = `logscan_auto_upload_${tool}`
    const dataset = `currentAutoUpload${tool === 'kometa' ? 'Kometa' : 'Imagemaid'}`
    const settingsInput = document.getElementById(`quickstart-settings-auto-upload-${tool}`)
    const trigger = document.getElementById('quickstart-settings-btn')
    const status = document.getElementById(`${input.id}-status`)
    const sync = () => { input.checked = String(getAppConfig(key, false)).toLowerCase() === 'true' }
    sync()
    document.addEventListener('quickstart-settings-change', () => {
      if (input.isConnected && !input.disabled) sync()
    })
    input.addEventListener('change', async () => {
      const enabled = input.checked
      input.disabled = true
      if (settingsInput) settingsInput.disabled = true
      status.textContent = 'Saving...'
      status.classList.remove('text-danger')
      try {
        const response = await fetch('/update-quickstart-settings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ [field]: enabled })
        })
        const data = await response.json()
        if (!response.ok || !data.success || typeof data[field] !== 'boolean') {
          throw new Error(data.message || 'Could not save automatic uploads. Try again.')
        }
        setAppConfig({ [key]: data[field] })
        if (trigger) trigger.dataset[dataset] = String(data[field])
        if (settingsInput) settingsInput.checked = data[field]
        status.textContent = 'Saved.'
        document.dispatchEvent(new CustomEvent('quickstart-settings-change'))
      } catch (error) {
        status.textContent = error.message
        status.classList.add('text-danger')
      } finally {
        input.disabled = false
        if (settingsInput) settingsInput.disabled = false
        sync()
      }
    })
  })
}

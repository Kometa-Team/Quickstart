export function renderKometaIntegrity (report, lines = []) {
  const panel = document.getElementById('kometa-integrity-panel')
  const details = document.getElementById('kometa-integrity-details')
  if (!panel || !details || !report) return
  const style = report.state === 'clean' ? 'alert-success' : (report.state === 'not_applicable' ? 'alert-secondary' : 'alert-warning')
  panel.classList.remove('alert-success', 'alert-secondary', 'alert-warning')
  panel.classList.add(style)
  details.textContent = Array.isArray(lines) && lines.length ? lines.join('\n') : `Kometa Integrity: ${String(report.state || 'not_verified').replaceAll('_', ' ').toUpperCase()}`
}

export async function refreshKometaIntegrity () {
  const button = document.getElementById('refresh-kometa-integrity')
  if (button?.disabled) return
  if (button) button.disabled = true
  try {
    const response = await fetch('/kometa-integrity')
    if (!response.ok) throw new Error('Integrity check failed')
    const data = await response.json()
    renderKometaIntegrity(data.integrity, data.integrity_lines)
  } catch {
    renderKometaIntegrity({ state: 'check_failed' }, ['Kometa Integrity: CHECK FAILED', 'Unable to refresh integrity diagnostics.'])
  } finally {
    if (button) button.disabled = false
  }
}

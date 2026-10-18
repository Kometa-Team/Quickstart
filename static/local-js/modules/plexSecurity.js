// The backend evaluates advisories. This module only presents their status.
export function renderPlexSecurity (assessments) {
  const target = document.getElementById('plex-security-status')
  if (!target) return
  target.replaceChildren()
  target.className = 'small text-body-secondary mb-2'
  target.setAttribute('role', 'status')
  if (!Array.isArray(assessments) || !assessments.length) {
    target.textContent = 'Plex advisory status unknown. Validate the connection to check the installed version.'
    return
  }
  const affected = assessments.some(item => item.status === 'affected')
  if (affected) {
    target.className = 'alert alert-danger mb-3'
    target.setAttribute('role', 'alert')
  }
  for (const item of assessments) {
    const row = document.createElement('div')
    const version = item.detected_version || 'unavailable'
    const patched = item.minimum_patched_version
    if (item.status === 'affected') {
      row.textContent = `Security update required: installed Plex Media Server ${version}. Update Plex Media Server to ${patched} or newer. Critical is Kometa's recommendation severity, not an official CVSS rating. `
    } else if (item.status === 'patched') {
      row.textContent = `Installed Plex Media Server ${version} addresses ${item.advisory_id} (minimum ${patched}). This status covers this advisory only. `
    } else {
      row.textContent = `Plex advisory ${item.advisory_id}: unknown. Installed version: ${version}. Minimum patched version: ${patched}. `
    }
    const link = document.createElement('a')
    link.href = item.advisory_url
    link.target = '_blank'
    link.rel = 'noopener noreferrer'
    link.textContent = 'Official Plex advisory'
    row.append(link)
    target.append(row)
  }
}

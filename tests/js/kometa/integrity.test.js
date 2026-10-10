import { beforeEach, describe, expect, it, vi } from 'vitest'
import { refreshKometaIntegrity, renderKometaIntegrity } from '../../../static/local-js/modules/kometa/_integrity.js'

beforeEach(() => {
  document.body.innerHTML = '<div id="kometa-integrity-panel" class="alert alert-success"><div id="kometa-integrity-details"></div></div><button id="refresh-kometa-integrity"></button>'
  vi.restoreAllMocks()
  global.fetch = vi.fn()
})

describe('Kometa integrity diagnostics', () => {
  it.each(['modified', 'not_verified', 'check_failed'])('shows %s as a warning without changing run controls', (state) => {
    document.body.insertAdjacentHTML('beforeend', '<button id="run-now">Run</button>')
    renderKometaIntegrity({ state }, ['WARNING', 'Modified: defaults/overlays/images/rating.png'])
    expect(document.getElementById('kometa-integrity-panel').classList.contains('alert-warning')).toBe(true)
    expect(document.getElementById('run-now').disabled).toBe(false)
  })

  it('replaces a warning after a clean check', () => {
    renderKometaIntegrity({ state: 'modified' }, ['Modified'])
    renderKometaIntegrity({ state: 'clean' }, ['Kometa Integrity: CLEAN'])
    expect(document.getElementById('kometa-integrity-panel').classList.contains('alert-warning')).toBe(false)
    expect(document.getElementById('kometa-integrity-panel').classList.contains('alert-success')).toBe(true)
  })

  it('renders unmanaged installs as not applicable', () => {
    renderKometaIntegrity({ state: 'not_applicable' }, ['Not applicable'])
    expect(document.getElementById('kometa-integrity-panel').classList.contains('alert-secondary')).toBe(true)
  })

  it('renders filenames as text, never HTML', () => {
    renderKometaIntegrity({ state: 'modified' }, ['Added: <img src=x onerror=alert(1)>'])
    expect(document.querySelector('img')).toBeNull()
    expect(document.getElementById('kometa-integrity-details').textContent).toContain('<img')
  })

  it('refreshes through the read-only endpoint and re-enables the button', async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ integrity: { state: 'modified' }, integrity_lines: ['Modified image'] }) })
    await refreshKometaIntegrity()
    expect(global.fetch).toHaveBeenCalledWith('/kometa-integrity')
    expect(document.getElementById('kometa-integrity-details').textContent).toBe('Modified image')
    expect(document.getElementById('refresh-kometa-integrity').disabled).toBe(false)
  })

  it('never leaves a stale clean state when refresh fails', async () => {
    global.fetch.mockRejectedValue(new Error('offline'))
    await refreshKometaIntegrity()
    expect(document.getElementById('kometa-integrity-details').textContent).toContain('CHECK FAILED')
    expect(document.getElementById('refresh-kometa-integrity').disabled).toBe(false)
  })

  it('works when the panel is absent', () => {
    document.body.innerHTML = ''
    expect(() => renderKometaIntegrity({ state: 'clean' }, ['Clean'])).not.toThrow()
  })
})

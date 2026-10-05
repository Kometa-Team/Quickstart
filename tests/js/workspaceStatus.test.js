import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

beforeAll(async () => {
  window.QS_DEBUG = true
  await import('../../static/local-js/000-base.js')
})

const requiredKeys = ['001-start', '020-tmdb']
const optionalKeys = ['050-omdb', '060-mdblist', '070-notifiarr']

function stepLink (key) {
  return `<button class="qs-step-link" data-step-key="${key}"><span class="qs-step-link-state qs-step-link-state--unknown"></span></button>`
}

function payload (overrides = {}) {
  return {
    required_keys: requiredKeys,
    optional_keys: optionalKeys,
    review_keys: [],
    step_statuses: Object.fromEntries([...requiredKeys, ...optionalKeys].map(key => [key, 'unknown'])),
    ...overrides
  }
}

function removedSteps (apply) {
  const observer = new MutationObserver(() => {})
  observer.observe(document.body, { childList: true, subtree: true })
  apply()
  const removed = observer.takeRecords().flatMap(record => Array.from(record.removedNodes))
    .filter(node => node.matches?.('.qs-step-link'))
  observer.disconnect()
  return removed
}

beforeEach(() => {
  window.QS_CURRENT_TEMPLATE = '020-tmdb'
  window.QS_STEP_STATUSES = {}
  document.body.innerHTML = `
    <div class="qs-workspace-section" data-current-step="020-tmdb">
      <input type="hidden" id="tmdb_validated" value="true">
      <details class="qs-step-group" data-step-group="required" open>
        <div class="qs-step-group-list"><div class="qs-step-subgroup" data-step-keys="001-start 020-tmdb 050-omdb 060-mdblist 070-notifiarr">
          <div class="qs-step-subgroup-list">${requiredKeys.map(stepLink).join('')}</div>
        </div></div>
      </details>
      <details class="qs-step-group" data-step-group="optional">
        <div class="qs-step-group-list"><div class="qs-step-subgroup" data-step-keys="050-omdb 060-mdblist 070-notifiarr">
          <div class="qs-step-subgroup-list">${optionalKeys.map(stepLink).join('')}</div>
        </div></div>
      </details>
      <details class="qs-step-group" data-step-group="review"><div class="qs-step-group-list"></div></details>
    </div>`
})

afterEach(() => {
  vi.restoreAllMocks()
  document.body.innerHTML = ''
})

describe('workspace status reconciliation', () => {
  it.each(['010-plex', '020-tmdb', '025-libraries', '050-omdb', '060-mdblist', '070-notifiarr', '110-radarr', '140-mal'])(
    'preserves unsaved validation on %s without scheduling another refresh', (key) => {
      window.QS_CURRENT_TEMPLATE = key
      document.querySelector('.qs-workspace-section').dataset.currentStep = key
      document.querySelector('input').id = `${key.split('-')[1]}_validated`
      if (!document.querySelector(`[data-step-key="${key}"]`)) {
        document.querySelector('.qs-workspace-section').insertAdjacentHTML('beforeend', stepLink(key))
      }
      const refresh = vi.spyOn(window.QSWorkspaceStatus, 'refresh').mockImplementation(() => {})

      const status = payload({ step_statuses: { ...payload().step_statuses, [key]: 'unknown' } })
      window.QSWorkspaceStatus.apply(status)
      window.QSWorkspaceStatus.apply(status)

      expect(window.QS_STEP_STATUSES[key]).toBe('ok')
      expect(refresh).not.toHaveBeenCalled()
    }
  )

  it('still requests a refresh when the user changes local validation', () => {
    window.QSWorkspaceStatus.apply(payload())
    const refresh = vi.spyOn(window.QSWorkspaceStatus, 'refresh').mockImplementation(() => {})
    document.getElementById('tmdb_validated').value = 'false'

    window.QSValidationCallouts.refresh('tmdb_validated')

    expect(refresh).toHaveBeenCalledWith({ reason: 'validation-state-change', delayMs: 120 })
    expect(window.QS_STEP_STATUSES['020-tmdb']).toBe('error')
  })

  it('does not detach correctly positioned buttons on repeated status updates', () => {
    window.QSWorkspaceStatus.apply(payload())
    expect(removedSteps(() => window.QSWorkspaceStatus.apply(payload()))).toEqual([])
  })

  it('preserves unsaved validation failures without requesting another refresh', () => {
    document.getElementById('tmdb_validated').value = 'false'
    const refresh = vi.spyOn(window.QSWorkspaceStatus, 'refresh').mockImplementation(() => {})
    window.QSWorkspaceStatus.apply(payload({ step_statuses: { '020-tmdb': 'ok' } }))
    expect(window.QS_STEP_STATUSES['020-tmdb']).toBe('error')
    expect(refresh).not.toHaveBeenCalled()
  })

  it('keeps fallback subgroup buttons attached without an explicit subgroup order', () => {
    const subgroup = document.querySelector('[data-step-group="optional"] .qs-step-subgroup')
    subgroup.removeAttribute('data-step-keys')
    subgroup.dataset.stepSubgroup = 'other'
    window.QSWorkspaceStatus.apply(payload())
    expect(removedSteps(() => window.QSWorkspaceStatus.apply(payload()))).toEqual([])
    expect(Array.from(subgroup.querySelector('.qs-step-subgroup-list').children).map(node => node.dataset.stepKey)).toEqual(optionalKeys)
  })

  it('moves dependency-required steps and restores their optional order', () => {
    const key = '060-mdblist'
    const promoted = payload({
      required_keys: [...requiredKeys, key],
      optional_keys: optionalKeys.filter(entry => entry !== key)
    })
    const link = document.querySelector(`[data-step-key="${key}"]`)
    window.QSWorkspaceStatus.apply(promoted)
    expect(link.closest('[data-step-group]').dataset.stepGroup).toBe('required')
    expect(removedSteps(() => window.QSWorkspaceStatus.apply(promoted))).toEqual([])

    window.QSWorkspaceStatus.apply(payload())
    expect(link.closest('[data-step-group]').dataset.stepGroup).toBe('optional')
    expect(Array.from(link.parentElement.children).map(node => node.dataset.stepKey)).toEqual(optionalKeys)
    expect(removedSteps(() => window.QSWorkspaceStatus.apply(payload()))).toEqual([])
  })

  it('opens the new group only when the active step changes groups', () => {
    window.QS_CURRENT_TEMPLATE = '060-mdblist'
    document.querySelector('.qs-workspace-section').dataset.currentStep = '060-mdblist'
    const required = document.querySelector('[data-step-group="required"]')
    required.open = false
    const promoted = payload({ required_keys: [...requiredKeys, '060-mdblist'], optional_keys: ['050-omdb', '070-notifiarr'] })
    window.QSWorkspaceStatus.apply(promoted)
    expect(required.open).toBe(true)

    required.open = false
    window.QSWorkspaceStatus.apply(promoted)
    expect(required.open).toBe(false)
  })

  it('keeps review buttons attached in their requested order', () => {
    const list = document.querySelector('[data-step-group="review"] .qs-step-group-list')
    list.innerHTML = stepLink('910-review') + stepLink('920-review')
    const status = payload({ review_keys: ['910-review', '920-review'] })
    expect(removedSteps(() => window.QSWorkspaceStatus.apply(status))).toEqual([])
    window.QSWorkspaceStatus.apply(payload({ review_keys: ['920-review', '910-review'] }))
    expect(Array.from(list.children).map(node => node.dataset.stepKey)).toEqual(['920-review', '910-review'])
    expect(removedSteps(() => window.QSWorkspaceStatus.apply(status))).toHaveLength(1)
  })
})

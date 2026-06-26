/* global CustomEvent */

(function () {
  const templateStringListPresetConfigs = {
    generic_text: {
      duplicateInsensitive: false,
      normalize: value => value,
      validate: value => {
        if (!value) return { valid: false, message: 'Enter a value before adding it.' }
        return { valid: true }
      }
    },
    name_like: {
      duplicateInsensitive: true,
      normalize: value => value.replace(/\s+/g, ' '),
      validate: value => {
        const normalized = String(value || '').trim()
        if (!normalized) return { valid: false, message: 'Enter a text value before adding it.' }
        try {
          if (!/[\p{L}\p{N}]/u.test(normalized)) {
            return { valid: false, message: 'Enter a text value with letters or numbers.' }
          }
          if (!/^[\p{L}\p{N} .,&'’:+\-/()!]+$/u.test(normalized)) {
            return { valid: false, message: 'Use letters, numbers, spaces, or common punctuation only.' }
          }
        } catch {
          if (!/[A-Za-z0-9]/.test(normalized)) {
            return { valid: false, message: 'Enter a text value with letters or numbers.' }
          }
          if (!/^[A-Za-z0-9 .,&':+\-/()!]+$/.test(normalized)) {
            return { valid: false, message: 'Use letters, numbers, spaces, or common punctuation only.' }
          }
        }
        return { valid: true }
      }
    },
    tmdb_collection_id: {
      duplicateInsensitive: true,
      normalize: value => value,
      lookupService: 'tmdb',
      validate: value => /^\d+$/.test(value)
        ? { valid: true }
        : { valid: false, message: 'Enter a numeric TMDb collection ID like 131292.' }
    },
    numeric_id: {
      duplicateInsensitive: true,
      normalize: value => value,
      lookupService: 'tmdb',
      validate: value => /^\d+$/.test(value)
        ? { valid: true }
        : { valid: false, message: 'Enter a numeric ID like 603 or 1399.' }
    },
    imdb_id_tmdb: {
      duplicateInsensitive: true,
      normalize: value => value.toLowerCase(),
      lookupService: 'tmdb',
      validate: value => /^tt\d{7,8}$/i.test(value)
        ? { valid: true }
        : { valid: false, message: 'Enter an IMDb ID like tt1234567 or tt12345678.' }
    },
    imdb_id_plex: {
      duplicateInsensitive: true,
      normalize: value => value.toLowerCase(),
      lookupService: 'plex',
      validate: value => /^tt\d{7,8}$/i.test(value)
        ? { valid: true }
        : { valid: false, message: 'Enter an IMDb ID like tt1234567 or tt12345678.' }
    },
    year: {
      duplicateInsensitive: true,
      normalize: value => value,
      validate: value => /^\d{4}$/.test(value)
        ? { valid: true }
        : { valid: false, message: 'Enter a 4-digit year like 2022.' }
    },
    decade: {
      duplicateInsensitive: true,
      normalize: value => value,
      validate: value => /^\d{3,4}0$/.test(value)
        ? { valid: true }
        : { valid: false, message: 'Enter a decade key ending in 0 like 2020.' }
    },
    language_code: {
      duplicateInsensitive: true,
      normalize: value => value.toLowerCase(),
      suggestions: ['en', 'fr', 'es', 'de', 'it', 'pt', 'ja', 'ko', 'zh', 'ru', 'ar', 'hi', 'fil', 'myn', 'rom', 'tai'],
      validate: value => /^[a-z]{2,3}$/.test(value)
        ? { valid: true }
        : { valid: false, message: 'Enter a 2 or 3 letter language code like fr or fil.' }
    },
    aspect_key: {
      duplicateInsensitive: true,
      normalize: value => value,
      suggestions: ['1.33', '1.65', '1.66', '1.78', '1.85', '2.2', '2.35', '2.77'],
      allowedValues: new Set(['1.33', '1.65', '1.66', '1.78', '1.85', '2.2', '2.35', '2.77']),
      validate: value => templateStringListPresetConfigs.aspect_key.allowedValues.has(value)
        ? { valid: true }
        : { valid: false, message: 'Enter a supported aspect ratio key like 1.78 or 2.35.' }
    },
    resolution_key: {
      duplicateInsensitive: true,
      normalize: value => value.toLowerCase(),
      suggestions: ['4k', '1080', '720', '480', '8k', '2k', '576', 'sd'],
      allowedValues: new Set(['4k', '1080', '720', '480', '8k', '2k', '144', '240', '360', '576', 'sd']),
      validate: value => templateStringListPresetConfigs.resolution_key.allowedValues.has(value)
        ? { valid: true }
        : { valid: false, message: 'Enter a supported resolution key like 4k, 1080, 720, 480, or sd.' }
    },
    streaming_key: {
      duplicateInsensitive: true,
      normalize: value => value.toLowerCase(),
      suggestions: ['netflix', 'disney', 'amazon', 'hulu', 'hbomax', 'paramount', 'peacock'],
      allowedValues: new Set(['channel4', 'appletv', 'bet', 'crave', 'crunchyroll', 'discovery', 'disney', 'itvx', 'hbomax', 'hayu', 'hulu', 'movistar', 'atresplayer', 'netflix', 'now', 'paramount', 'peacock', 'amazon', 'amc', 'filmin', 'youtube', 'tubi']),
      validate: value => templateStringListPresetConfigs.streaming_key.allowedValues.has(value)
        ? { valid: true }
        : { valid: false, message: 'Enter a supported streaming service key like netflix, disney, or amazon.' }
    },
    universe_key: {
      duplicateInsensitive: true,
      normalize: value => value.toLowerCase(),
      suggestions: ['mcu', 'star', 'trek', 'wizard', 'fast'],
      allowedValues: new Set(['avp', 'arrow', 'askew', 'conjuring', 'dca', 'dcu', 'fast', 'marvel', 'mcu', 'middle', 'rocky', 'trek', 'star', 'mummy', 'wizard', 'xmen']),
      validate: value => templateStringListPresetConfigs.universe_key.allowedValues.has(value)
        ? { valid: true }
        : { valid: false, message: 'Enter a supported universe key like mcu, star, trek, or wizard.' }
    },
    based_key: {
      duplicateInsensitive: true,
      normalize: value => value.toLowerCase(),
      suggestions: ['books', 'comics', 'true_story', 'video_games'],
      allowedValues: new Set(['books', 'comics', 'true_story', 'video_games']),
      validate: value => templateStringListPresetConfigs.based_key.allowedValues.has(value)
        ? { valid: true }
        : { valid: false, message: 'Enter a supported media outlet key like books or video_games.' }
    },
    seasonal_key: {
      duplicateInsensitive: true,
      normalize: value => value.toLowerCase(),
      suggestions: ['christmas', 'halloween', 'valentine', 'years', 'women'],
      allowedValues: new Set(['years', 'valentine', 'patrick', 'easter', 'mother', 'memorial', 'father', 'independence', 'labor', 'halloween', 'veteran', 'thanksgiving', 'christmas', 'aapi', 'disabilities', 'black_history', 'lgbtq', 'latinx', 'women']),
      validate: value => templateStringListPresetConfigs.seasonal_key.allowedValues.has(value)
        ? { valid: true }
        : { valid: false, message: 'Enter a supported seasonal key like halloween, christmas, or women.' }
    },
    content_rating: {
      duplicateInsensitive: true,
      normalize: value => value.replace(/\s+/g, ' '),
      validate: value => /^[A-Za-z0-9][A-Za-z0-9 +\-./()]*$/.test(value)
        ? { valid: true }
        : { valid: false, message: 'Enter a content rating like PG-13, TV-14, 15, or M.' }
    }
  }

  function inferTemplateStringListPreset (wrapper, input) {
    const explicitPreset = String(wrapper.dataset.validationPreset || input.dataset.validationPreset || '').trim()
    if (explicitPreset && templateStringListPresetConfigs[explicitPreset]) return explicitPreset

    const placeholder = String(input.getAttribute('placeholder') || '').trim().toLowerCase()
    if (placeholder.includes('tmdb collection id')) return 'tmdb_collection_id'
    if (placeholder.includes('year (e.g. 2022)')) return 'year'
    if (placeholder.includes('decade key')) return 'decade'
    if (placeholder.includes('language code')) return 'language_code'
    if (placeholder.includes('aspect ratio key')) return 'aspect_key'
    if (placeholder.includes('resolution key')) return 'resolution_key'
    if (placeholder.includes('service key')) return 'streaming_key'
    if (placeholder.includes('universe key')) return 'universe_key'
    if (placeholder.includes('media outlet key')) return 'based_key'
    if (placeholder.includes('seasonal key')) return 'seasonal_key'
    if (placeholder.includes('content rating')) return 'content_rating'
    if (
      placeholder.includes('genre name') ||
      placeholder.includes('person name') ||
      placeholder.includes('studio name') ||
      placeholder.includes('network name') ||
      placeholder.includes('country name') ||
      placeholder.includes('region name') ||
      placeholder.includes('continent name')
    ) {
      return 'name_like'
    }
    return 'generic_text'
  }

  function ensureTemplateStringListDatalist (wrapper, input, presetConfig, presetName) {
    if (!wrapper || !input || !presetConfig || !Array.isArray(presetConfig.suggestions) || !presetConfig.suggestions.length) return
    if (presetConfig.suggestions.length > 50) return
    const existingListId = input.getAttribute('list')
    if (existingListId && document.getElementById(existingListId)) return
    const hiddenId = String(wrapper.dataset.hiddenInput || input.id || 'template-string-list').replace(/[^A-Za-z0-9_-]+/g, '_')
    const datalistId = `${hiddenId}_${presetName}_options`
    let datalist = document.getElementById(datalistId)
    if (!datalist) {
      datalist = document.createElement('datalist')
      datalist.id = datalistId
      presetConfig.suggestions.forEach(value => {
        const option = document.createElement('option')
        option.value = value
        datalist.appendChild(option)
      })
      wrapper.appendChild(datalist)
    }
    input.setAttribute('list', datalistId)
  }

  function setupTemplateStringListHandlers (scope) {
    const templateStringLookupCache = window.__qsTemplateStringLookupCache || new Map()
    window.__qsTemplateStringLookupCache = templateStringLookupCache

    function getServiceValidationState (serviceName) {
      const el = document.getElementById(`qs-validate-${serviceName}`)
      return String(el?.value || '').trim().toLowerCase() === 'true'
    }

    async function lookupTemplateStringValue (presetName, value, context = {}) {
      const libraryName = String(context.libraryName || '').trim()
      const mediaType = String(context.mediaType || '').trim()
      const cacheKey = `${presetName}:${libraryName}:${mediaType}:${value}`
      if (templateStringLookupCache.has(cacheKey)) {
        return templateStringLookupCache.get(cacheKey)
      }
      const request = fetch('/lookup_template_string_value', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          preset: presetName,
          value,
          library_name: libraryName,
          media_type: mediaType
        })
      })
        .then(async (response) => {
          const data = await response.json().catch(() => ({}))
          if (!response.ok) {
            return {
              valid: false,
              verified: false,
              message: data.error || data.message || `Lookup failed (${response.status})`
            }
          }
          return data
        })
        .catch(() => ({
          valid: false,
          verified: false,
          message: 'Lookup unavailable right now.'
        }))
      templateStringLookupCache.set(cacheKey, request)
      return request
    }

    const root = scope || document
    root.querySelectorAll('[data-template-string-list]').forEach(wrapper => {
      if (wrapper.dataset.listenerAdded) return
      const hiddenId = wrapper.dataset.hiddenInput
      const hidden = hiddenId ? document.getElementById(hiddenId) : wrapper.querySelector('input[type="hidden"]')
      const input = wrapper.querySelector('input[type="text"]')
      const addBtn = wrapper.querySelector('[data-template-string-add]')
      const list = wrapper.querySelector('[data-template-string-items]')
      const feedback = wrapper.querySelector('[data-template-string-feedback]')
      const templateVariableKey = String(wrapper.dataset.templateVariableKey || '').trim()
      const mutuallyExclusiveWith = String(wrapper.dataset.mutuallyExclusiveWith || '').trim()

      if (!hidden || !input || !addBtn || !list) return

      const presetName = inferTemplateStringListPreset(wrapper, input)
      const presetConfig = templateStringListPresetConfigs[presetName] || templateStringListPresetConfigs.generic_text
      const libraryName = String(wrapper.dataset.libraryName || '').trim()
      const mediaType = String(wrapper.dataset.mediaType || '').trim()
      ensureTemplateStringListDatalist(wrapper, input, presetConfig, presetName)

      function parseStoredStringList (rawValue) {
        const raw = String(rawValue || '').trim()
        if (!raw) return []
        try {
          const parsed = JSON.parse(raw)
          if (Array.isArray(parsed)) {
            return parsed.map(item => String(item).trim()).filter(Boolean)
          }
        } catch {
          // Fall through to support legacy storage.
        }
        if (raw.toLowerCase() === 'none') return []
        return raw.split(',').map(item => item.trim()).filter(Boolean)
      }

      function getCounterpartHiddenId () {
        if (!hiddenId || !templateVariableKey || !mutuallyExclusiveWith) return ''
        const suffix = `_${templateVariableKey}`
        if (!hiddenId.endsWith(suffix)) return ''
        return `${hiddenId.slice(0, -suffix.length)}_${mutuallyExclusiveWith}`
      }

      function getCounterpartWrapper () {
        const counterpartHiddenId = getCounterpartHiddenId()
        if (!counterpartHiddenId) return null
        return document.querySelector(`[data-template-string-list][data-hidden-input="${counterpartHiddenId}"]`)
      }

      function getCounterpartValues () {
        const counterpartWrapper = getCounterpartWrapper()
        if (counterpartWrapper && typeof counterpartWrapper.__qsTemplateStringListGetValues === 'function') {
          return counterpartWrapper.__qsTemplateStringListGetValues()
        }
        const counterpartHiddenId = getCounterpartHiddenId()
        const counterpartHidden = counterpartHiddenId ? document.getElementById(counterpartHiddenId) : null
        return parseStoredStringList(counterpartHidden?.value)
      }

      function setLookupState (target, state) {
        if (!target) return
        target.textContent = state?.message || ''
        target.className = 'small mt-1'
        if (!state?.message) {
          target.classList.add('d-none')
          return
        }
        target.classList.remove('d-none')
        if (state.level === 'warning') {
          target.classList.add('text-warning')
        } else if (state.valid && state.verified) {
          target.classList.add('text-success')
        } else if (state.verified) {
          target.classList.add('text-danger')
        } else {
          target.classList.add('text-warning')
        }
      }

      function setFeedback (message, persistent = false, level = 'error') {
        const isError = Boolean(message) && level === 'error'
        if (feedback) {
          feedback.textContent = message || ''
          feedback.classList.toggle('d-none', !message)
          feedback.classList.toggle('d-block', Boolean(message))
          feedback.classList.toggle('invalid-feedback', isError)
          feedback.classList.toggle('text-warning', Boolean(message) && level === 'warning')
          feedback.classList.toggle('small', Boolean(message) && level === 'warning')
        }
        input.classList.toggle('is-invalid', isError)
        input.setCustomValidity(persistent && isError && message ? message : '')
      }

      function clearTransientFeedback () {
        if (input.validationMessage) return
        setFeedback('')
      }

      function parseValues () {
        return parseStoredStringList(hidden.value)
      }

      function validateValue (rawValue) {
        const normalizedRaw = String(rawValue || '').trim()
        const normalized = presetConfig.normalize ? presetConfig.normalize(normalizedRaw) : normalizedRaw
        const result = presetConfig.validate ? presetConfig.validate(normalized) : { valid: Boolean(normalized) }
        return {
          value: normalized,
          valid: Boolean(result.valid),
          message: result.message || 'Enter a valid value.'
        }
      }

      function duplicateKeyForValue (value) {
        return presetConfig.duplicateInsensitive ? String(value || '').toLowerCase() : String(value || '')
      }

      function analyzeValues (values) {
        const seen = new Set()
        const analyzed = []
        values.forEach(rawValue => {
          const checked = validateValue(rawValue)
          if (!checked.value) return
          const duplicateKey = duplicateKeyForValue(checked.value)
          if (seen.has(duplicateKey)) return
          seen.add(duplicateKey)
          analyzed.push(checked)
        })
        return analyzed
      }

      function renderList (items) {
        list.replaceChildren()
        items.forEach((item, index) => {
          const li = document.createElement('li')
          li.className = 'list-group-item d-flex justify-content-between align-items-center'
          if (!item.valid) li.classList.add('list-group-item-danger')

          const textWrap = document.createElement('div')
          textWrap.className = 'd-flex flex-column'

          const titleRow = document.createElement('div')
          titleRow.className = 'd-flex align-items-center gap-2'

          const textSpan = document.createElement('span')
          textSpan.textContent = item.value
          titleRow.appendChild(textSpan)

          if (!item.valid) {
            const badge = document.createElement('span')
            badge.className = 'badge text-bg-danger'
            badge.textContent = 'Invalid'
            badge.title = item.message
            titleRow.appendChild(badge)
          }

          textWrap.appendChild(titleRow)

          const lookupMeta = document.createElement('div')
          lookupMeta.className = 'small mt-1 d-none'
          textWrap.appendChild(lookupMeta)

          const button = document.createElement('button')
          button.type = 'button'
          button.className = 'btn btn-sm btn-danger'
          button.setAttribute('aria-label', 'Remove')
          const icon = document.createElement('i')
          icon.className = 'bi bi-x-lg'
          button.appendChild(icon)
          li.append(textWrap, button)
          list.appendChild(li)

          button.addEventListener('click', () => {
            const updated = items
              .filter((_, itemIndex) => itemIndex !== index)
              .map(entry => entry.value)
            syncState(updated)
          })

          if (item.valid && presetConfig.lookupService === 'tmdb') {
            if (!getServiceValidationState('tmdb')) {
              setLookupState(lookupMeta, {
                valid: false,
                verified: false,
                message: 'TMDb not validated, so the item could not be checked.'
              })
            } else {
              setLookupState(lookupMeta, {
                valid: false,
                verified: false,
                message: 'Checking TMDb...'
              })
              lookupTemplateStringValue(presetName, item.value, { libraryName, mediaType }).then(result => {
                if (!lookupMeta.isConnected) return
                if (result.valid && result.verified && result.label) {
                  const successMessage = result.message || `TMDb: ${result.label}`
                  setLookupState(lookupMeta, {
                    valid: true,
                    verified: true,
                    level: result.level,
                    message: successMessage
                  })
                  return
                }
                setLookupState(lookupMeta, {
                  valid: Boolean(result.valid),
                  verified: Boolean(result.verified),
                  level: result.level,
                  message: result.message || 'TMDb lookup failed.'
                })
              })
            }
          } else if (item.valid && presetConfig.lookupService === 'plex') {
            if (!getServiceValidationState('plex')) {
              setLookupState(lookupMeta, {
                valid: false,
                verified: false,
                message: 'Plex not validated, so the IMDb ID could not be checked against the active library.'
              })
            } else if (!libraryName) {
              setLookupState(lookupMeta, {
                valid: false,
                verified: false,
                message: 'Library context is unavailable for Plex lookup.'
              })
            } else {
              setLookupState(lookupMeta, {
                valid: false,
                verified: false,
                message: 'Checking Plex library for this IMDb ID...'
              })
              lookupTemplateStringValue(presetName, item.value, { libraryName, mediaType }).then(result => {
                if (!lookupMeta.isConnected) return
                if (result.valid && result.verified && result.label) {
                  const successMessage = result.message || `Plex: ${result.label}`
                  setLookupState(lookupMeta, {
                    valid: true,
                    verified: true,
                    level: result.level,
                    message: successMessage
                  })
                  return
                }
                setLookupState(lookupMeta, {
                  valid: Boolean(result.valid),
                  verified: Boolean(result.verified),
                  level: result.level,
                  message: result.message || 'Plex lookup failed.'
                })
              })
            }
          }
        })
      }

      function syncState (values, transientMessage = '', options = {}) {
        const previousSerialized = String(hidden.value || '')
        const analyzed = analyzeValues(values)
        const normalizedValues = analyzed.map(item => item.value)
        let feedbackMessage = transientMessage || ''
        let feedbackLevel = 'error'

        if (!options.skipMutualExclusion && mutuallyExclusiveWith && normalizedValues.length) {
          const counterpartValues = getCounterpartValues()
          if (counterpartValues.length && !feedbackMessage) {
            feedbackMessage = 'Include and Exclude are both set. Kometa code allows this, but the wiki says not to combine them.'
            feedbackLevel = 'warning'
          }
        }

        hidden.value = JSON.stringify(normalizedValues)
        renderList(analyzed)

        const invalidItems = analyzed.filter(item => !item.valid)
        if (invalidItems.length) {
          const message = invalidItems.length === 1
            ? `${invalidItems[0].message} Remove or fix the invalid entry.`
            : `${invalidItems[0].message} Remove or fix the invalid entries.`
          setFeedback(message, true)
        } else {
          setFeedback(feedbackMessage || '', false, feedbackLevel)
        }

        if (options.emitChange !== false && String(hidden.value || '') !== previousSerialized) {
          hidden.dispatchEvent(new Event('change', { bubbles: true }))
          wrapper.dispatchEvent(new CustomEvent('qs:template-string-list-change', {
            bubbles: true,
            detail: {
              hiddenInput: hidden.id || hidden.name || hiddenId || '',
              values: normalizedValues
            }
          }))
        }

        return analyzed
      }

      function addValue () {
        const checked = validateValue(input.value)
        if (!checked.value) {
          setFeedback('Enter a value before adding it.', false)
          return
        }
        if (!checked.valid) {
          setFeedback(checked.message, false)
          return
        }
        const current = analyzeValues(parseValues())
        if (current.some(item => duplicateKeyForValue(item.value) === duplicateKeyForValue(checked.value))) {
          setFeedback('That value is already in the list.', false)
          return
        }
        current.push(checked)
        syncState(current.map(item => item.value))
        input.value = ''
        clearTransientFeedback()
      }

      wrapper.__qsTemplateStringListGetValues = () => parseValues()
      wrapper.__qsTemplateStringListSync = syncState
      wrapper.__qsTemplateStringListValidate = () => {
        const analyzed = syncState(parseValues(), '', { emitChange: false })
        return analyzed.every(item => item.valid) && !input.validationMessage
      }
      syncState(parseValues(), '', { emitChange: false })

      addBtn.addEventListener('click', addValue)
      input.addEventListener('input', clearTransientFeedback)
      hidden.addEventListener('change', () => {
        syncState(parseValues(), '', { emitChange: false })
      })
      input.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
          event.preventDefault()
          addValue()
        }
      })

      wrapper.dataset.listenerAdded = 'true'
    })
  }

  function validateAllTemplateStringLists (scope) {
    let allValid = true
    const root = scope || document
    root.querySelectorAll('[data-template-string-list]').forEach(wrapper => {
      if (typeof wrapper.__qsTemplateStringListValidate === 'function') {
        if (!wrapper.__qsTemplateStringListValidate()) {
          allValid = false
        }
      }
    })
    return allValid
  }

  window.QSTemplateStringLists = {
    presetConfigs: templateStringListPresetConfigs,
    setup: setupTemplateStringListHandlers,
    validateAll: validateAllTemplateStringLists
  }
})()

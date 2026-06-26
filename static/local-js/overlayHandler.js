/* global EventHandler, ValidationHandler, toggleOverlayTemplateSection, FontFace, FileReader, Image, requestAnimationFrame, boardState, ResizeObserver, DOMParser, applyPosition */

const OverlayHandler = {
  baseDimensions: {
    default: { width: 1000, height: 1500 },
    episode: { width: 1920, height: 1080 }
  },
  initializeOverlays: function (libraryId, isMovie) {
    console.log(`[DEBUG] Initializing overlays for ${libraryId} - ${isMovie ? 'Movie' : 'Show'}`)

    // Attach event listener for separator dropdown
    const fieldId = `${libraryId}-template_variables[use_separator]`
    const separatorDropdown = document.querySelector(`[name="${fieldId}"]`)

    if (separatorDropdown && !separatorDropdown.dataset.listenerAdded) {
      separatorDropdown.addEventListener('change', () => {
        const selectedStyle = separatorDropdown.value !== 'none'
        OverlayHandler.updateSeparatorToggles(libraryId, selectedStyle)
        OverlayHandler.updateSeparatorPreview(fieldId, separatorDropdown.value)
        OverlayHandler.toggleSeparatorPlaceholder(libraryId, selectedStyle)
        OverlayHandler.updateHiddenInputs(libraryId, isMovie)
        EventHandler.updateAccordionHighlights()
      })

      separatorDropdown.dataset.listenerAdded = true

      // Apply separator logic on initial page load
      const initialSelected = separatorDropdown.value !== 'none'
      OverlayHandler.updateSeparatorToggles(libraryId, initialSelected)
      OverlayHandler.updateSeparatorPreview(fieldId, separatorDropdown.value)
      OverlayHandler.toggleSeparatorPlaceholder(libraryId, initialSelected)
      OverlayHandler.updateHiddenInputs(libraryId, isMovie)
      EventHandler.updateAccordionHighlights()
    }

    const placeholderWrapper = OverlayHandler.getSeparatorPlaceholderWrapper(libraryId)
    const sourceSelect = placeholderWrapper?.querySelector('.separator-placeholder-source')
    if (sourceSelect && !sourceSelect.dataset.listenerAdded) {
      sourceSelect.addEventListener('change', () => {
        const separatorsEnabled = separatorDropdown ? separatorDropdown.value !== 'none' : true
        OverlayHandler.syncSeparatorPlaceholderFields(placeholderWrapper, { show: separatorsEnabled })
        EventHandler.updateAccordionHighlights()
      })
      sourceSelect.dataset.listenerAdded = 'true'
    }
  },

  /**
     * Enable/Disable Award & Chart Separator Toggles Based on Separator Style Selection
     */
  updateSeparatorToggles: function (libraryId, isEnabled) {
    console.log(`[DEBUG] Updating Separator Toggles for ${libraryId} - Enabled: ${isEnabled}`)

    const awardToggle = document.getElementById(`${libraryId}-collection_separator_award`)
    const chartToggle = document.getElementById(`${libraryId}-collection_separator_chart`)

    if (awardToggle) {
      awardToggle.disabled = !isEnabled
      awardToggle.checked = isEnabled
      console.log(`[DEBUG] Award Separator Toggle is now ${isEnabled ? 'ENABLED' : 'DISABLED'}`)
    }

    if (chartToggle) {
      chartToggle.disabled = !isEnabled
      chartToggle.checked = isEnabled
      console.log(`[DEBUG] Chart Separator Toggle is now ${isEnabled ? 'ENABLED' : 'DISABLED'}`)
    }
  },

  updateSeparatorPreview: function (fieldId, selectedStyle) {
    console.log(`[DEBUG] Updating Separator Preview for ${fieldId} - Style: ${selectedStyle}`)

    const safeId = fieldId.replace('[', '_').replace(']', '')
    const containerId = `${safeId}-separatorPreviewContainer`
    const imageId = `${safeId}-separatorPreviewImage`

    const separatorPreviewContainer = document.getElementById(containerId)
    const separatorPreviewImage = document.getElementById(imageId)

    if (!separatorPreviewContainer || !separatorPreviewImage) {
      console.error(`[ERROR] Separator preview elements missing for ${fieldId}`)
      return
    }

    if (selectedStyle && selectedStyle !== 'none') {
      const imageUrl = `https://github.com/Kometa-Team/Default-Images/blob/master/separators/${selectedStyle}/chart.jpg?raw=true`
      separatorPreviewImage.src = imageUrl
      separatorPreviewContainer.style.display = 'block'
      console.log(`[DEBUG] Separator preview updated to: ${imageUrl}`)
    } else {
      separatorPreviewContainer.style.display = 'none'
    }
  },

  updateHiddenInputs: function (libraryId, isMovie) {
    console.log(`[DEBUG] Updating hidden inputs for Library: ${libraryId} - ${isMovie ? 'Movies' : 'Shows'}`)

    const form = document.getElementById('configForm')
    if (!form) {
      console.error("[ERROR] Form element 'configForm' not found!")
      return
    }

    const useSeparatorsDropdown = document.querySelector(`[name="${libraryId}-template_variables[use_separator]"]`)
    let useSeparatorsInput = document.getElementById(`${libraryId}-template_variables_use_separator`)
    let sepStyleInput = document.getElementById(`${libraryId}-template_variables_sep_style`)

    const awardSeparatorToggle = document.getElementById(`${libraryId}-collection_separator_award`)
    const chartSeparatorToggle = document.getElementById(`${libraryId}-collection_separator_chart`)

    const selectedValue = useSeparatorsDropdown.value
    const isEnabled = selectedValue !== 'none'

    // Clear separator placeholder values if separator is disabled
    if (!isEnabled) {
      const placeholderWrapper = OverlayHandler.getSeparatorPlaceholderWrapper(libraryId)
      OverlayHandler.syncSeparatorPlaceholderFields(placeholderWrapper, { show: false })
    }

    // Create hidden inputs dynamically if missing
    if (!useSeparatorsInput) {
      useSeparatorsInput = document.createElement('input')
      useSeparatorsInput.type = 'hidden'
      useSeparatorsInput.name = `${libraryId}-template_variables[use_separator]`
      useSeparatorsInput.id = `${libraryId}-template_variables_use_separator`
      form.appendChild(useSeparatorsInput)
    }

    if (!sepStyleInput) {
      sepStyleInput = document.createElement('input')
      sepStyleInput.type = 'hidden'
      sepStyleInput.name = `${libraryId}-template_variables[sep_style]`
      sepStyleInput.id = `${libraryId}-template_variables_sep_style`
      form.appendChild(sepStyleInput)
    }
    sepStyleInput.value = isEnabled ? selectedValue : ''

    if (awardSeparatorToggle) {
      // Only depend on sep_style being set to enable/disable
      awardSeparatorToggle.disabled = !isEnabled
      awardSeparatorToggle.checked = isEnabled
    }

    if (chartSeparatorToggle) {
      // Only depend on sep_style being set to enable/disable
      chartSeparatorToggle.disabled = !isEnabled
      chartSeparatorToggle.checked = isEnabled
    }

    const fieldId = `${libraryId}-template_variables[use_separator]`
    OverlayHandler.updateSeparatorPreview(fieldId, selectedValue)
  },

  getSeparatorPlaceholderWrapper: function (libraryId) {
    return document.querySelector(`[data-separator-placeholder-wrapper="true"][data-library-prefix="${libraryId}"]`)
  },

  syncSeparatorPlaceholderFields: function (wrapper, options = {}) {
    if (!wrapper) return

    const show = options.show !== false
    const libraryType = String(wrapper.dataset.libraryType || '').trim().toLowerCase()
    const allowedSources = libraryType === 'movie' ? ['imdb', 'tmdb_movie'] : ['imdb', 'tvdb_show']
    const sourceSelect = wrapper.querySelector('.separator-placeholder-source')
    const fieldInputs = Array.from(wrapper.querySelectorAll('[data-separator-placeholder-input]'))
    if (!sourceSelect || !fieldInputs.length) return

    const valueBySource = {}
    fieldInputs.forEach(input => {
      valueBySource[input.dataset.separatorPlaceholderInput] = String(input.value || '').trim()
      input.classList.remove('is-invalid')
    })

    let activeSource = String(sourceSelect.value || '').trim()
    if (!allowedSources.includes(activeSource)) {
      activeSource = allowedSources.find(source => valueBySource[source]) || 'imdb'
    }
    sourceSelect.value = activeSource
    sourceSelect.disabled = !show
    sourceSelect.classList.remove('is-invalid')
    wrapper.classList.toggle('visually-hidden', !show)

    fieldInputs.forEach(input => {
      const source = String(input.dataset.separatorPlaceholderInput || '').trim()
      const fieldGroup = input.closest('.separator-placeholder-field')
      const isActive = show && source === activeSource
      if (fieldGroup) fieldGroup.classList.toggle('d-none', !isActive)
      if (!isActive) {
        input.value = ''
      }
    })
  },

  toggleSeparatorPlaceholder: function (libraryId, show) {
    const wrapper = OverlayHandler.getSeparatorPlaceholderWrapper(libraryId)
    if (!wrapper) {
      console.error(`[ERROR] Separator placeholder block not found for libraryId: ${libraryId}`)
      return
    }
    OverlayHandler.syncSeparatorPlaceholderFields(wrapper, { show })
  },

  /**
   * Initialize drag-to-position previews for overlays.
   * Keeps offsets in sync with the form inputs.
   */
  initializeOverlayPositioners: function (scope) {
    const root = scope || document
    const positioners = root.querySelectorAll('.overlay-positioner')

    positioners.forEach((pos) => {
      if (pos.dataset.positionerBound === 'true') return
      pos.dataset.positionerBound = 'true'

      const canvas = pos.querySelector('.overlay-canvas')
      const overlay = pos.querySelector('.overlay-preview-node')
      const xLabel = pos.querySelector('[data-overlay-x]')
      const yLabel = pos.querySelector('[data-overlay-y]')

      const hInputId = pos.dataset.horizontalId
      const vInputId = pos.dataset.verticalId
      const hInput = hInputId ? document.getElementById(hInputId) : null
      const vInput = vInputId ? document.getElementById(vInputId) : null

      const baseWidth = Number(pos.dataset.baseWidth) || OverlayHandler.baseDimensions.default.width
      const baseHeight = Number(pos.dataset.baseHeight) || OverlayHandler.baseDimensions.default.height

      if (!canvas || !overlay || !hInput || !vInput) {
        console.warn('[OverlayPositioner] Missing required elements', { canvas, overlay, hInput, vInput })
        return
      }

      const updateLabels = (h, v) => {
        if (xLabel) xLabel.textContent = Math.round(h)
        if (yLabel) yLabel.textContent = Math.round(v)
      }

      const clamp = (val, min, max) => Math.min(Math.max(val, min), max)

      const setOverlayPosition = (h, v) => {
        const canvasRect = canvas.getBoundingClientRect()
        const scaleX = canvasRect.width / baseWidth
        const scaleY = canvasRect.height / baseHeight || scaleX
        overlay.style.left = `${h * scaleX}px`
        overlay.style.top = `${v * scaleY}px`
        updateLabels(h, v)
      }

      const getCurrentOffsets = () => ({
        h: Number(hInput.value) || 0,
        v: Number(vInput.value) || 0
      })

      let syncing = false
      const syncFromInputs = () => {
        if (syncing) return
        const { h, v } = getCurrentOffsets()
        setOverlayPosition(h, v)
      }

      const syncToInputs = (h, v) => {
        syncing = true
        hInput.value = h
        vInput.value = v
        hInput.dispatchEvent(new Event('change', { bubbles: true }))
        vInput.dispatchEvent(new Event('change', { bubbles: true }))
        syncing = false
      }

      const handleDrag = () => {
        let dragging = false
        let start = { x: 0, y: 0, h: 0, v: 0 }

        const onPointerDown = (e) => {
          e.preventDefault()
          overlay.setPointerCapture(e.pointerId)
          const { h, v } = getCurrentOffsets()
          start = { x: e.clientX, y: e.clientY, h, v }
          dragging = true
          overlay.classList.add('dragging')
        }

        const onPointerMove = (e) => {
          if (!dragging) return
          const canvasRect = canvas.getBoundingClientRect()
          const scaleX = canvasRect.width / baseWidth
          const scaleY = canvasRect.height / baseHeight || scaleX
          const overlayRect = overlay.getBoundingClientRect()

          const overlayWidthBase = overlayRect.width / scaleX
          const overlayHeightBase = overlayRect.height / scaleY

          const deltaX = (e.clientX - start.x) / (scaleX * boardState.zoom)
          const deltaY = (e.clientY - start.y) / (scaleY * boardState.zoom)

          const maxH = Math.max(0, baseWidth - overlayWidthBase)
          const maxV = Math.max(0, baseHeight - overlayHeightBase)

          const nextH = clamp(start.h + deltaX, 0, maxH)
          const nextV = clamp(start.v + deltaY, 0, maxV)

          setOverlayPosition(nextH, nextV)
          syncToInputs(Math.round(nextH), Math.round(nextV))
        }

        const onPointerUp = (e) => {
          if (!dragging) return
          dragging = false
          overlay.releasePointerCapture(e.pointerId)
          overlay.classList.remove('dragging')
        }

        overlay.addEventListener('pointerdown', onPointerDown)
        window.addEventListener('pointermove', onPointerMove)
        window.addEventListener('pointerup', onPointerUp)
      }

      const overlayImage = overlay.tagName === 'IMG' ? overlay : null
      const kickOff = () => {
        const canvasWidth = canvas.clientWidth || canvas.offsetWidth
        const ratio = baseWidth / baseHeight
        if (canvasWidth && canvas.style.aspectRatio === '') {
          canvas.style.setProperty('--overlay-ratio', `${ratio}`)
        }
        syncFromInputs()
      }

      overlayImage?.addEventListener('load', kickOff, { once: true })
      kickOff()

      hInput.addEventListener('input', syncFromInputs)
      vInput.addEventListener('input', syncFromInputs)
      hInput.addEventListener('change', syncFromInputs)
      vInput.addEventListener('change', syncFromInputs)

      handleDrag()
    })
  },

  /**
   * Render a combined overlay board for all overlays within a group.
   * Layers stay in sync with toggle state and offset inputs, and support dragging.
   */
  initializeOverlayBoards: function (scope) {
    const root = scope || document
    const defaultDims = OverlayHandler.baseDimensions
    const isFlagsOverlay = (cfg) => cfg.id === 'overlay_languages' || cfg.id === 'overlay_languages_subtitles'

    const resolveOverlayImage = (cfg) => {
      const replacePathSegment = (baseUrl, marker, newSegment) => {
        try {
          const urlObj = new URL(baseUrl)
          const parts = urlObj.pathname.split('/')
          const idx = parts.findIndex((p) => p === marker)
          if (idx !== -1 && idx + 1 < parts.length) {
            parts[idx + 1] = encodeURIComponent(newSegment)
            urlObj.pathname = parts.join('/')
            return urlObj.toString()
          }
        } catch (e) {
          console.warn('[OverlayBoards] Failed to adjust URL', { baseUrl, e })
        }
        return baseUrl
      }

      if (cfg.id === 'overlay_ribbon' && cfg.styleInput) {
        const style = (cfg.styleInput.value || 'yellow').toLowerCase()
        const allowed = ['yellow', 'red', 'black', 'gray']
        const styleSafe = allowed.includes(style) ? style : 'yellow'
        return replacePathSegment(cfg.image, 'ribbon', styleSafe)
      }
      if (cfg.id === 'overlay_streaming' && cfg.styleInput) {
        const style = (cfg.styleInput.value || 'color').toLowerCase()
        const allowed = ['color', 'white']
        const styleSafe = allowed.includes(style) ? style : 'color'
        return replacePathSegment(cfg.image, 'streaming', styleSafe)
      }
      if (cfg.id === 'overlay_studio' && cfg.styleInput) {
        const style = (cfg.styleInput.value || 'standard').toLowerCase()
        const allowed = ['standard', 'bigger']
        const styleSafe = allowed.includes(style) ? style : 'standard'
        const folder = styleSafe === 'bigger' ? 'bigger' : 'standard'
        return replacePathSegment(cfg.image, 'studio', folder)
      }
      if (cfg.id === 'overlay_network' && cfg.styleInput) {
        const style = (cfg.styleInput.value || 'color').toLowerCase()
        const allowed = ['color', 'white']
        const styleSafe = allowed.includes(style) ? style : 'color'
        return replacePathSegment(cfg.image, 'network', styleSafe)
      }
      if (cfg.id === 'overlay_audio_codec' && cfg.styleInput) {
        const style = (cfg.styleInput.value || 'compact').toLowerCase()
        const allowed = ['compact', 'standard']
        const styleSafe = allowed.includes(style) ? style : 'compact'
        return replacePathSegment(cfg.image, 'audio_codec', styleSafe)
      }
      if ((cfg.id === 'overlay_languages' || cfg.id === 'overlay_languages_subtitles') && cfg.styleInput) {
        const style = (cfg.styleInput.value || 'round').toLowerCase()
        const styleSafe = style === 'square' || style === 'half' ? 'square' : 'round'
        return replacePathSegment(cfg.image, 'flag', styleSafe)
      }
      if (cfg.id && cfg.id.startsWith('overlay_content_rating_')) {
        let colorVal = 'true'
        const templateName = cfg.container?.dataset?.overlayTemplate
        if (templateName) {
          const colorInput = cfg.container.querySelector(`[name="${templateName}[color]"]`)
          if (colorInput) colorVal = colorInput.value || 'true'
        }
        const isColor = String(colorVal).toLowerCase() !== 'false'
        if (!isColor) {
          try {
            const urlObj = new URL(cfg.image, window.location.origin)
            const parts = urlObj.pathname.split('/')
            const last = parts.pop()
            if (last) {
              const newLast = last.replace(/c(\.[^.]+)$/i, '$1')
              parts.push(newLast)
              urlObj.pathname = parts.join('/')
              return urlObj.toString()
            }
          } catch {
            // Fallback simple replace
            return cfg.image.replace(/c(\.[^.]+)$/i, '$1')
          }
        }
        return cfg.image
      }
      return cfg.image
    }

    const BACKDROP_IMAGE_OVERLAYS = new Set([
      'overlay_mediastinger',
      'overlay_versions',
      'overlay_audio_codec',
      'overlay_streaming',
      'overlay_studio',
      'overlay_network',
      'overlay_language_count',
      'overlay_direct_play',
      'overlay_resolution',
      'overlay_ratings'
    ])
    const BACKDROP_TEXT_OVERLAYS = new Set([
      'overlay_video_format',
      'overlay_aspect',
      'overlay_runtimes',
      'overlay_episode_info',
      'overlay_status'
    ])

    // Runtime overlay specific: ensure selected font is loaded before drawing
    const runtimeFontCache = new Map()
    const imageCache = OverlayHandler._imageCache instanceof Map
      ? OverlayHandler._imageCache
      : new Map()
    OverlayHandler._imageCache = imageCache
    const normalizeFontFile = (fontVal) => {
      if (!fontVal) return { file: null, family: null }
      const file = fontVal.split(/[\\/]/).pop()
      return {
        file,
        family: file ? file.replace(/\.[^.]+$/, '') : null
      }
    }
    const ensureRuntimeFontLoaded = (fontVal) => {
      const { file, family } = normalizeFontFile(fontVal)
      if (!file || !file.match(/\.(ttf|otf)$/i) || typeof FontFace === 'undefined') {
        return Promise.resolve(null)
      }
      if (runtimeFontCache.has(file)) return runtimeFontCache.get(file)
      const face = new FontFace(family, `url(/custom-fonts/${encodeURIComponent(file)})`)
      const p = face.load()
        .then(loaded => {
          document.fonts.add(loaded)
          return family
        })
        .catch(err => {
          console.warn('[OverlayBoards] Failed to load font', file, err)
          return null
        })
      runtimeFontCache.set(file, p)
      return p
    }

    const getRuntimeVars = (cfg) => {
      const container = cfg.container
      const templateName = container?.dataset.overlayTemplate
      const getVal = (key, defaultVal) => {
        if (!container || !templateName) return defaultVal
        const el = container.querySelector(`[name="${templateName}[${key}]"]`)
        if (!el) return defaultVal
        if (el.tagName === 'SELECT') return el.value || defaultVal
        if (el.type === 'number') return Number(el.value) || defaultVal
        if (key === 'text') return el.value ?? ''
        return el.value || defaultVal
      }
      return {
        text: getVal('text', 'Runtime: '),
        format: getVal('format', '<<runtimeH>>h <<runtimeM>>m'),
        font: getVal('font', 'Inter-Medium.ttf'),
        font_size: getVal('font_size', 55),
        font_color: getVal('font_color', '#FFFFFF'),
        stroke_width: getVal('stroke_width', 1),
        stroke_color: getVal('stroke_color', '#00000000')
      }
    }

    const getSimpleTextVars = (cfg) => {
      const container = cfg.container
      const templateName = container?.dataset.overlayTemplate
      const getVal = (key, defaultVal) => {
        if (!container || !templateName) return defaultVal
        const el = container.querySelector(`[name="${templateName}[${key}]"]`)
        if (!el) return defaultVal
        const fallback = el.dataset?.default || defaultVal
        if (el.tagName === 'SELECT') return el.value || fallback
        if (el.type === 'number') {
          const n = Number(el.value)
          return Number.isFinite(n) ? n : (Number(el.dataset?.default) || fallback)
        }
        return el.value || fallback
      }
      const mode = getOverlayTextPreviewMode(cfg)
      const selectedPreview = ['toggle_text', 'episode_info'].includes(mode)
        ? getOverlayTextPreviewSelectedValue(cfg)
        : ''
      if (selectedPreview) syncOverlayTextPreviewTextInput(cfg)
      return {
        text: selectedPreview || getVal('text', ''),
        font: getVal('font', 'Inter-Medium.ttf'),
        font_size: getVal('font_size', 55),
        font_color: getVal('font_color', '#FFFFFFFF'),
        stroke_width: getVal('stroke_width', 1),
        stroke_color: getVal('stroke_color', '#00000000')
      }
    }

    const getTextBoxMetrics = (ctx, text, fontSize, padding = 10, strokeWidth = 0) => {
      const metrics = ctx.measureText(text)
      const left = Math.ceil(metrics.actualBoundingBoxLeft || 0)
      const right = Math.ceil(metrics.actualBoundingBoxRight || metrics.width || 0)
      const ascent = Math.ceil(metrics.actualBoundingBoxAscent || fontSize * 0.8)
      const descent = Math.ceil(metrics.actualBoundingBoxDescent || fontSize * 0.2)
      const safePad = Math.ceil(fontSize * 0.2)
      const strokePad = Math.ceil(Math.max(0, Number(strokeWidth) || 0))
      const pad = padding + Math.ceil(safePad / 2) + strokePad
      return {
        width: left + right + pad * 2,
        height: ascent + descent + pad * 2,
        left,
        ascent,
        pad
      }
    }

    const getStatusTextVars = (cfg) => {
      const container = cfg.container
      const templateName = container?.dataset.overlayTemplate
      const getVal = (key, defaultVal) => {
        if (!container || !templateName) return defaultVal
        const el = container.querySelector(`[name="${templateName}[${key}]"]`)
        if (!el) return defaultVal
        const fallback = el.dataset?.default || defaultVal
        if (el.tagName === 'SELECT') return el.value || fallback
        if (el.type === 'number') {
          const n = Number(el.value)
          return Number.isFinite(n) ? n : (Number(el.dataset?.default) || fallback)
        }
        return el.value || fallback
      }

      const previewKey = getOverlayTextPreviewSelectedValue(cfg) || 'airing'
      const text = getVal(`text_${previewKey}`, 'AIRING')
      return {
        text,
        font: getVal('font', 'Inter-Medium.ttf'),
        font_size: getVal('font_size', 55),
        font_color: getVal('font_color', '#FFFFFFFF'),
        stroke_width: getVal('stroke_width', 1),
        stroke_color: getVal('stroke_color', '#00000000')
      }
    }

    const getBackdropVars = (cfg) => {
      const container = cfg.container
      const templateName = container?.dataset.overlayTemplate
      const getVal = (key, defaultVal) => {
        if (!container || !templateName) return defaultVal
        const el = container.querySelector(`[name="${templateName}[${key}]"]`)
        if (!el) return defaultVal
        const fallback = el.dataset?.default ?? defaultVal
        if (el.tagName === 'SELECT') return (el.value || fallback)
        if (el.type === 'number') {
          const n = Number(el.value)
          return Number.isFinite(n) ? n : (Number(fallback) || defaultVal)
        }
        return (el.value || fallback)
      }
      return {
        back_align: String(getVal('back_align', 'center') || 'center').toLowerCase(),
        back_color: getVal('back_color', '#00000099'),
        back_height: getVal('back_height', 105),
        back_width: getVal('back_width', 105),
        back_line_color: getVal('back_line_color', '#00000000'),
        back_line_width: getVal('back_line_width', 0),
        back_padding: getVal('back_padding', 0),
        back_radius: getVal('back_radius', 30)
      }
    }

    const getFlagVars = (cfg) => {
      const container = cfg.container
      const templateName = container?.dataset.overlayTemplate
      const getEl = (key) => {
        if (!container || !templateName) return null
        return container.querySelector(`[name="${templateName}[${key}]"]`)
      }
      const getVal = (key, defaultVal) => {
        const el = getEl(key)
        if (!el) return defaultVal
        const fallback = el.dataset?.default ?? defaultVal
        if (el.type === 'checkbox') return el.checked
        if (el.tagName === 'SELECT') return el.value || fallback
        if (el.type === 'number') {
          const n = Number(el.value)
          return Number.isFinite(n) ? n : (Number(fallback) || defaultVal)
        }
        return el.value || fallback
      }
      const normalizeBool = (val, fallback = false) => {
        if (typeof val === 'boolean') return val
        if (typeof val === 'string') return val.toLowerCase() === 'true'
        return Boolean(val ?? fallback)
      }
      return {
        style: String(getVal('style', 'round') || 'round').toLowerCase(),
        size: String(getVal('size', 'small') || 'small').toLowerCase(),
        hide_text: normalizeBool(getVal('hide_text', false), false),
        use_lowercase: normalizeBool(getVal('use_lowercase', false), false),
        group_alignment: String(getVal('group_alignment', 'vertical') || 'vertical').toLowerCase(),
        offset: Number(getVal('offset', 10)) || 10,
        font: String(getVal('font', 'Inter-Bold.ttf') || 'Inter-Bold.ttf'),
        font_size: Number(getVal('font_size', 50)) || 50,
        font_color: String(getVal('font_color', '#FFFFFFFF') || '#FFFFFFFF'),
        stroke_width: Number(getVal('stroke_width', 1)) || 1,
        stroke_color: String(getVal('stroke_color', '#00000000') || '#00000000')
      }
    }

    const getTemplateInput = (cfg, key) => {
      const container = cfg.container
      const templateName = container?.dataset.overlayTemplate
      if (!container || !templateName) return null
      return container.querySelector(`[name="${templateName}[${key}]"]`)
    }

    const getOverlayTextPreviewMode = (cfg) => {
      const overlayId = String(cfg?.id || '').trim()
      if (overlayId === 'overlay_aspect' || overlayId === 'overlay_video_format') return 'toggle_text'
      if (overlayId === 'overlay_episode_info') return 'episode_info'
      if (overlayId === 'overlay_status') return 'status'
      if (overlayId === 'overlay_runtimes') return 'runtime'
      return ''
    }

    const getOverlayTextPreviewStateKey = (cfg) => {
      const overlayId = String(cfg?.id || '').trim()
      if (overlayId === 'overlay_aspect') return 'aspect_text'
      if (overlayId === 'overlay_video_format') return 'video_format_text'
      if (overlayId === 'overlay_episode_info') return 'episode_info_text'
      if (overlayId === 'overlay_status') return 'status_text'
      if (overlayId === 'overlay_runtimes') return 'runtime_minutes'
      return ''
    }

    const getOverlayTextPreviewOptions = (cfg) => {
      const mode = getOverlayTextPreviewMode(cfg)
      if (!mode || !cfg?.container) return []

      if (mode === 'episode_info') {
        return [
          { value: 'S01E01', label: 'S01E01' },
          { value: 'S03E15', label: 'S03E15' },
          { value: 'S10E22', label: 'S10E22' },
          { value: 'S00E01', label: 'Special (S00E01)' }
        ]
      }

      if (mode === 'runtime') {
        return [
          { value: '24', label: '24 min' },
          { value: '45', label: '45 min' },
          { value: '93', label: '93 min (1h 33m)' },
          { value: '130', label: '130 min (2h 10m)' }
        ]
      }

      const templateName = cfg.container.dataset.overlayTemplate
      if (!templateName) return []

      if (mode === 'toggle_text') {
        const options = []
        const seen = new Set()
        const toggleInputs = Array.from(cfg.container.querySelectorAll(`[name^="${templateName}[use_"]`))
          .filter(input => String(input?.type || '').toLowerCase() === 'checkbox')
        toggleInputs.forEach((input) => {
          const keyMatch = /\[([^\]]+)\]$/.exec(String(input.name || ''))
          const toggleKey = String(keyMatch?.[1] || '').trim()
          if (!toggleKey.startsWith('use_')) return
          const labelEl = input.closest('.form-check')?.querySelector('.form-check-label')
          let label = String(labelEl?.textContent || toggleKey.slice(4)).replace(/\s+/g, ' ').trim()
          if (label.toLowerCase().startsWith('use ')) {
            label = label.slice(4).trim()
          }
          if (!label || seen.has(label)) return
          seen.add(label)
          options.push({
            value: label,
            label,
            enabled: input.checked
          })
        })
        return options
      }

      if (mode === 'status') {
        const statusDefs = [
          { key: 'airing', label: 'Airing' },
          { key: 'returning', label: 'Returning' },
          { key: 'canceled', label: 'Canceled' },
          { key: 'ended', label: 'Ended' }
        ]
        return statusDefs.map((statusDef) => {
          const toggle = cfg.container.querySelector(`[name="${templateName}[use_${statusDef.key}]"]`)
          return {
            value: statusDef.key,
            label: statusDef.label,
            enabled: Boolean(toggle?.checked)
          }
        })
      }

      return []
    }

    const pickDefaultOverlayTextPreviewValue = (cfg) => {
      const mode = getOverlayTextPreviewMode(cfg)
      const options = getOverlayTextPreviewOptions(cfg)
      if (mode === 'runtime') return options.find(option => option.value === '93')?.value || options[0]?.value || '93'
      if (mode === 'episode_info') return options.find(option => option.value === 'S03E15')?.value || options[0]?.value || 'S03E15'
      return options.find(option => option.enabled)?.value || options[0]?.value || ''
    }

    const getOverlayTextPreviewSelectedValue = (cfg) => {
      const mode = getOverlayTextPreviewMode(cfg)
      if (!mode) return ''
      const stateKey = getOverlayTextPreviewStateKey(cfg)
      const state = ensureResolutionPreviewState(cfg)
      const options = getOverlayTextPreviewOptions(cfg)
      const values = new Set(options.map(option => String(option.value || '').trim()))
      const current = String(state[stateKey] || '').trim()
      if (current && values.has(current)) return current

      let fallback = ''
      if (mode === 'toggle_text' || mode === 'episode_info') {
        const textInput = getTemplateInput(cfg, 'text')
        const currentText = String(textInput?.value || textInput?.dataset?.default || '').trim()
        if (currentText && values.has(currentText)) {
          fallback = currentText
        }
      }
      if (!fallback) fallback = pickDefaultOverlayTextPreviewValue(cfg)
      state[stateKey] = fallback
      return fallback
    }

    const setOverlayTextPreviewSelectedValue = (cfg, value) => {
      const stateKey = getOverlayTextPreviewStateKey(cfg)
      if (!stateKey) return
      const state = ensureResolutionPreviewState(cfg)
      state[stateKey] = String(value || '').trim()
    }

    const syncOverlayTextPreviewTextInput = (cfg) => {
      const mode = getOverlayTextPreviewMode(cfg)
      if (!['toggle_text', 'episode_info'].includes(mode)) return
      const textInput = getTemplateInput(cfg, 'text')
      if (!textInput) return
      const selected = getOverlayTextPreviewSelectedValue(cfg)
      textInput.value = selected
      textInput.dataset.default = selected
    }

    const setTemplateNumber = (cfg, key, value, emit = true) => {
      const input = getTemplateInput(cfg, key)
      if (!input) return
      const next = String(value)
      input.dataset.default = next
      if (input.value !== next) {
        input.value = next
        if (emit) {
          input.dispatchEvent(new Event('input', { bubbles: true }))
          input.dispatchEvent(new Event('change', { bubbles: true }))
        }
      }
    }

    const setBackdropHeight = (cfg, height, emit = true) => {
      setTemplateNumber(cfg, 'back_height', height, emit)
    }

    const FLAG_PREVIEW_SLOT_COUNT = 3
    const FLAG_PREVIEW_DEFAULT_KEYS = ['en', 'de', 'fr']
    const FLAG_PREVIEW_METADATA = {
      en: { previewKey: 'us', text: 'EN' },
      de: { previewKey: 'de', text: 'DE' },
      fr: { previewKey: 'fr', text: 'FR' },
      es: { previewKey: 'es', text: 'ES' },
      pt: { previewKey: 'pt', text: 'PT' },
      ja: { previewKey: 'jp', text: 'JA' },
      ko: { previewKey: 'kr', text: 'KO' },
      zh: { previewKey: 'cn', text: 'ZH' },
      da: { previewKey: 'dk', text: 'DA' },
      ru: { previewKey: 'ru', text: 'RU' },
      it: { previewKey: 'it', text: 'IT' },
      hi: { previewKey: 'in', text: 'HI' },
      te: { previewKey: 'in', text: 'TE' },
      fa: { previewKey: 'ir', text: 'FA' },
      th: { previewKey: 'th', text: 'TH' },
      nl: { previewKey: 'nl', text: 'NL' },
      no: { previewKey: 'no', text: 'NO' },
      is: { previewKey: 'is', text: 'IS' },
      sv: { previewKey: 'se', text: 'SV' },
      tr: { previewKey: 'tr', text: 'TR' },
      pl: { previewKey: 'pl', text: 'PL' },
      cs: { previewKey: 'cz', text: 'CS' },
      uk: { previewKey: 'ua', text: 'UK' },
      hu: { previewKey: 'hu', text: 'HU' },
      ar: { previewKey: 'eg', text: 'AR' },
      bg: { previewKey: 'bg', text: 'BG' },
      bn: { previewKey: 'bd', text: 'BN' },
      bs: { previewKey: 'ba', text: 'BS' },
      ca: { previewKey: 'ad', text: 'CA' },
      cy: { previewKey: 'uk', text: 'CY' },
      el: { previewKey: 'gr', text: 'EL' },
      et: { previewKey: 'ee', text: 'ET' },
      eu: { previewKey: 'es', text: 'EU' },
      fi: { previewKey: 'fi', text: 'FI' },
      tl: { previewKey: 'ph', text: 'FL' },
      fil: { previewKey: 'ph', text: 'FIL' },
      gl: { previewKey: 'es', text: 'GL' },
      he: { previewKey: 'il', text: 'HE' },
      hr: { previewKey: 'hr', text: 'HR' },
      id: { previewKey: 'id', text: 'ID' },
      ka: { previewKey: 'ge', text: 'KA' },
      kk: { previewKey: 'kz', text: 'KK' },
      kn: { previewKey: 'in', text: 'KN' },
      la: { previewKey: 'it', text: 'LA' },
      lt: { previewKey: 'lt', text: 'LT' },
      lv: { previewKey: 'lv', text: 'LV' },
      mk: { previewKey: 'mk', text: 'MK' },
      ml: { previewKey: 'in', text: 'ML' },
      mr: { previewKey: 'in', text: 'MR' },
      ms: { previewKey: 'my', text: 'MS' },
      nb: { previewKey: 'no', text: 'NB' },
      nn: { previewKey: 'no', text: 'NN' },
      pa: { previewKey: 'in', text: 'PA' },
      ro: { previewKey: 'ro', text: 'RO' },
      sk: { previewKey: 'sk', text: 'SK' },
      sl: { previewKey: 'si', text: 'SL' },
      sq: { previewKey: 'al', text: 'SQ' },
      sr: { previewKey: 'rs', text: 'SR' },
      sw: { previewKey: 'tz', text: 'SW' },
      so: { previewKey: 'so', text: 'SO' },
      ta: { previewKey: 'in', text: 'TA' },
      ur: { previewKey: 'pk', text: 'UR' },
      vi: { previewKey: 'vn', text: 'VI' },
      wo: { previewKey: 'sn', text: 'WO' },
      myn: { previewKey: 'mx', text: 'MYN' },
      iu: { previewKey: 'ca', text: 'IK' },
      rom: { previewKey: 'ro', text: 'ROM' },
      am: { previewKey: 'et', text: 'AM' },
      su: { previewKey: 'id', text: 'SU' },
      zu: { previewKey: 'za', text: 'ZU' }
    }

    const RESOLUTION_CHILD_TOGGLE_KEYS = [
      'use_4k',
      'use_1080p',
      'use_720p',
      'use_576p',
      'use_480p',
      'use_dv',
      'use_hlg',
      'use_hdr',
      'use_plus',
      'use_dvhdr',
      'use_dvhdrplus'
    ]

    const RESOLUTION_BASE_BADGE_KEYS = ['4k', '1080p', '720p', '576p', '480p']
    const RESOLUTION_ALT_BADGE_KEYS = ['dvhdrplus', 'dvhdr', 'plus', 'dv', 'hlg', 'hdr']

    const EDITION_CHILD_TOGGLE_KEYS = [
      'use_extended',
      'use_uncut',
      'use_unrated',
      'use_special',
      'use_anniversary',
      'use_collector',
      'use_diamond',
      'use_platinum',
      'use_directors',
      'use_final',
      'use_international',
      'use_theatrical',
      'use_ultimate',
      'use_alternate',
      'use_coda',
      'use_enhanced',
      'use_imax',
      'use_remastered',
      'use_criterion',
      'use_richarddonner',
      'use_blackchrome',
      'use_definitive',
      'use_openmatte',
      'use_ulysses',
      'use_producers'
    ]

    const RESOLUTION_TOGGLE_FAMILIES = [
      {
        family: 'resolution',
        title: 'Resolution Badges',
        description: 'Enable the family, then choose which resolution and HDR variants can render.',
        masterKey: 'use_resolution',
        childKeys: RESOLUTION_CHILD_TOGGLE_KEYS
      },
      {
        family: 'edition',
        title: 'Edition Badges',
        description: 'Enable the family, then choose which edition badges can render.',
        masterKey: 'use_edition',
        childKeys: EDITION_CHILD_TOGGLE_KEYS
      }
    ]

    const AUDIO_CODEC_CHILD_TOGGLE_KEYS = [
      'use_truehd_atmos',
      'use_dtsx',
      'use_plus_atmos',
      'use_dolby_atmos',
      'use_truehd',
      'use_ma',
      'use_flac',
      'use_pcm',
      'use_hra',
      'use_plus',
      'use_dtses',
      'use_dts',
      'use_digital',
      'use_aac',
      'use_mp3',
      'use_opus'
    ]

    const STREAMING_CHILD_TOGGLE_KEYS = [
      'use_netflix',
      'use_amazon',
      'use_disney',
      'use_hbomax',
      'use_crunchyroll',
      'use_movistar',
      'use_atresplayer',
      'use_youtube',
      'use_hulu',
      'use_paramount',
      'use_amc',
      'use_appletv',
      'use_peacock',
      'use_discovery',
      'use_crave',
      'use_now',
      'use_channel4',
      'use_itvx',
      'use_bet',
      'use_hayu',
      'use_tubi',
      'use_filmin'
    ]

    const RIBBON_CHILD_TOGGLE_KEYS = [
      'use_oscars',
      'use_oscars_director',
      'use_golden',
      'use_golden_director',
      'use_bafta',
      'use_cannes',
      'use_berlinale',
      'use_venice',
      'use_sundance',
      'use_emmys',
      'use_choice',
      'use_spirit',
      'use_cesar',
      'use_imdb',
      'use_letterboxd',
      'use_rottenverified',
      'use_rotten',
      'use_metacritic',
      'use_common',
      'use_razzie'
    ]

    const LANGUAGE_COUNT_CHILD_TOGGLE_KEYS = [
      'use_dual',
      'use_multi'
    ]

    const STREAMING_BADGE_FILENAME_MAP = {
      amazon: 'Prime Video',
      amc: 'AMC+',
      appletv: 'AppleTV',
      atresplayer: 'Atres Player',
      bet: 'BET+',
      channel4: 'Channel 4',
      crave: 'Crave',
      crunchyroll: 'Crunchyroll',
      discovery: 'discovery+',
      disney: 'Disney',
      filmin: 'Filmin',
      hayu: 'hayu',
      hbomax: 'HBO Max',
      hulu: 'Hulu',
      itvx: 'ITVX',
      max: 'Max',
      movistar: 'Movistar Plus+',
      netflix: 'Netflix',
      now: 'NOW',
      paramount: 'Paramount+',
      peacock: 'Peacock',
      tubi: 'tubi',
      youtube: 'YouTube'
    }

    const SINGLE_BADGE_OVERLAY_FAMILY_BY_ID = {
      overlay_network: 'network',
      overlay_studio: 'studio'
    }

    const FIXED_BADGE_OVERLAY_FAMILY_BY_ID = {
      overlay_mediastinger: 'mediastinger',
      overlay_versions: 'versions',
      overlay_direct_play: 'direct_play'
    }

    const FIXED_BADGE_OVERLAY_KEY_BY_ID = {
      overlay_mediastinger: 'Mediastinger',
      overlay_versions: 'versions',
      overlay_direct_play: 'Direct-Play'
    }

    const BUNDLED_OVERLAY_PREVIEW_ROOT = '/static/images/overlay-defaults'
    const bundledOverlayKeyOptionsCache = new Map()
    const bundledOverlayKeyOptionsInflight = new Map()

    const getResolutionToggleFamilyDef = (family) => {
      return RESOLUTION_TOGGLE_FAMILIES.find(item => item.family === family) || null
    }

    const parseResolutionBadgeKey = (badgeKey) => {
      const key = String(badgeKey || '').trim().replace(/^use_/, '')
      if (!key) return null
      if (RESOLUTION_BASE_BADGE_KEYS.includes(key)) {
        return { badgeKey: key, baseKey: key, altKey: '' }
      }
      if (RESOLUTION_ALT_BADGE_KEYS.includes(key)) {
        return { badgeKey: key, baseKey: '', altKey: key }
      }
      for (const baseKey of RESOLUTION_BASE_BADGE_KEYS) {
        const prefix = `${baseKey}_`
        if (!key.startsWith(prefix)) continue
        const altKey = key.slice(prefix.length)
        if (RESOLUTION_ALT_BADGE_KEYS.includes(altKey)) {
          return { badgeKey: key, baseKey, altKey }
        }
      }
      return null
    }

    const getResolutionFamilyToggleKeys = (cfg) => {
      if (!cfg?.container) return RESOLUTION_CHILD_TOGGLE_KEYS.slice()
      const templateName = cfg.container.dataset.overlayTemplate
      if (!templateName) return RESOLUTION_CHILD_TOGGLE_KEYS.slice()

      const seen = new Set()
      const keys = []
      const toggleInputs = Array.from(cfg.container.querySelectorAll(`[name^="${templateName}[use_"]`))
        .filter(input => String(input?.type || '').toLowerCase() === 'checkbox')
      toggleInputs.forEach(input => {
        const keyMatch = /\[([^\]]+)\]$/.exec(String(input.name || ''))
        const toggleKey = String(keyMatch?.[1] || '').trim()
        if (toggleKey === 'use_resolution' || !parseResolutionBadgeKey(toggleKey) || seen.has(toggleKey)) return
        seen.add(toggleKey)
        keys.push(toggleKey)
      })

      return keys.length ? keys : RESOLUTION_CHILD_TOGGLE_KEYS.slice()
    }

    const getToggleFamilyChildKeys = (cfg, family) => {
      if (family === 'resolution') return getResolutionFamilyToggleKeys(cfg)
      if (family === 'edition') return EDITION_CHILD_TOGGLE_KEYS.slice()
      if (family === 'audio_codec') return AUDIO_CODEC_CHILD_TOGGLE_KEYS.slice()
      if (family === 'streaming') return STREAMING_CHILD_TOGGLE_KEYS.slice()
      if (family === 'ribbon') return RIBBON_CHILD_TOGGLE_KEYS.slice()
      if (family === 'language_count') return LANGUAGE_COUNT_CHILD_TOGGLE_KEYS.slice()
      return []
    }

    const getResolutionToggleFamilyForBadgeKey = (badgeKey) => {
      const key = String(badgeKey || '').trim()
      if (!key) return ''
      if (parseResolutionBadgeKey(key)) return 'resolution'
      if (EDITION_CHILD_TOGGLE_KEYS.includes(`use_${key}`)) return 'edition'
      return ''
    }

    const CONTENT_RATING_PREVIEW_FILENAMES = {
      overlay_content_rating_us_movie: {
        g: { color: 'usgc.png', mono: 'usg.png' },
        pg: { color: 'uspgc.png', mono: 'uspg.png' },
        'pg-13': { color: 'uspg-13c.png', mono: 'uspg-13.png' },
        r: { color: 'usrc.png', mono: 'usr.png' },
        'nc-17': { color: 'usnc-17c.png', mono: 'usnc-17.png' },
        nr: { color: 'usnrc.png', mono: 'usnr.png' }
      },
      overlay_content_rating_us_show: {
        'tv-g': { color: 'ustv-gc.png', mono: 'ustv-g.png' },
        'tv-y': { color: 'ustv-yc.png', mono: 'ustv-y.png' },
        'tv-pg': { color: 'ustv-pgc.png', mono: 'ustv-pg.png' },
        'tv-14': { color: 'ustv-14c.png', mono: 'ustv-14.png' },
        'tv-ma': { color: 'ustv-mac.png', mono: 'ustv-ma.png' },
        nr: { color: 'usnrc.png', mono: 'usnr.png' }
      },
      overlay_content_rating_uk: {
        u: { color: 'ukuc.png', mono: 'uku.png' },
        pg: { color: 'ukpgc.png', mono: 'ukpg.png' },
        12: { color: 'uk12c.png', mono: 'uk12.png' },
        '12a': { color: 'uk12ac.png', mono: 'uk12a.png' },
        15: { color: 'uk15c.png', mono: 'uk15.png' },
        18: { color: 'uk18c.png', mono: 'uk18.png' },
        r18: { color: 'ukr18c.png', mono: 'ukr18.png' },
        nr: { color: 'uknrc.png', mono: 'uknr.png' }
      },
      overlay_content_rating_de: {
        0: { color: 'de0c.png', mono: 'de0.png' },
        6: { color: 'de6c.png', mono: 'de6.png' },
        12: { color: 'de12c.png', mono: 'de12.png' },
        16: { color: 'de16c.png', mono: 'de16.png' },
        18: { color: 'de18c.png', mono: 'de18.png' },
        bpjm: { color: 'debpjmc.png', mono: 'debpjm.png' },
        nr: { color: 'denrc.png', mono: 'denr.png' }
      },
      overlay_content_rating_au: {
        g: { color: 'au_gc.png', mono: 'au_g.png' },
        pg: { color: 'au_pgc.png', mono: 'au_pg.png' },
        m: { color: 'au_mc.png', mono: 'au_m.png' },
        ma: { color: 'au_mac.png', mono: 'au_ma.png' },
        r: { color: 'au_rc.png', mono: 'au_r.png' },
        x: { color: 'au_xc.png', mono: 'au_x.png' },
        nr: { color: 'au_nrc.png', mono: 'au_nr.png' }
      },
      overlay_content_rating_nz: {
        g: { color: 'nz_gc.png', mono: 'nz_g.png' },
        pg: { color: 'nz_pgc.png', mono: 'nz_pg.png' },
        m: { color: 'nz_mc.png', mono: 'nz_m.png' },
        r13: { color: 'nz_r13c.png', mono: 'nz_r13.png' },
        rp13: { color: 'nz_rp13c.png', mono: 'nz_rp13.png' },
        r15: { color: 'nz_r15c.png', mono: 'nz_r15.png' },
        r16: { color: 'nz_r16c.png', mono: 'nz_r16.png' },
        rp16: { color: 'nz_rp16c.png', mono: 'nz_rp16.png' },
        R18: { color: 'nz_r18c.png', mono: 'nz_r18.png' },
        rp18: { color: 'nz_rp18c.png', mono: 'nz_rp18.png' },
        r: { color: 'nz_rc.png', mono: 'nz_r.png' },
        nr: { color: 'nz_nrc.png', mono: 'nz_nr.png' }
      },
      overlay_content_rating_commonsense: {
        commonsense: { color: 'Commonsense.png', mono: 'Commonsense.png' }
      }
    }

    const REGIONAL_CONTENT_RATING_OVERLAY_IDS = new Set([
      'overlay_content_rating_us_movie',
      'overlay_content_rating_us_show',
      'overlay_content_rating_uk',
      'overlay_content_rating_de',
      'overlay_content_rating_au',
      'overlay_content_rating_nz'
    ])

    const getOverlayPreviewFilename = (badgeKey, family = '') => {
      const normalizedFamily = String(family || '').trim().toLowerCase()
      const rawKey = String(badgeKey || '').trim()
      const normalizedKey = normalizedFamily === 'audio_codec' || normalizedFamily === 'ribbon'
        ? rawKey
        : normalizedFamily === 'streaming'
          ? (STREAMING_BADGE_FILENAME_MAP[rawKey] || rawKey)
          : rawKey.replace(/_/g, '')
      return normalizedKey ? `${normalizedKey}.png` : ''
    }

    const buildBundledOverlayPreviewUrl = (family, badgeKey, variant = '') => {
      const filename = getOverlayPreviewFilename(badgeKey, family)
      if (!family || !filename) return ''
      const normalizedVariant = String(variant || '').trim().toLowerCase()
      if (family === 'flag') {
        const style = normalizedVariant === 'square' ? 'square' : 'round'
        return `${BUNDLED_OVERLAY_PREVIEW_ROOT}/${family}/${style}/${filename}`
      }
      if (family === 'audio_codec') {
        const style = normalizedVariant === 'standard' ? 'standard' : 'compact'
        return `${BUNDLED_OVERLAY_PREVIEW_ROOT}/${family}/${style}/${filename}`
      }
      if (family === 'streaming') {
        const style = normalizedVariant === 'white' ? 'white' : 'color'
        return `${BUNDLED_OVERLAY_PREVIEW_ROOT}/${family}/${style}/${filename}`
      }
      if (family === 'ribbon') {
        const style = ['yellow', 'gray', 'black', 'red'].includes(normalizedVariant) ? normalizedVariant : 'yellow'
        return `${BUNDLED_OVERLAY_PREVIEW_ROOT}/${family}/${style}/${filename}`
      }
      if (family === 'language_count') {
        const style = normalizedVariant === 'subs' ? 'subs' : 'audio'
        return `${BUNDLED_OVERLAY_PREVIEW_ROOT}/${family}/${String(badgeKey || '').trim()}_${style}.png`
      }
      return `${BUNDLED_OVERLAY_PREVIEW_ROOT}/${family}/${filename}`
    }

    const isRegionalContentRatingOverlay = (cfg) => {
      return REGIONAL_CONTENT_RATING_OVERLAY_IDS.has(String(cfg?.id || '').trim())
    }

    const isCommonsenseContentRatingOverlay = (cfg) => {
      return String(cfg?.id || '').trim() === 'overlay_content_rating_commonsense'
    }

    const getCommonsensePreviewTextInput = (cfg) => {
      if (!cfg?.container) return null
      const templateName = cfg.container.dataset.overlayTemplate
      if (!templateName) return null
      return cfg.container.querySelector(`[name="${templateName}[text]"]`)
    }

    const getCommonsensePreviewOptions = (cfg) => {
      if (!cfg?.container) return []
      const templateName = cfg.container.dataset.overlayTemplate
      if (!templateName) return []
      const options = []
      cfg.container.querySelectorAll(`input[type="checkbox"][name^="${templateName}[use_"]`).forEach((input) => {
        const rawName = String(input.name || '')
        const match = new RegExp(`^${templateName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\[use_(.+)\\]$`).exec(rawName)
        const value = String(match?.[1] || '').trim()
        if (!value) return
        const numericValue = Number(value)
        const labelEl = input.closest('.form-check')?.querySelector('.form-check-label')
        let label = String(labelEl?.textContent || `${value}+`).replace(/\s+/g, ' ').trim()
        if (label.toLowerCase().startsWith('use ')) {
          label = label.slice(4).trim()
        }
        options.push({
          value,
          label,
          enabled: input.checked,
          sortValue: Number.isFinite(numericValue) ? numericValue : Number.MAX_SAFE_INTEGER
        })
      })
      options.sort((a, b) => {
        if (a.sortValue !== b.sortValue) return a.sortValue - b.sortValue
        return a.label.localeCompare(b.label)
      })
      return options
    }

    const pickDefaultCommonsensePreviewValue = (cfg) => {
      const options = getCommonsensePreviewOptions(cfg)
      return options.find(option => option.enabled)?.value || options[0]?.value || ''
    }

    const getCommonsensePreviewValue = (cfg) => {
      const input = getCommonsensePreviewTextInput(cfg)
      const current = String(input?.value || '').trim()
      const options = getCommonsensePreviewOptions(cfg)
      const values = new Set(options.map(option => option.value))
      if (current && values.has(current)) return current
      const fallback = pickDefaultCommonsensePreviewValue(cfg)
      if (input && fallback) input.value = fallback
      return fallback
    }

    const setCommonsensePreviewValue = (cfg, value) => {
      const input = getCommonsensePreviewTextInput(cfg)
      if (input) {
        input.value = String(value || '').trim()
      }
    }

    const normalizeCommonsensePreviewText = (value) => {
      const normalized = String(value || '').trim()
      if (!normalized) return ''
      return normalized.toLowerCase() === 'nr' ? 'NR' : normalized
    }

    const getContentRatingPreviewOptions = (cfg) => {
      if (isCommonsenseContentRatingOverlay(cfg)) {
        return getCommonsensePreviewOptions(cfg)
      }
      if (!cfg?.container) return []
      const templateName = cfg.container.dataset.overlayTemplate
      if (!templateName) return []
      const overlayId = String(cfg?.id || '').trim()
      const filenameMap = CONTENT_RATING_PREVIEW_FILENAMES[overlayId]
      if (!filenameMap) return []
      const options = []
      Object.keys(filenameMap).forEach((badgeKey) => {
        const toggleKey = `use_${badgeKey}`
        const input = cfg.container.querySelector(`input[type="checkbox"][name="${templateName}[${toggleKey}]"]`)
        if (!input) return
        const labelEl = input.closest('.form-check')?.querySelector('.form-check-label')
        let label = String(labelEl?.textContent || badgeKey).replace(/\s+/g, ' ').trim()
        if (label.toLowerCase().startsWith('use ')) {
          label = label.slice(4).trim()
        }
        options.push({
          value: badgeKey,
          label,
          enabled: input.checked
        })
      })
      return options
    }

    const pickDefaultContentRatingPreviewKey = (cfg) => {
      if (isCommonsenseContentRatingOverlay(cfg)) {
        return pickDefaultCommonsensePreviewValue(cfg)
      }
      const options = getContentRatingPreviewOptions(cfg)
      return options.find(option => option.enabled)?.value || options[0]?.value || ''
    }

    const getContentRatingPreviewSelectedKey = (cfg) => {
      if (isCommonsenseContentRatingOverlay(cfg)) {
        return getCommonsensePreviewValue(cfg)
      }
      const state = ensureResolutionPreviewState(cfg)
      const options = getContentRatingPreviewOptions(cfg)
      const values = new Set(options.map(option => option.value))
      const stateKey = String(cfg?.id || '').trim()
      const current = String(state[stateKey] || '').trim()
      if (current && values.has(current)) return current
      const fallback = pickDefaultContentRatingPreviewKey(cfg)
      state[stateKey] = fallback
      return fallback
    }

    const setContentRatingPreviewSelectedKey = (cfg, badgeKey) => {
      if (isCommonsenseContentRatingOverlay(cfg)) {
        setCommonsensePreviewValue(cfg, badgeKey)
        return
      }
      const state = ensureResolutionPreviewState(cfg)
      const stateKey = String(cfg?.id || '').trim()
      state[stateKey] = String(badgeKey || '').trim()
    }

    const getContentRatingPreviewOverrideEntries = (cfg) => {
      const config = getOverlaySourceOverrideConfig(cfg)
      const section = cfg?.container?.querySelector('[data-overlay-source-editor="true"]')
      const hiddenHost = section?.querySelector('[data-overlay-source-hidden]')
      if (!config || !hiddenHost) return []
      return readOverlaySourceOverrideState(cfg, config, hiddenHost)
    }

    const getContentRatingPreviewColorMode = (cfg) => {
      if (isCommonsenseContentRatingOverlay(cfg)) return 'color'
      const colorInput = getTemplateInput(cfg, 'color')
      return String(colorInput?.value || 'true').toLowerCase() === 'false' ? 'mono' : 'color'
    }

    const buildBundledContentRatingPreviewUrl = (cfg, badgeKey) => {
      const overlayId = String(cfg?.id || '').trim()
      const filenameMap = CONTENT_RATING_PREVIEW_FILENAMES[overlayId]
      const badgeMap = filenameMap?.[String(badgeKey || '').trim()]
      if (!badgeMap) return ''
      const colorMode = getContentRatingPreviewColorMode(cfg)
      const filename = badgeMap[colorMode] || badgeMap.color || badgeMap.mono || ''
      if (!filename) return ''
      return `${BUNDLED_OVERLAY_PREVIEW_ROOT}/content_rating/${filename}`
    }

    const resolveContentRatingPreviewImage = (cfg) => {
      const overrideEntries = getContentRatingPreviewOverrideEntries(cfg)
      if (isCommonsenseContentRatingOverlay(cfg)) {
        const overrideEntry = overrideEntries.find(entry => entry.badgeKey === 'commonsense' && entry.sourceType && entry.value)
        if (overrideEntry) {
          return buildOverlaySourcePreviewUrl(overrideEntry.sourceType, overrideEntry.value)
        }
        return buildBundledContentRatingPreviewUrl(cfg, 'commonsense') || resolveOverlayImage(cfg)
      }
      const badgeKey = getContentRatingPreviewSelectedKey(cfg)
      const overrideEntry = overrideEntries.find(entry => entry.badgeKey === badgeKey && entry.sourceType && entry.value)
      if (overrideEntry) {
        return buildOverlaySourcePreviewUrl(overrideEntry.sourceType, overrideEntry.value)
      }
      return buildBundledContentRatingPreviewUrl(cfg, badgeKey) || resolveOverlayImage(cfg)
    }

    const buildOverlaySourcePreviewUrl = (sourceType, sourceValue) => {
      const normalizedType = String(sourceType || '').trim()
      const normalizedValue = String(sourceValue || '').trim()
      if (!normalizedType || !normalizedValue) return ''
      const params = new URLSearchParams({
        source_type: normalizedType,
        source_value: normalizedValue
      })
      return `/overlay-source-preview?${params.toString()}`
    }

    const blobToDataUrl = (blob) => {
      return new Promise((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => resolve(reader.result)
        reader.onerror = () => reject(reader.error || new Error('Unable to read preview image blob'))
        reader.readAsDataURL(blob)
      })
    }

    const getResolutionRenderPayload = (cfg) => {
      const { useResolution, useEdition } = getResolutionToggleState(cfg)
      const overrideEntries = getResolutionPreviewOverrideEntries(cfg)
      const resolutionBadgeKey = getResolutionPreviewSelectedKey(cfg, 'resolution')
      const editionBadgeKey = getResolutionPreviewSelectedKey(cfg, 'edition')
      const resolutionOverride = overrideEntries.find(entry => entry.badgeKey === resolutionBadgeKey && entry.sourceType && entry.value)
      const editionOverride = overrideEntries.find(entry => entry.badgeKey === editionBadgeKey && entry.sourceType && entry.value)

      return {
        overlay_id: cfg.id,
        use_resolution: useResolution,
        use_edition: useEdition,
        spacing: Number(cfg.edition?.spacing) || 15,
        resolution: {
          badge_key: resolutionBadgeKey,
          source_type: resolutionOverride?.sourceType || '',
          source_value: resolutionOverride?.value || ''
        },
        edition: {
          badge_key: editionBadgeKey,
          source_type: editionOverride?.sourceType || '',
          source_value: editionOverride?.value || ''
        }
      }
    }

    const getAudioCodecStyle = (cfg) => {
      const style = String(cfg?.styleInput?.value || 'compact').trim().toLowerCase()
      return style === 'standard' ? 'standard' : 'compact'
    }

    const getStreamingStyle = (cfg) => {
      const style = String(cfg?.styleInput?.value || 'color').trim().toLowerCase()
      return style === 'white' ? 'white' : 'color'
    }

    const getNetworkStyle = (cfg) => {
      const style = String(cfg?.styleInput?.value || 'color').trim().toLowerCase()
      return style === 'white' ? 'white' : 'color'
    }

    const getStudioStyle = (cfg) => {
      const style = String(cfg?.styleInput?.value || 'standard').trim().toLowerCase()
      return style === 'bigger' ? 'bigger' : 'standard'
    }

    const getRibbonStyle = (cfg) => {
      const style = String(cfg?.styleInput?.value || 'yellow').trim().toLowerCase()
      return ['yellow', 'gray', 'black', 'red'].includes(style) ? style : 'yellow'
    }

    const getLanguageCountVariant = (cfg) => {
      const subtitlesToggle = getTemplateInput(cfg, 'use_subtitles')
      return subtitlesToggle?.checked ? 'subs' : 'audio'
    }

    const getAudioCodecPreviewOptions = (cfg) => {
      if (!cfg?.container) return []
      const templateName = cfg.container.dataset.overlayTemplate
      if (!templateName) return []
      const options = []
      const childKeys = getToggleFamilyChildKeys(cfg, 'audio_codec')
      childKeys.forEach(toggleKey => {
        const badgeKey = String(toggleKey || '').trim().replace(/^use_/, '')
        if (!badgeKey) return
        const input = cfg.container.querySelector(`[name="${templateName}[${toggleKey}]"]`)
        const labelEl = input?.closest('.form-check')?.querySelector('.form-check-label')
        let label = String(labelEl?.textContent || badgeKey).replace(/\s+/g, ' ').trim()
        if (label.toLowerCase().startsWith('use ')) {
          label = label.slice(4).trim()
        }
        options.push({
          value: badgeKey,
          label,
          enabled: input ? input.checked : false
        })
      })
      return options
    }

    const getAudioCodecPreviewSelectedKey = (cfg) => {
      const state = ensureResolutionPreviewState(cfg)
      const options = getAudioCodecPreviewOptions(cfg)
      const values = new Set(options.map(option => option.value))
      const current = String(state.audio_codec || '').trim()
      if (current && values.has(current)) return current
      const fallback = options.find(option => option.enabled)?.value || options[0]?.value || ''
      state.audio_codec = fallback
      return fallback
    }

    const setAudioCodecPreviewSelectedKey = (cfg, badgeKey) => {
      const state = ensureResolutionPreviewState(cfg)
      state.audio_codec = String(badgeKey || '').trim()
    }

    const getAudioCodecPreviewOverrideEntries = (cfg) => {
      const config = getOverlaySourceOverrideConfig(cfg)
      const section = cfg?.container?.querySelector('[data-overlay-source-editor="true"]')
      const hiddenHost = section?.querySelector('[data-overlay-source-hidden]')
      if (!config || !hiddenHost) return []
      return readOverlaySourceOverrideState(cfg, config, hiddenHost)
    }

    const getAudioCodecRenderPayload = (cfg) => {
      const overrideEntries = getAudioCodecPreviewOverrideEntries(cfg)
      const badgeKey = getAudioCodecPreviewSelectedKey(cfg)
      const override = overrideEntries.find(entry => entry.badgeKey === badgeKey && entry.sourceType && entry.value)
      return {
        overlay_id: cfg.id,
        audio_codec: {
          badge_key: badgeKey,
          source_type: override?.sourceType || '',
          source_value: override?.value || '',
          variant: getAudioCodecStyle(cfg)
        }
      }
    }

    const getStreamingPreviewOptions = (cfg) => {
      if (!cfg?.container) return []
      const templateName = cfg.container.dataset.overlayTemplate
      if (!templateName) return []
      const options = []
      const childKeys = getToggleFamilyChildKeys(cfg, 'streaming')
      childKeys.forEach(toggleKey => {
        const badgeKey = String(toggleKey || '').trim().replace(/^use_/, '')
        if (!badgeKey) return
        const input = cfg.container.querySelector(`[name="${templateName}[${toggleKey}]"]`)
        const labelEl = input?.closest('.form-check')?.querySelector('.form-check-label')
        let label = String(labelEl?.textContent || badgeKey).replace(/\s+/g, ' ').trim()
        if (label.toLowerCase().startsWith('use ')) {
          label = label.slice(4).trim()
        }
        options.push({
          value: badgeKey,
          label,
          enabled: input ? input.checked : false
        })
      })
      return options
    }

    const getStreamingPreviewSelectedKey = (cfg) => {
      const state = ensureResolutionPreviewState(cfg)
      const options = getStreamingPreviewOptions(cfg)
      const values = new Set(options.map(option => option.value))
      const current = String(state.streaming || '').trim()
      if (current && values.has(current)) return current
      const fallback = options.find(option => option.enabled)?.value || options[0]?.value || ''
      state.streaming = fallback
      return fallback
    }

    const setStreamingPreviewSelectedKey = (cfg, badgeKey) => {
      const state = ensureResolutionPreviewState(cfg)
      state.streaming = String(badgeKey || '').trim()
    }

    const getStreamingPreviewOverrideEntries = (cfg) => {
      const config = getOverlaySourceOverrideConfig(cfg)
      const section = cfg?.container?.querySelector('[data-overlay-source-editor="true"]')
      const hiddenHost = section?.querySelector('[data-overlay-source-hidden]')
      if (!config || !hiddenHost) return []
      return readOverlaySourceOverrideState(cfg, config, hiddenHost)
    }

    const getStreamingRenderPayload = (cfg) => {
      const overrideEntries = getStreamingPreviewOverrideEntries(cfg)
      const badgeKey = getStreamingPreviewSelectedKey(cfg)
      const override = overrideEntries.find(entry => entry.badgeKey === badgeKey && entry.sourceType && entry.value)
      return {
        overlay_id: cfg.id,
        streaming: {
          badge_key: badgeKey,
          source_type: override?.sourceType || '',
          source_value: override?.value || '',
          variant: getStreamingStyle(cfg)
        }
      }
    }

    const getRibbonPreviewOptions = (cfg) => {
      if (!cfg?.container) return []
      const templateName = cfg.container.dataset.overlayTemplate
      if (!templateName) return []
      const options = []
      const childKeys = getToggleFamilyChildKeys(cfg, 'ribbon')
      childKeys.forEach(toggleKey => {
        const badgeKey = String(toggleKey || '').trim().replace(/^use_/, '')
        if (!badgeKey) return
        const input = cfg.container.querySelector(`[name="${templateName}[${toggleKey}]"]`)
        const labelEl = input?.closest('.form-check')?.querySelector('.form-check-label')
        let label = String(labelEl?.textContent || badgeKey).replace(/\s+/g, ' ').trim()
        if (label.toLowerCase().startsWith('use ')) label = label.slice(4).trim()
        options.push({
          value: badgeKey,
          label,
          enabled: input ? input.checked : false
        })
      })
      return options
    }

    const getRibbonPreviewSelectedKey = (cfg) => {
      const state = ensureResolutionPreviewState(cfg)
      const options = getRibbonPreviewOptions(cfg)
      const values = new Set(options.map(option => option.value))
      const current = String(state.ribbon || '').trim()
      if (current && values.has(current)) return current
      const fallback = options.find(option => option.enabled)?.value || options[0]?.value || ''
      state.ribbon = fallback
      return fallback
    }

    const setRibbonPreviewSelectedKey = (cfg, badgeKey) => {
      const state = ensureResolutionPreviewState(cfg)
      state.ribbon = String(badgeKey || '').trim()
    }

    const getRibbonPreviewOverrideEntries = (cfg) => {
      const config = getOverlaySourceOverrideConfig(cfg)
      const section = cfg?.container?.querySelector('[data-overlay-source-editor="true"]')
      const hiddenHost = section?.querySelector('[data-overlay-source-hidden]')
      if (!config || !hiddenHost) return []
      return readOverlaySourceOverrideState(cfg, config, hiddenHost)
    }

    const getRibbonRenderPayload = (cfg) => {
      const overrideEntries = getRibbonPreviewOverrideEntries(cfg)
      const badgeKey = getRibbonPreviewSelectedKey(cfg)
      const override = overrideEntries.find(entry => entry.badgeKey === badgeKey && entry.sourceType && entry.value)
      return {
        overlay_id: cfg.id,
        ribbon: {
          badge_key: badgeKey,
          source_type: override?.sourceType || '',
          source_value: override?.value || '',
          variant: getRibbonStyle(cfg)
        }
      }
    }

    const getLanguageCountPreviewOptions = (cfg) => {
      if (!cfg?.container) return []
      const templateName = cfg.container.dataset.overlayTemplate
      if (!templateName) return []
      const options = []
      const childKeys = getToggleFamilyChildKeys(cfg, 'language_count')
      childKeys.forEach(toggleKey => {
        const badgeKey = String(toggleKey || '').trim().replace(/^use_/, '')
        if (!badgeKey) return
        const input = cfg.container.querySelector(`[name="${templateName}[${toggleKey}]"]`)
        const labelEl = input?.closest('.form-check')?.querySelector('.form-check-label')
        let label = String(labelEl?.textContent || badgeKey).replace(/\s+/g, ' ').trim()
        if (label.toLowerCase().startsWith('use ')) label = label.slice(4).trim()
        options.push({
          value: badgeKey,
          label,
          enabled: input ? input.checked : false
        })
      })
      return options
    }

    const getLanguageCountPreviewSelectedKey = (cfg) => {
      const state = ensureResolutionPreviewState(cfg)
      const options = getLanguageCountPreviewOptions(cfg)
      const values = new Set(options.map(option => option.value))
      const current = String(state.language_count || '').trim()
      if (current && values.has(current)) return current
      const fallback = options.find(option => option.enabled)?.value || options[0]?.value || ''
      state.language_count = fallback
      return fallback
    }

    const setLanguageCountPreviewSelectedKey = (cfg, badgeKey) => {
      const state = ensureResolutionPreviewState(cfg)
      state.language_count = String(badgeKey || '').trim()
    }

    const getLanguageCountPreviewOverrideEntries = (cfg) => {
      const config = getOverlaySourceOverrideConfig(cfg)
      const section = cfg?.container?.querySelector('[data-overlay-source-editor="true"]')
      const hiddenHost = section?.querySelector('[data-overlay-source-hidden]')
      if (!config || !hiddenHost) return []
      return readOverlaySourceOverrideState(cfg, config, hiddenHost)
    }

    const getLanguageCountRenderPayload = (cfg) => {
      const overrideEntries = getLanguageCountPreviewOverrideEntries(cfg)
      const badgeKey = getLanguageCountPreviewSelectedKey(cfg)
      const override = overrideEntries.find(entry => entry.badgeKey === badgeKey && entry.sourceType && entry.value)
      return {
        overlay_id: cfg.id,
        language_count: {
          badge_key: badgeKey,
          source_type: override?.sourceType || '',
          source_value: override?.value || '',
          variant: getLanguageCountVariant(cfg)
        }
      }
    }

    const getFlagsPreviewOverrideEntries = (cfg) => {
      const config = getOverlaySourceOverrideConfig(cfg)
      const section = cfg?.container?.querySelector('[data-overlay-source-editor="true"]')
      const hiddenHost = section?.querySelector('[data-overlay-source-hidden]')
      if (!config || !hiddenHost) return []
      return readOverlaySourceOverrideState(cfg, config, hiddenHost)
    }

    const resolveFlagPreviewImage = (cfg, previewItem, useSquareFlags) => {
      const overrideEntries = getFlagsPreviewOverrideEntries(cfg)
      const badgeKey = String(previewItem?.badgeKey || '').trim()
      const override = overrideEntries.find(entry => entry.badgeKey === badgeKey && entry.sourceType && entry.value)
      if (override) {
        return buildOverlaySourcePreviewUrl(override.sourceType, override.value)
      }
      return useSquareFlags ? previewItem?.square : previewItem?.round
    }

    const getSingleBadgeOverlayPreviewDefaultKey = (cfg) => {
      const imageUrl = String(cfg?.image || '').trim()
      if (!imageUrl) return ''
      try {
        const url = new URL(imageUrl, window.location.origin)
        const parts = String(url.pathname || '').split('/')
        const rawName = parts[parts.length - 1] || ''
        return decodeURIComponent(rawName.replace(/\.[^.]+$/, '')).trim()
      } catch {
        const rawName = imageUrl.split('/').pop() || ''
        try {
          return decodeURIComponent(rawName.replace(/\.[^.]+$/, '')).trim()
        } catch {
          return rawName.replace(/\.[^.]+$/, '').trim()
        }
      }
    }

    const getSingleBadgeOverlayFamily = (cfg) => {
      return SINGLE_BADGE_OVERLAY_FAMILY_BY_ID[String(cfg?.id || '').trim()] || ''
    }

    const getFixedBadgeOverlayFamily = (cfg) => {
      return FIXED_BADGE_OVERLAY_FAMILY_BY_ID[String(cfg?.id || '').trim()] || ''
    }

    const getFixedBadgeOverlayKey = (cfg) => {
      return FIXED_BADGE_OVERLAY_KEY_BY_ID[String(cfg?.id || '').trim()] || ''
    }

    const getBundledOverlayKeyOptions = (cfg) => {
      if (Array.isArray(cfg?.bundledPreviewKeyOptions) && cfg.bundledPreviewKeyOptions.length) {
        return cfg.bundledPreviewKeyOptions
      }
      return []
    }

    const getBundledOverlayPreviewKeyOptions = async (cfg) => {
      const family = getSingleBadgeOverlayFamily(cfg)
      if (!family) return []
      if (bundledOverlayKeyOptionsCache.has(family)) {
        const cached = bundledOverlayKeyOptionsCache.get(family)
        if (cfg) cfg.bundledPreviewKeyOptions = cached
        return cached
      }
      if (bundledOverlayKeyOptionsInflight.has(family)) {
        return bundledOverlayKeyOptionsInflight.get(family)
      }

      const request = fetch(`/overlay-preview-keys?family=${encodeURIComponent(family)}`)
        .then(async response => {
          if (!response.ok) {
            let message = `HTTP ${response.status}`
            try {
              const payload = await response.json()
              message = payload?.message || payload?.error || message
            } catch {
            }
            throw new Error(message)
          }
          const payload = await response.json()
          const options = Array.isArray(payload?.keys)
            ? payload.keys
              .map(value => String(value || '').trim())
              .filter(Boolean)
              .map(value => ({ value, label: value }))
            : []
          bundledOverlayKeyOptionsCache.set(family, options)
          if (cfg) cfg.bundledPreviewKeyOptions = options
          return options
        })
        .catch(error => {
          console.warn('[OverlayBoards] Failed to load bundled overlay preview keys', { family, error })
          return []
        })
        .finally(() => {
          bundledOverlayKeyOptionsInflight.delete(family)
        })

      bundledOverlayKeyOptionsInflight.set(family, request)
      return request
    }

    const getSingleBadgeOverlayPreviewStateKey = (cfg) => {
      if (cfg?.id === 'overlay_network') return 'network'
      if (cfg?.id === 'overlay_studio') return 'studio'
      return ''
    }

    const getSingleBadgeOverlayPreviewSelectedKey = (cfg) => {
      const stateKey = getSingleBadgeOverlayPreviewStateKey(cfg)
      const state = ensureResolutionPreviewState(cfg)
      const current = String(state[stateKey] || '').trim()
      if (current) return current
      const fallback = getSingleBadgeOverlayPreviewDefaultKey(cfg)
      state[stateKey] = fallback
      return fallback
    }

    const setSingleBadgeOverlayPreviewSelectedKey = (cfg, badgeKey) => {
      const stateKey = getSingleBadgeOverlayPreviewStateKey(cfg)
      const state = ensureResolutionPreviewState(cfg)
      state[stateKey] = String(badgeKey || '').trim()
    }

    const getSingleBadgeOverlayPreviewOverrideEntries = (cfg) => {
      const config = getOverlaySourceOverrideConfig(cfg)
      const section = cfg?.container?.querySelector('[data-overlay-source-editor="true"]')
      const hiddenHost = section?.querySelector('[data-overlay-source-hidden]')
      if (!config || !hiddenHost) return []
      return readOverlaySourceOverrideState(cfg, config, hiddenHost)
    }

    const getSingleBadgeOverlayRenderPayload = (cfg, family, variantResolver) => {
      const overrideEntries = getSingleBadgeOverlayPreviewOverrideEntries(cfg)
      const badgeKey = getSingleBadgeOverlayPreviewSelectedKey(cfg)
      const override = overrideEntries.find(entry => entry.badgeKey === badgeKey && entry.sourceType && entry.value)
      return {
        overlay_id: cfg.id,
        [family]: {
          badge_key: badgeKey,
          source_type: override?.sourceType || '',
          source_value: override?.value || '',
          variant: typeof variantResolver === 'function' ? variantResolver(cfg) : ''
        }
      }
    }

    const getFixedBadgeOverlayPreviewOverrideEntries = (cfg) => {
      const config = getOverlaySourceOverrideConfig(cfg)
      const section = cfg?.container?.querySelector('[data-overlay-source-editor="true"]')
      const hiddenHost = section?.querySelector('[data-overlay-source-hidden]')
      if (!config || !hiddenHost) return []
      return readOverlaySourceOverrideState(cfg, config, hiddenHost)
    }

    const getFixedBadgeOverlayRenderPayload = (cfg) => {
      const family = getFixedBadgeOverlayFamily(cfg)
      const badgeKey = getFixedBadgeOverlayKey(cfg)
      const overrideEntries = getFixedBadgeOverlayPreviewOverrideEntries(cfg)
      const override = overrideEntries.find(entry => entry.badgeKey === badgeKey && entry.sourceType && entry.value)
      return {
        overlay_id: cfg.id,
        [family]: {
          badge_key: badgeKey,
          source_type: override?.sourceType || '',
          source_value: override?.value || '',
          variant: ''
        }
      }
    }

    const getResolutionPreviewOptionsForFamily = (cfg, family) => {
      if (!cfg?.container) return []
      const templateName = cfg.container.dataset.overlayTemplate
      const familyDef = getResolutionToggleFamilyDef(family)
      if (!templateName || !familyDef) return []
      const options = []
      const childKeys = getToggleFamilyChildKeys(cfg, family)
      childKeys.forEach(toggleKey => {
        const badgeKey = String(toggleKey || '').trim().replace(/^use_/, '')
        if (!badgeKey) return
        const input = cfg.container.querySelector(`[name="${templateName}[${toggleKey}]"]`)
        const labelEl = input?.closest('.form-check')?.querySelector('.form-check-label')
        let label = String(labelEl?.textContent || badgeKey).replace(/\s+/g, ' ').trim()
        if (label.toLowerCase().startsWith('use ')) {
          label = label.slice(4).trim()
        }
        options.push({
          value: badgeKey,
          label,
          enabled: input ? input.checked : false
        })
      })
      return options
    }

    const ensureResolutionPreviewState = (cfg) => {
      if (!cfg) return { resolution: '', edition: '' }
      if (!cfg.previewSelection || typeof cfg.previewSelection !== 'object') {
        cfg.previewSelection = { resolution: '', edition: '' }
      }
      return cfg.previewSelection
    }

    const pickDefaultResolutionPreviewKey = (cfg, family) => {
      const options = getResolutionPreviewOptionsForFamily(cfg, family)
      return options.find(option => option.enabled)?.value || options[0]?.value || ''
    }

    const getResolutionPreviewSelectedKey = (cfg, family) => {
      const state = ensureResolutionPreviewState(cfg)
      const options = getResolutionPreviewOptionsForFamily(cfg, family)
      const values = new Set(options.map(option => option.value))
      const current = String(state[family] || '').trim()
      if (current && values.has(current)) return current
      const fallback = pickDefaultResolutionPreviewKey(cfg, family)
      state[family] = fallback
      return fallback
    }

    const setResolutionPreviewSelectedKey = (cfg, family, badgeKey) => {
      const state = ensureResolutionPreviewState(cfg)
      state[family] = String(badgeKey || '').trim()
    }

    const getFlagPreviewStateKey = (slotIndex) => `flags_${slotIndex + 1}`

    const getFlagPreviewOptions = (cfg) => {
      const config = getOverlaySourceOverrideConfig(cfg)
      if (!config) return []
      return getOverlaySourceOverrideKeyOptions(cfg, config)
        .filter(option => Boolean(FLAG_PREVIEW_METADATA[String(option.value || '').trim()]))
        .map(option => {
          const key = String(option.value || '').trim()
          const meta = FLAG_PREVIEW_METADATA[key] || {}
          return {
            value: key,
            label: meta.text || option.label || key.toUpperCase(),
            enabled: Boolean(option.enabled),
            previewKey: meta.previewKey || key,
            text: meta.text || key.toUpperCase()
          }
        })
    }

    const pickDefaultFlagPreviewKeys = (cfg) => {
      const options = getFlagPreviewOptions(cfg)
      const values = new Set(options.map(option => option.value))
      const ordered = []

      FLAG_PREVIEW_DEFAULT_KEYS.forEach((key) => {
        if (values.has(key) && !ordered.includes(key)) ordered.push(key)
      })

      options.forEach((option) => {
        if (option.enabled && !ordered.includes(option.value)) ordered.push(option.value)
      })

      options.forEach((option) => {
        if (!ordered.includes(option.value)) ordered.push(option.value)
      })

      return ordered.slice(0, FLAG_PREVIEW_SLOT_COUNT)
    }

    const getFlagPreviewSelectedKeys = (cfg) => {
      const state = ensureResolutionPreviewState(cfg)
      const options = getFlagPreviewOptions(cfg)
      const values = new Set(options.map(option => option.value))
      const selected = []

      for (let i = 0; i < FLAG_PREVIEW_SLOT_COUNT; i += 1) {
        const current = String(state[getFlagPreviewStateKey(i)] || '').trim()
        if (current && values.has(current) && !selected.includes(current)) {
          selected.push(current)
        }
      }

      pickDefaultFlagPreviewKeys(cfg).forEach((key) => {
        if (!selected.includes(key)) selected.push(key)
      })

      const normalized = selected.slice(0, FLAG_PREVIEW_SLOT_COUNT)
      normalized.forEach((key, idx) => {
        state[getFlagPreviewStateKey(idx)] = key
      })
      return normalized
    }

    const setFlagPreviewSelectedKey = (cfg, slotIndex, badgeKey) => {
      const state = ensureResolutionPreviewState(cfg)
      state[getFlagPreviewStateKey(slotIndex)] = String(badgeKey || '').trim()
    }

    const buildFlagPreviewItems = (cfg) => {
      const optionMap = new Map(getFlagPreviewOptions(cfg).map(option => [option.value, option]))
      return getFlagPreviewSelectedKeys(cfg)
        .map((key) => {
          const option = optionMap.get(key)
          if (!option) return null
          const previewKey = option.previewKey || key
          const text = option.text || option.label || key.toUpperCase()
          return {
            badgeKey: key,
            previewKey,
            text,
            round: buildBundledOverlayPreviewUrl('flag', previewKey, 'round'),
            square: buildBundledOverlayPreviewUrl('flag', previewKey, 'square')
          }
        })
        .filter(Boolean)
    }

    const getResolutionPreviewOverrideEntries = (cfg) => {
      const config = getOverlaySourceOverrideConfig(cfg)
      const section = cfg?.container?.querySelector('[data-overlay-source-editor="true"]')
      const hiddenHost = section?.querySelector('[data-overlay-source-hidden]')
      if (!config || !hiddenHost) return []
      return readOverlaySourceOverrideState(cfg, config, hiddenHost)
    }

    const resolveResolutionPreviewImage = (cfg, family) => {
      const badgeKey = getResolutionPreviewSelectedKey(cfg, family)
      if (!badgeKey) return ''
      const overrideEntry = getResolutionPreviewOverrideEntries(cfg).find(entry => {
        return entry.badgeKey === badgeKey && entry.sourceType && entry.value
      })
      if (overrideEntry) {
        return buildOverlaySourcePreviewUrl(overrideEntry.sourceType, overrideEntry.value)
      }
      return buildBundledOverlayPreviewUrl(family, badgeKey)
    }

    const getResolutionToggleState = (cfg) => {
      if (cfg.id !== 'overlay_resolution') {
        return { useResolution: true, useEdition: true }
      }
      const useResolutionToggle = getTemplateInput(cfg, 'use_resolution')
      const useEditionToggle = getTemplateInput(cfg, 'use_edition')
      return {
        useResolution: useResolutionToggle ? useResolutionToggle.checked : true,
        useEdition: useEditionToggle ? useEditionToggle.checked : true
      }
    }

    const syncAudioCodecBackdropHeight = (cfg, emit = true) => {
      if (cfg.id !== 'overlay_audio_codec') return
      const style = (cfg.styleInput?.value || 'compact').toLowerCase()
      const height = style === 'standard' ? 189 : 105
      setBackdropHeight(cfg, height, emit)
    }

    const syncResolutionBackdropHeight = (cfg, emit = true) => {
      if (cfg.id !== 'overlay_resolution') return
      const { useResolution, useEdition } = getResolutionToggleState(cfg)
      const height = useResolution && useEdition ? 189 : 105
      setBackdropHeight(cfg, height, emit)
    }

    const syncResolutionEditionVisibility = (cfg, emit = true) => {
      if (cfg.id !== 'overlay_resolution') return
      if (!cfg.container) return
      const templateName = cfg.container.dataset.overlayTemplate
      if (!templateName) return
      const { useResolution, useEdition } = getResolutionToggleState(cfg)
      const hideBackdropControls = useResolution && useEdition
      const keys = [
        'back_align',
        'back_color',
        'back_height',
        'back_width',
        'back_line_color',
        'back_line_width',
        'back_padding',
        'back_radius'
      ]
      keys.forEach((key) => {
        const input = cfg.container.querySelector(`[name="${templateName}[${key}]"]`)
        if (!input) return
        const group = input.closest('.rgba-group') || input.closest('.input-group') || input.closest('.form-check') || input.parentElement
        if (group) {
          group.classList.toggle('d-none', hideBackdropControls)
        }
        input.disabled = hideBackdropControls
        if (emit) {
          input.dispatchEvent(new Event('change', { bubbles: true }))
        }
      })
    }

    const ensureResolutionToggleFamilyGroups = (cfg) => {
      if (cfg.id !== 'overlay_resolution' || !cfg.container) return
      const templateName = cfg.container.dataset.overlayTemplate
      if (!templateName) return

      RESOLUTION_TOGGLE_FAMILIES.forEach((familyDef) => {
        const masterInput = cfg.container.querySelector(`[name="${templateName}[${familyDef.masterKey}]"]`)
        const masterRow = masterInput?.closest('.form-check')
        if (!masterRow) return

        let group = cfg.container.querySelector(`[data-resolution-family-group="${familyDef.family}"]`)
        let copy = group?.querySelector(`[data-resolution-family-copy="${familyDef.family}"]`)
        let childContainer = group?.querySelector(`[data-resolution-family-children="${familyDef.family}"]`)

        if (!group) {
          group = document.createElement('section')
          group.className = 'border rounded-3 px-3 pt-3 pb-2 mb-3 bg-body-tertiary'
          group.dataset.resolutionFamilyGroup = familyDef.family

          const heading = document.createElement('div')
          heading.className = 'small text-uppercase fw-semibold text-secondary mb-2'
          heading.dataset.resolutionFamilyHeading = familyDef.family
          heading.textContent = familyDef.title

          copy = document.createElement('div')
          copy.className = 'form-text mb-2'
          copy.dataset.resolutionFamilyCopy = familyDef.family
          copy.textContent = familyDef.description

          childContainer = document.createElement('div')
          childContainer.className = 'pt-1'
          childContainer.dataset.resolutionFamilyChildren = familyDef.family

          const parent = masterRow.parentElement
          if (!parent) return
          parent.insertBefore(group, masterRow)
          group.appendChild(heading)
          group.appendChild(masterRow)
          group.appendChild(copy)
          group.appendChild(childContainer)
        } else {
          group.insertBefore(masterRow, copy || childContainer || null)
        }

        let previewWrap = group.querySelector(`[data-resolution-preview-wrap="${familyDef.family}"]`)
        let previewSelect = group.querySelector(`[data-resolution-preview-select="${familyDef.family}"]`)
        if (!previewWrap) {
          previewWrap = document.createElement('div')
          previewWrap.className = 'mb-2'
          previewWrap.dataset.resolutionPreviewWrap = familyDef.family
          previewWrap.innerHTML = `
            <label class="form-label small fw-semibold mb-1">Preview badge</label>
            <select class="form-select form-select-sm" data-resolution-preview-select="${familyDef.family}"></select>
          `
          if (copy) {
            copy.insertAdjacentElement('afterend', previewWrap)
          } else if (childContainer) {
            group.insertBefore(previewWrap, childContainer)
          } else {
            group.appendChild(previewWrap)
          }
          previewSelect = previewWrap.querySelector(`[data-resolution-preview-select="${familyDef.family}"]`)
        }
        if (previewSelect && previewSelect.dataset.listenerAdded !== 'true') {
          previewSelect.dataset.listenerAdded = 'true'
          previewSelect.addEventListener('change', () => {
            setResolutionPreviewSelectedKey(cfg, familyDef.family, previewSelect.value)
            refreshResolutionOverlayPreview(cfg)
          })
        }

        const childKeys = getToggleFamilyChildKeys(cfg, familyDef.family)
        childKeys.forEach((key) => {
          const input = cfg.container.querySelector(`[name="${templateName}[${key}]"]`)
          const row = input?.closest('.form-check')
          if (row && childContainer) {
            childContainer.appendChild(row)
          }
        })
      })
      syncResolutionPreviewControls(cfg)
    }

    const syncResolutionToggleFamilyVisibility = (cfg, family, keys, enabled) => {
      if (cfg.id !== 'overlay_resolution' || !cfg.container) return
      const templateName = cfg.container.dataset.overlayTemplate
      if (!templateName) return

      const familyGroup = cfg.container.querySelector(`[data-resolution-family-group="${family}"]`)
      if (familyGroup) {
        familyGroup.classList.toggle('opacity-75', !enabled)
      }

      const childContainer = cfg.container.querySelector(`[data-resolution-family-children="${family}"]`)
      if (childContainer) {
        childContainer.classList.toggle('d-none', !enabled)
      }

      keys.forEach((key) => {
        const input = cfg.container.querySelector(`[name="${templateName}[${key}]"]`)
        if (!input) return
        const group = input.closest('.form-check') || input.parentElement
        if (group && !childContainer) {
          group.classList.toggle('d-none', !enabled)
        }
        input.disabled = !enabled
      })
    }

    const syncResolutionChildToggleVisibility = (cfg) => {
      if (cfg.id !== 'overlay_resolution' || !cfg.container) return
      const { useResolution, useEdition } = getResolutionToggleState(cfg)
      syncResolutionToggleFamilyVisibility(cfg, 'resolution', getToggleFamilyChildKeys(cfg, 'resolution'), useResolution)
      syncResolutionToggleFamilyVisibility(cfg, 'edition', getToggleFamilyChildKeys(cfg, 'edition'), useEdition)
      syncResolutionPreviewControls(cfg)
    }

    const syncResolutionToggleWarning = (cfg) => {
      if (cfg.id !== 'overlay_resolution' || !cfg.container) return
      const { useResolution, useEdition } = getResolutionToggleState(cfg)
      let warning = cfg.container.querySelector('[data-resolution-toggle-warning]')
      if (!warning) {
        warning = document.createElement('div')
        warning.className = 'alert alert-warning py-2 px-3 mb-2 small d-none'
        warning.dataset.resolutionToggleWarning = 'true'
        warning.textContent = 'Both Use Resolution and Use Edition are off. This default will load but produce no overlays.'
        const anchor = cfg.container.querySelector('.overlay-detail-actions') || cfg.container.querySelector('.form-check')
        if (anchor) {
          anchor.insertAdjacentElement('afterend', warning)
        } else {
          cfg.container.prepend(warning)
        }
      }
      warning.classList.toggle('d-none', useResolution || useEdition)
    }

    const bindResolutionPreviewInputs = (cfg) => {
      if (cfg.id !== 'overlay_resolution' || !cfg.container) return
      const templateName = cfg.container.dataset.overlayTemplate
      if (!templateName) return
      const toggleKeys = ['use_resolution', 'use_edition', ...getToggleFamilyChildKeys(cfg, 'resolution'), ...getToggleFamilyChildKeys(cfg, 'edition')]
      toggleKeys.forEach((toggleKey) => {
        const input = cfg.container.querySelector(`[name="${templateName}[${toggleKey}]"]`)
        if (!input || input.dataset.resolutionPreviewBound === 'true') return
        input.dataset.resolutionPreviewBound = 'true'
        input.addEventListener('change', () => {
          syncResolutionChildToggleVisibility(cfg)
          syncResolutionToggleWarning(cfg)
          refreshResolutionOverlayPreview(cfg)
        })
      })
    }

    const getOverlaySourceOverrideConfig = (cfg) => {
      if (!cfg.container) return null
      const raw = String(cfg.container.dataset.overlaySourceOverrides || '').trim()
      if (!raw) return null
      try {
        const parsed = JSON.parse(raw)
        if (!parsed || parsed.enabled === false) return null
        const sourceTypes = Array.isArray(parsed.source_types) && parsed.source_types.length
          ? parsed.source_types.map(item => String(item || '').trim()).filter(Boolean)
          : ['file', 'url', 'git', 'repo']
        return {
          title: String(parsed.title || 'Image Source Overrides').trim(),
          description: String(parsed.description || 'Advanced source overrides for this overlay.').trim(),
          addLabel: String(parsed.add_label || 'Add override').trim(),
          keyMode: String(parsed.key_mode || '').trim().toLowerCase(),
          fixedKey: String(parsed.fixed_key || '').trim(),
          keyPlaceholder: String(parsed.key_placeholder || '').trim(),
          keyFields: Array.isArray(parsed.key_fields)
            ? parsed.key_fields.map(item => String(item || '').trim()).filter(Boolean)
            : [],
          sourceTypes,
          excludeToggleKeys: Array.isArray(parsed.exclude_toggle_keys)
            ? parsed.exclude_toggle_keys.map(item => String(item || '').trim()).filter(Boolean)
            : []
        }
      } catch (error) {
        console.warn('[OverlaySourceOverrides] Failed to parse config', { overlayId: cfg.id, error })
        return null
      }
    }

    const decodeOverlaySourceOverrideVarName = (sourceTypes, varName) => {
      const normalizedVarName = String(varName || '').trim()
      if (!normalizedVarName) return null
      for (const sourceType of sourceTypes) {
        if (normalizedVarName === sourceType) {
          return { sourceType, badgeKey: '' }
        }
        const prefix = `${sourceType}_`
        if (normalizedVarName.startsWith(prefix)) {
          return { sourceType, badgeKey: normalizedVarName.slice(prefix.length) }
        }
      }
      return null
    }

    const encodeOverlaySourceOverrideVarName = (sourceType, badgeKey) => {
      const normalizedType = String(sourceType || '').trim()
      const normalizedKey = String(badgeKey || '').trim()
      return normalizedKey ? `${normalizedType}_${normalizedKey}` : normalizedType
    }

    const getOverlaySourceOverrideKeyOptions = (cfg, config) => {
      const options = []
      if (!cfg.container) return options
      if (config.keyMode === 'fixed_key' && config.fixedKey) {
        return [{ value: config.fixedKey, label: config.fixedKey }]
      }
      if (config.keyMode === 'bundled_preview_keys') {
        return getBundledOverlayKeyOptions(cfg)
      }
      if (config.keyMode === 'from_select_options') {
        const seen = new Set()
        ;(config.keyFields || []).forEach((fieldKey) => {
          const input = getTemplateInput(cfg, fieldKey)
          if (!input || input.tagName !== 'SELECT') return
          Array.from(input.options || []).forEach((option) => {
            const value = String(option.value || '').trim()
            if (!value || seen.has(value)) return
            seen.add(value)
            options.push({
              value,
              label: String(option.textContent || value).trim() || value
            })
          })
        })
        return options
      }
      if (config.keyMode !== 'from_use_toggles') return options

      const templateName = cfg.container.dataset.overlayTemplate
      if (!templateName) return options

      const seen = new Set()
      const excludedToggleKeys = new Set(config.excludeToggleKeys || [])
      const toggleInputs = Array.from(cfg.container.querySelectorAll(`[name^="${templateName}[use_"]`))
        .filter(input => String(input?.type || '').toLowerCase() === 'checkbox')

      toggleInputs.forEach(input => {
        const keyMatch = /\[([^\]]+)\]$/.exec(String(input.name || ''))
        const toggleKey = String(keyMatch?.[1] || '').trim()
        if (!toggleKey.startsWith('use_') || excludedToggleKeys.has(toggleKey)) return
        const badgeKey = toggleKey.slice(4)
        if (!badgeKey || seen.has(badgeKey)) return

        const labelEl = input.closest('.form-check')?.querySelector('.form-check-label')
        let label = String(labelEl?.textContent || badgeKey).replace(/\s+/g, ' ').trim()
        if (label.toLowerCase().startsWith('use ')) {
          label = label.slice(4).trim()
        }
        seen.add(badgeKey)
        options.push({ value: badgeKey, label })
      })

      return options
    }

    const createOverlaySourceOverrideHiddenInput = (cfg, hiddenHost, varName, value) => {
      const templateName = cfg.container?.dataset?.overlayTemplate
      if (!hiddenHost || !templateName) return null
      const input = document.createElement('input')
      input.type = 'hidden'
      input.name = `${templateName}[${varName}]`
      input.value = String(value || '').trim()
      input.dataset.default = ''
      input.dataset.overlaySourceOverride = 'true'
      hiddenHost.appendChild(input)
      return input
    }

    const materializeOverlaySourceOverrideSeed = (cfg, config, hiddenHost) => {
      if (!cfg.container || !hiddenHost || cfg.container.dataset.overlaySourceSeedApplied === 'true') return
      const rawSeed = String(cfg.container.dataset.overlaySourceSeed || '').trim()
      if (!rawSeed) {
        cfg.container.dataset.overlaySourceSeedApplied = 'true'
        return
      }
      try {
        const parsed = JSON.parse(rawSeed)
        if (Array.isArray(parsed)) {
          parsed.forEach(entry => {
            if (!entry || typeof entry !== 'object') return
            const varName = String(entry.key || '').trim()
            const value = String(entry.value || '').trim()
            if (!value) return
            if (!decodeOverlaySourceOverrideVarName(config.sourceTypes, varName)) return
            createOverlaySourceOverrideHiddenInput(cfg, hiddenHost, varName, value)
          })
        }
      } catch (error) {
        console.warn('[OverlaySourceOverrides] Failed to parse seed', { overlayId: cfg.id, error })
      }
      cfg.container.dataset.overlaySourceSeedApplied = 'true'
    }

    const readOverlaySourceOverrideState = (cfg, config, hiddenHost) => {
      materializeOverlaySourceOverrideSeed(cfg, config, hiddenHost)
      const state = []
      hiddenHost.querySelectorAll('input[data-overlay-source-override="true"]').forEach(input => {
        const varMatch = /\[([^\]]+)\]$/.exec(String(input.name || ''))
        const varName = String(varMatch?.[1] || '').trim()
        const decoded = decodeOverlaySourceOverrideVarName(config.sourceTypes, varName)
        const value = String(input.value || '').trim()
        if (!decoded || !value) return
        if (config.keyMode === 'from_use_toggles' && !decoded.badgeKey) return
        state.push({
          sourceType: decoded.sourceType,
          badgeKey: decoded.badgeKey,
          value
        })
      })
      return state
    }

    const syncResolutionPreviewControls = (cfg) => {
      if (cfg?.id !== 'overlay_resolution' || !cfg.container) return
      RESOLUTION_TOGGLE_FAMILIES.forEach((familyDef) => {
        const group = cfg.container.querySelector(`[data-resolution-family-group="${familyDef.family}"]`)
        const select = group?.querySelector(`[data-resolution-preview-select="${familyDef.family}"]`)
        if (!select) return
        const options = getResolutionPreviewOptionsForFamily(cfg, familyDef.family)
        const selected = getResolutionPreviewSelectedKey(cfg, familyDef.family)
        const masterInput = getTemplateInput(cfg, familyDef.masterKey)
        const enabled = masterInput ? masterInput.checked : true

        select.replaceChildren()
        options.forEach((option) => {
          const el = document.createElement('option')
          el.value = option.value
          el.textContent = option.label
          select.appendChild(el)
        })
        if (selected && options.some(option => option.value === selected)) {
          select.value = selected
        } else if (options[0]?.value) {
          setResolutionPreviewSelectedKey(cfg, familyDef.family, options[0].value)
          select.value = options[0].value
        }
        select.disabled = !enabled || options.length === 0
      })
    }

    const refreshResolutionOverlayPreview = (cfg) => {
      if (cfg?.id !== 'overlay_resolution' || !cfg.layer) return
      buildBackdropDataUrl(cfg).then(dataUrl => {
        if (!dataUrl) return
        cfg.layer.src = dataUrl
      })
    }

    const syncContentRatingPreviewControls = (cfg) => {
      if ((!isRegionalContentRatingOverlay(cfg) && !isCommonsenseContentRatingOverlay(cfg)) || !cfg.container) return
      const select = cfg.container.querySelector('[data-content-rating-preview-select="true"]')
      if (!select) return
      const options = getContentRatingPreviewOptions(cfg)
      const selected = getContentRatingPreviewSelectedKey(cfg)

      select.replaceChildren()
      options.forEach((option) => {
        const el = document.createElement('option')
        el.value = option.value
        el.textContent = option.label
        select.appendChild(el)
      })
      if (selected && options.some(option => option.value === selected)) {
        select.value = selected
      } else if (options[0]?.value) {
        setContentRatingPreviewSelectedKey(cfg, options[0].value)
        select.value = options[0].value
      }
      select.disabled = options.length === 0
    }

    const refreshContentRatingOverlayPreview = (cfg) => {
      if (!cfg?.layer || (!isRegionalContentRatingOverlay(cfg) && !isCommonsenseContentRatingOverlay(cfg))) return
      if (isCommonsenseContentRatingOverlay(cfg)) {
        const baseOverride = resolveContentRatingPreviewImage(cfg)
        buildCommonsenseDataUrl(cfg, baseOverride).then(dataUrl => {
          buildBackdropDataUrl(cfg, dataUrl).then(backdropUrl => {
            if (!backdropUrl) return
            cfg.layer.src = backdropUrl
          })
        })
        return
      }
      const baseOverride = resolveContentRatingPreviewImage(cfg)
      buildBackdropDataUrl(cfg, baseOverride).then(dataUrl => {
        if (!dataUrl) return
        cfg.layer.src = dataUrl
      })
    }

    const ensureFlagsPreviewControl = (cfg) => {
      if (!isFlagsOverlay(cfg) || !cfg?.container) return
      const anchorInput = getTemplateInput(cfg, 'font')
      const anchorRow = anchorInput?.closest('.font-row') ||
        anchorInput?.closest('.rgba-group') ||
        anchorInput?.closest('.input-group') ||
        anchorInput?.closest('.mb-3') ||
        anchorInput?.parentElement
      if (!anchorRow) return

      let previewWrap = cfg.container.querySelector('[data-flag-preview-wrap]')
      if (!previewWrap) {
        previewWrap = document.createElement('div')
        previewWrap.className = 'mb-3 w-100'
        previewWrap.dataset.flagPreviewWrap = 'true'
        previewWrap.style.flexBasis = '100%'
        previewWrap.style.width = '100%'
        previewWrap.innerHTML = `
          <label class="form-label small fw-semibold mb-1">Preview flags</label>
          <div class="row g-2" data-flag-preview-row="true">
            <div class="col-12 col-md-4">
              <select class="form-select form-select-sm" data-flag-preview-select="0"></select>
            </div>
            <div class="col-12 col-md-4">
              <select class="form-select form-select-sm" data-flag-preview-select="1"></select>
            </div>
            <div class="col-12 col-md-4">
              <select class="form-select form-select-sm" data-flag-preview-select="2"></select>
            </div>
          </div>
        `
      }

      anchorRow.insertAdjacentElement('beforebegin', previewWrap)

      previewWrap.querySelectorAll('[data-flag-preview-select]').forEach((select) => {
        if (select.dataset.listenerAdded === 'true') return
        select.dataset.listenerAdded = 'true'
        select.addEventListener('change', () => {
          const slotIndex = Number(select.dataset.flagPreviewSelect)
          setFlagPreviewSelectedKey(cfg, slotIndex, select.value)
          syncFlagsPreviewControls(cfg)
          refreshFlagsOverlayPreview(cfg)
        })
      })
    }

    const syncFlagsPreviewControls = (cfg) => {
      if (!isFlagsOverlay(cfg) || !cfg?.container) return
      const options = getFlagPreviewOptions(cfg)
      const selectedKeys = getFlagPreviewSelectedKeys(cfg)
      const selects = cfg.container.querySelectorAll('[data-flag-preview-select]')
      selects.forEach((select, index) => {
        select.replaceChildren()
        options.forEach((option) => {
          const el = document.createElement('option')
          el.value = option.value
          el.textContent = option.label
          select.appendChild(el)
        })
        const selected = selectedKeys[index] || options[0]?.value || ''
        if (selected) {
          select.value = selected
          setFlagPreviewSelectedKey(cfg, index, selected)
        }
        select.disabled = options.length === 0
      })
    }

    const refreshFlagsOverlayPreview = (cfg) => {
      if (!cfg?.layer) return
      buildFlagsCompositeDataUrl(cfg).then(dataUrl => {
        cfg.layer.src = dataUrl
      })
    }

    const bindFlagsPreviewInputs = (cfg) => {
      if (!isFlagsOverlay(cfg) || !cfg?.container) return
      const templateName = cfg.container.dataset.overlayTemplate
      if (!templateName) return
      const selectors = Array.from(cfg.container.querySelectorAll(`[name^="${templateName}[use_"]`))
        .filter(input => String(input?.type || '').toLowerCase() === 'checkbox')
      selectors.forEach((input) => {
        if (input.dataset.flagPreviewBound === 'true') return
        input.dataset.flagPreviewBound = 'true'
        input.addEventListener('change', () => {
          syncFlagsPreviewControls(cfg)
          refreshFlagsOverlayPreview(cfg)
        })
      })
    }

    const ensureContentRatingPreviewControl = (cfg) => {
      if ((!isRegionalContentRatingOverlay(cfg) && !isCommonsenseContentRatingOverlay(cfg)) || !cfg.container) return
      const anchorInput = isCommonsenseContentRatingOverlay(cfg)
        ? getTemplateInput(cfg, 'post_text')
        : getTemplateInput(cfg, 'color')
      const anchorRow = anchorInput?.closest('.input-group') || anchorInput?.closest('.mb-3') || anchorInput?.parentElement
      if (!anchorRow) return

      let previewWrap = cfg.container.querySelector('[data-content-rating-preview-wrap]')
      let previewSelect = cfg.container.querySelector('[data-content-rating-preview-select]')
      if (!previewWrap) {
        previewWrap = document.createElement('div')
        previewWrap.className = 'mb-3'
        previewWrap.dataset.contentRatingPreviewWrap = 'true'
        previewWrap.innerHTML = `
          <label class="form-label small fw-semibold mb-1">${isCommonsenseContentRatingOverlay(cfg) ? 'Preview rating' : 'Preview badge'}</label>
          <select class="form-select form-select-sm" data-content-rating-preview-select="true"></select>
        `
        anchorRow.insertAdjacentElement('afterend', previewWrap)
        previewSelect = previewWrap.querySelector('[data-content-rating-preview-select]')
      }

      if (previewSelect && previewSelect.dataset.listenerAdded !== 'true') {
        previewSelect.dataset.listenerAdded = 'true'
        previewSelect.addEventListener('change', () => {
          setContentRatingPreviewSelectedKey(cfg, previewSelect.value)
          refreshContentRatingOverlayPreview(cfg)
        })
      }
    }

    const ensureOverlayTextPreviewControl = (cfg) => {
      const mode = getOverlayTextPreviewMode(cfg)
      if (!mode || !cfg?.container) return

      const anchorInput = getTemplateInput(cfg, 'font') || (mode === 'status' ? getTemplateInput(cfg, 'text_airing') : null)
      const anchorRow = anchorInput?.closest('.font-row') ||
        anchorInput?.closest('.rgba-group') ||
        anchorInput?.closest('.input-group') ||
        anchorInput?.closest('.mb-3') ||
        anchorInput?.parentElement
      if (!anchorRow) return

      let previewWrap = cfg.container.querySelector('[data-overlay-text-preview-wrap]')
      let previewSelect = cfg.container.querySelector('[data-overlay-text-preview-select]')
      if (!previewWrap) {
        let label = 'Preview badge'
        if (mode === 'runtime') label = 'Preview runtime'
        else if (mode === 'status') label = 'Preview status'
        else if (mode === 'episode_info') label = 'Preview text'
        previewWrap = document.createElement('div')
        previewWrap.className = 'mb-3 w-100'
        previewWrap.dataset.overlayTextPreviewWrap = 'true'
        previewWrap.style.flexBasis = '100%'
        previewWrap.style.width = '100%'
        previewWrap.innerHTML = `
          <label class="form-label small fw-semibold mb-1">${label}</label>
          <select class="form-select form-select-sm" data-overlay-text-preview-select="true"></select>
        `
        previewSelect = previewWrap.querySelector('[data-overlay-text-preview-select]')
      }

      anchorRow.insertAdjacentElement('beforebegin', previewWrap)

      if (previewSelect && previewSelect.dataset.listenerAdded !== 'true') {
        previewSelect.dataset.listenerAdded = 'true'
        previewSelect.addEventListener('change', () => {
          setOverlayTextPreviewSelectedValue(cfg, previewSelect.value)
          syncOverlayTextPreviewTextInput(cfg)
          refreshOverlayTextPreview(cfg)
        })
      }
    }

    const syncOverlayTextPreviewControls = (cfg) => {
      const mode = getOverlayTextPreviewMode(cfg)
      if (!mode || !cfg?.container) return
      const select = cfg.container.querySelector('[data-overlay-text-preview-select="true"]')
      if (!select) return

      const options = getOverlayTextPreviewOptions(cfg)
      const selected = getOverlayTextPreviewSelectedValue(cfg)
      select.replaceChildren()
      options.forEach((option) => {
        const el = document.createElement('option')
        el.value = option.value
        el.textContent = option.label
        select.appendChild(el)
      })

      if (selected && options.some(option => option.value === selected)) {
        select.value = selected
      } else if (options[0]?.value) {
        setOverlayTextPreviewSelectedValue(cfg, options[0].value)
        select.value = options[0].value
      }
      select.disabled = options.length === 0
      syncOverlayTextPreviewTextInput(cfg)
    }

    const refreshOverlayTextPreview = (cfg) => {
      if (!cfg?.layer) return
      if (cfg.id === 'overlay_runtimes') {
        const { font } = getRuntimeVars(cfg)
        ensureRuntimeFontLoaded(font).then(family => {
          const { family: norm } = normalizeFontFile(font)
          const dataUrl = buildRuntimeDataUrl(cfg, family || norm)
          if (BACKDROP_TEXT_OVERLAYS.has(cfg.id)) {
            buildBackdropDataUrl(cfg, dataUrl).then(backdropUrl => {
              cfg.layer.src = backdropUrl
            })
            return
          }
          cfg.layer.src = dataUrl
        })
        return
      }

      if (cfg.id === 'overlay_status') {
        const vars = getStatusTextVars(cfg)
        ensureRuntimeFontLoaded(vars.font).then(family => {
          const { family: norm } = normalizeFontFile(vars.font)
          const dataUrl = buildSimpleTextDataUrl(cfg, vars, family || norm)
          if (BACKDROP_TEXT_OVERLAYS.has(cfg.id)) {
            buildBackdropDataUrl(cfg, dataUrl).then(backdropUrl => {
              cfg.layer.src = backdropUrl
            })
            return
          }
          cfg.layer.src = dataUrl
        })
        return
      }

      if (cfg.id === 'overlay_aspect' || cfg.id === 'overlay_video_format' || cfg.id === 'overlay_episode_info') {
        const vars = getSimpleTextVars(cfg)
        ensureRuntimeFontLoaded(vars.font).then(family => {
          const { family: norm } = normalizeFontFile(vars.font)
          const dataUrl = buildSimpleTextDataUrl(cfg, vars, family || norm)
          if (BACKDROP_TEXT_OVERLAYS.has(cfg.id)) {
            buildBackdropDataUrl(cfg, dataUrl).then(backdropUrl => {
              cfg.layer.src = backdropUrl
            })
            return
          }
          cfg.layer.src = dataUrl
        })
      }
    }

    const bindOverlayTextPreviewInputs = (cfg) => {
      const mode = getOverlayTextPreviewMode(cfg)
      if (!mode || !cfg?.container) return
      const templateName = cfg.container.dataset.overlayTemplate
      if (!templateName) return

      if (mode === 'toggle_text') {
        const toggleInputs = Array.from(cfg.container.querySelectorAll(`[name^="${templateName}[use_"]`))
          .filter(input => String(input?.type || '').toLowerCase() === 'checkbox')
        toggleInputs.forEach((input) => {
          if (input.dataset.overlayTextPreviewBound === 'true') return
          input.dataset.overlayTextPreviewBound = 'true'
          input.addEventListener('change', () => {
            syncOverlayTextPreviewControls(cfg)
            refreshOverlayTextPreview(cfg)
          })
        })
      }

      if (mode === 'status') {
        const selectors = [
          `[name="${templateName}[use_airing]"]`,
          `[name="${templateName}[use_returning]"]`,
          `[name="${templateName}[use_canceled]"]`,
          `[name="${templateName}[use_ended]"]`,
          `[name="${templateName}[text_airing]"]`,
          `[name="${templateName}[text_returning]"]`,
          `[name="${templateName}[text_canceled]"]`,
          `[name="${templateName}[text_ended]"]`
        ]
        const inputs = cfg.container.querySelectorAll(selectors.join(', '))
        inputs.forEach((input) => {
          if (input.dataset.overlayTextPreviewBound === 'true') return
          input.dataset.overlayTextPreviewBound = 'true'
          input.addEventListener('input', () => {
            syncOverlayTextPreviewControls(cfg)
            refreshOverlayTextPreview(cfg)
          })
          input.addEventListener('change', () => {
            syncOverlayTextPreviewControls(cfg)
            refreshOverlayTextPreview(cfg)
          })
        })
      }
    }

    const ensureSingleBadgeOverlayPreviewControl = (cfg) => {
      if (!cfg?.container || !cfg.styleInput || !['overlay_network', 'overlay_studio'].includes(cfg.id)) return
      const styleRow = cfg.styleInput.closest('.input-group') || cfg.styleInput.closest('.mb-3') || cfg.styleInput.parentElement
      if (!styleRow) return

      let previewWrap = cfg.container.querySelector('[data-single-badge-preview-wrap]')
      let previewInput = cfg.container.querySelector('[data-single-badge-preview-input]')
      let previewList = cfg.container.querySelector('[data-single-badge-preview-list]')
      if (!previewWrap) {
        previewWrap = document.createElement('div')
        previewWrap.className = 'mb-3'
        previewWrap.dataset.singleBadgePreviewWrap = 'true'
        previewWrap.innerHTML = `
          <label class="form-label small fw-semibold mb-1">Preview badge key</label>
          <input type="text" class="form-control form-control-sm" data-single-badge-preview-input="true" data-single-badge-preview-list-input="true">
          <datalist data-single-badge-preview-list="true"></datalist>
          <div class="form-text">Start typing to search bundled keys, or enter a custom key manually for edge cases.</div>
        `
        styleRow.insertAdjacentElement('afterend', previewWrap)
        previewInput = previewWrap.querySelector('[data-single-badge-preview-input]')
        previewList = previewWrap.querySelector('[data-single-badge-preview-list]')
      }

      if (previewInput && previewList && !previewInput.hasAttribute('list')) {
        const listId = `${cfg.instanceId}__single-badge-preview-list`
        previewList.id = listId
        previewInput.setAttribute('list', listId)
      }

      if (previewInput && previewInput.dataset.listenerAdded !== 'true') {
        previewInput.dataset.listenerAdded = 'true'
        previewInput.addEventListener('change', () => {
          setSingleBadgeOverlayPreviewSelectedKey(cfg, previewInput.value)
          refreshSingleBadgeOverlayPreview(cfg)
        })
        previewInput.addEventListener('blur', () => {
          setSingleBadgeOverlayPreviewSelectedKey(cfg, previewInput.value)
          refreshSingleBadgeOverlayPreview(cfg)
        })
      }
    }

    const ensureStreamingPreviewControl = (cfg) => {
      if (cfg?.id !== 'overlay_streaming' || !cfg.container || !cfg.styleInput) return
      const styleRow = cfg.styleInput.closest('.input-group') || cfg.styleInput.closest('.mb-3') || cfg.styleInput.parentElement
      if (!styleRow) return

      let previewWrap = cfg.container.querySelector('[data-streaming-preview-wrap]')
      let previewSelect = cfg.container.querySelector('[data-streaming-preview-select]')
      if (!previewWrap) {
        previewWrap = document.createElement('div')
        previewWrap.className = 'mb-3'
        previewWrap.dataset.streamingPreviewWrap = 'true'
        previewWrap.innerHTML = `
          <label class="form-label small fw-semibold mb-1">Preview badge</label>
          <select class="form-select form-select-sm" data-streaming-preview-select="true"></select>
        `
        styleRow.insertAdjacentElement('afterend', previewWrap)
        previewSelect = previewWrap.querySelector('[data-streaming-preview-select]')
      }

      if (previewSelect && previewSelect.dataset.listenerAdded !== 'true') {
        previewSelect.dataset.listenerAdded = 'true'
        previewSelect.addEventListener('change', () => {
          setStreamingPreviewSelectedKey(cfg, previewSelect.value)
          refreshStreamingOverlayPreview(cfg)
        })
      }
    }

    const ensureRibbonPreviewControl = (cfg) => {
      if (cfg?.id !== 'overlay_ribbon' || !cfg.container || !cfg.styleInput) return
      const styleRow = cfg.styleInput.closest('.input-group') || cfg.styleInput.closest('.mb-3') || cfg.styleInput.parentElement
      if (!styleRow) return

      let previewWrap = cfg.container.querySelector('[data-ribbon-preview-wrap]')
      let previewSelect = cfg.container.querySelector('[data-ribbon-preview-select]')
      if (!previewWrap) {
        previewWrap = document.createElement('div')
        previewWrap.className = 'mb-3'
        previewWrap.dataset.ribbonPreviewWrap = 'true'
        previewWrap.innerHTML = `
          <label class="form-label small fw-semibold mb-1">Preview badge</label>
          <select class="form-select form-select-sm" data-ribbon-preview-select="true"></select>
        `
        styleRow.insertAdjacentElement('afterend', previewWrap)
        previewSelect = previewWrap.querySelector('[data-ribbon-preview-select]')
      }

      if (previewSelect && previewSelect.dataset.listenerAdded !== 'true') {
        previewSelect.dataset.listenerAdded = 'true'
        previewSelect.addEventListener('change', () => {
          setRibbonPreviewSelectedKey(cfg, previewSelect.value)
          refreshRibbonOverlayPreview(cfg)
        })
      }
    }

    const ensureLanguageCountPreviewControl = (cfg) => {
      if (cfg?.id !== 'overlay_language_count' || !cfg.container) return
      const anchorInput = getTemplateInput(cfg, 'use_dual') || getTemplateInput(cfg, 'use_multi')
      const anchorRow = anchorInput?.closest('.form-check') || anchorInput?.closest('.input-group') || anchorInput?.closest('.mb-3') || anchorInput?.parentElement
      if (!anchorRow) return

      let previewWrap = cfg.container.querySelector('[data-language-count-preview-wrap]')
      let previewSelect = cfg.container.querySelector('[data-language-count-preview-select]')
      if (!previewWrap) {
        previewWrap = document.createElement('div')
        previewWrap.className = 'mb-3'
        previewWrap.dataset.languageCountPreviewWrap = 'true'
        previewWrap.innerHTML = `
          <label class="form-label small fw-semibold mb-1">Preview badge</label>
          <select class="form-select form-select-sm" data-language-count-preview-select="true"></select>
        `
        anchorRow.insertAdjacentElement('afterend', previewWrap)
        previewSelect = previewWrap.querySelector('[data-language-count-preview-select]')
      }

      if (previewSelect && previewSelect.dataset.listenerAdded !== 'true') {
        previewSelect.dataset.listenerAdded = 'true'
        previewSelect.addEventListener('change', () => {
          setLanguageCountPreviewSelectedKey(cfg, previewSelect.value)
          refreshLanguageCountOverlayPreview(cfg)
        })
      }
    }

    const ensureAudioCodecPreviewControl = (cfg) => {
      if (cfg?.id !== 'overlay_audio_codec' || !cfg.container || !cfg.styleInput) return
      const styleRow = cfg.styleInput.closest('.input-group') || cfg.styleInput.closest('.mb-3') || cfg.styleInput.parentElement
      if (!styleRow) return

      let previewWrap = cfg.container.querySelector('[data-audio-codec-preview-wrap]')
      let previewSelect = cfg.container.querySelector('[data-audio-codec-preview-select]')
      if (!previewWrap) {
        previewWrap = document.createElement('div')
        previewWrap.className = 'mb-3'
        previewWrap.dataset.audioCodecPreviewWrap = 'true'
        previewWrap.innerHTML = `
          <label class="form-label small fw-semibold mb-1">Preview badge</label>
          <select class="form-select form-select-sm" data-audio-codec-preview-select="true"></select>
        `
        styleRow.insertAdjacentElement('afterend', previewWrap)
        previewSelect = previewWrap.querySelector('[data-audio-codec-preview-select]')
      }

      if (previewSelect && previewSelect.dataset.listenerAdded !== 'true') {
        previewSelect.dataset.listenerAdded = 'true'
        previewSelect.addEventListener('change', () => {
          setAudioCodecPreviewSelectedKey(cfg, previewSelect.value)
          refreshAudioCodecOverlayPreview(cfg)
        })
      }
    }

    const syncAudioCodecPreviewControls = (cfg) => {
      if (cfg?.id !== 'overlay_audio_codec' || !cfg.container) return
      const select = cfg.container.querySelector('[data-audio-codec-preview-select]')
      if (!select) return
      const options = getAudioCodecPreviewOptions(cfg)
      const selected = getAudioCodecPreviewSelectedKey(cfg)

      select.replaceChildren()
      options.forEach((option) => {
        const el = document.createElement('option')
        el.value = option.value
        el.textContent = option.label
        select.appendChild(el)
      })
      if (selected && options.some(option => option.value === selected)) {
        select.value = selected
      } else if (options[0]?.value) {
        setAudioCodecPreviewSelectedKey(cfg, options[0].value)
        select.value = options[0].value
      }
      select.disabled = options.length === 0
    }

    const syncRibbonPreviewControls = (cfg) => {
      if (cfg?.id !== 'overlay_ribbon' || !cfg.container) return
      const select = cfg.container.querySelector('[data-ribbon-preview-select]')
      if (!select) return
      const options = getRibbonPreviewOptions(cfg)
      const selected = getRibbonPreviewSelectedKey(cfg)

      select.replaceChildren()
      options.forEach((option) => {
        const el = document.createElement('option')
        el.value = option.value
        el.textContent = option.label
        select.appendChild(el)
      })
      if (selected && options.some(option => option.value === selected)) {
        select.value = selected
      } else if (options[0]?.value) {
        setRibbonPreviewSelectedKey(cfg, options[0].value)
        select.value = options[0].value
      }
      select.disabled = options.length === 0
    }

    const syncLanguageCountPreviewControls = (cfg) => {
      if (cfg?.id !== 'overlay_language_count' || !cfg.container) return
      const select = cfg.container.querySelector('[data-language-count-preview-select]')
      if (!select) return
      const options = getLanguageCountPreviewOptions(cfg)
      const selected = getLanguageCountPreviewSelectedKey(cfg)

      select.replaceChildren()
      options.forEach((option) => {
        const el = document.createElement('option')
        el.value = option.value
        el.textContent = option.label
        select.appendChild(el)
      })
      if (selected && options.some(option => option.value === selected)) {
        select.value = selected
      } else if (options[0]?.value) {
        setLanguageCountPreviewSelectedKey(cfg, options[0].value)
        select.value = options[0].value
      }
      select.disabled = options.length === 0
    }

    const syncStreamingPreviewControls = (cfg) => {
      if (cfg?.id !== 'overlay_streaming' || !cfg.container) return
      const select = cfg.container.querySelector('[data-streaming-preview-select]')
      if (!select) return
      const options = getStreamingPreviewOptions(cfg)
      const selected = getStreamingPreviewSelectedKey(cfg)

      select.replaceChildren()
      options.forEach((option) => {
        const el = document.createElement('option')
        el.value = option.value
        el.textContent = option.label
        select.appendChild(el)
      })
      if (selected && options.some(option => option.value === selected)) {
        select.value = selected
      } else if (options[0]?.value) {
        setStreamingPreviewSelectedKey(cfg, options[0].value)
        select.value = options[0].value
      }
      select.disabled = options.length === 0
    }

    const syncSingleBadgeOverlayPreviewControls = (cfg) => {
      if (!cfg?.container || !['overlay_network', 'overlay_studio'].includes(cfg.id)) return
      const input = cfg.container.querySelector('[data-single-badge-preview-input]')
      const list = cfg.container.querySelector('[data-single-badge-preview-list]')
      if (!input) return
      const options = getBundledOverlayKeyOptions(cfg)
      if (list) {
        list.replaceChildren()
        options.forEach((option) => {
          const el = document.createElement('option')
          el.value = option.value
          list.appendChild(el)
        })
      }
      input.placeholder = options.length ? 'Search bundled keys or enter custom key' : 'Enter badge key'
      input.value = getSingleBadgeOverlayPreviewSelectedKey(cfg)
    }

    const bindContentRatingPreviewInputs = (cfg) => {
      if ((!isRegionalContentRatingOverlay(cfg) && !isCommonsenseContentRatingOverlay(cfg)) || !cfg.container) return
      const templateName = cfg.container.dataset.overlayTemplate
      if (!templateName) return
      const toggleInputs = Array.from(cfg.container.querySelectorAll(`[name^="${templateName}[use_"]`))
        .filter(input => String(input?.type || '').toLowerCase() === 'checkbox')
      toggleInputs.forEach((input) => {
        if (!input || input.dataset.contentRatingPreviewBound === 'true') return
        input.dataset.contentRatingPreviewBound = 'true'
        input.addEventListener('change', () => {
          syncContentRatingPreviewControls(cfg)
          refreshContentRatingOverlayPreview(cfg)
        })
      })
      const textInput = getCommonsensePreviewTextInput(cfg)
      if (textInput && textInput.dataset.commonsensePreviewBound !== 'true') {
        textInput.dataset.commonsensePreviewBound = 'true'
        const refreshText = () => {
          syncContentRatingPreviewControls(cfg)
          refreshContentRatingOverlayPreview(cfg)
        }
        textInput.addEventListener('input', refreshText)
        textInput.addEventListener('change', refreshText)
      }
      const colorInput = cfg.container.querySelector(`[name="${templateName}[color]"]`)
      if (colorInput && colorInput.dataset.contentRatingColorPreviewBound !== 'true') {
        colorInput.dataset.contentRatingColorPreviewBound = 'true'
        colorInput.addEventListener('change', () => {
          refreshContentRatingOverlayPreview(cfg)
        })
        colorInput.addEventListener('input', () => {
          refreshContentRatingOverlayPreview(cfg)
        })
      }
    }

    const bindAudioCodecPreviewInputs = (cfg) => {
      if (cfg?.id !== 'overlay_audio_codec' || !cfg.container) return
      const templateName = cfg.container.dataset.overlayTemplate
      if (!templateName) return
      const toggleKeys = getToggleFamilyChildKeys(cfg, 'audio_codec')
      toggleKeys.forEach((toggleKey) => {
        const input = cfg.container.querySelector(`[name="${templateName}[${toggleKey}]"]`)
        if (!input || input.dataset.audioCodecPreviewBound === 'true') return
        input.dataset.audioCodecPreviewBound = 'true'
        input.addEventListener('change', () => {
          syncAudioCodecPreviewControls(cfg)
          refreshAudioCodecOverlayPreview(cfg)
        })
      })
    }

    const bindStreamingPreviewInputs = (cfg) => {
      if (cfg?.id !== 'overlay_streaming' || !cfg.container) return
      const templateName = cfg.container.dataset.overlayTemplate
      if (!templateName) return
      const toggleKeys = getToggleFamilyChildKeys(cfg, 'streaming')
      toggleKeys.forEach((toggleKey) => {
        const input = cfg.container.querySelector(`[name="${templateName}[${toggleKey}]"]`)
        if (!input || input.dataset.streamingPreviewBound === 'true') return
        input.dataset.streamingPreviewBound = 'true'
        input.addEventListener('change', () => {
          syncStreamingPreviewControls(cfg)
          refreshStreamingOverlayPreview(cfg)
        })
      })
    }

    const bindRibbonPreviewInputs = (cfg) => {
      if (cfg?.id !== 'overlay_ribbon' || !cfg.container) return
      const templateName = cfg.container.dataset.overlayTemplate
      if (!templateName) return
      const toggleKeys = getToggleFamilyChildKeys(cfg, 'ribbon')
      toggleKeys.forEach((toggleKey) => {
        const input = cfg.container.querySelector(`[name="${templateName}[${toggleKey}]"]`)
        if (!input || input.dataset.ribbonPreviewBound === 'true') return
        input.dataset.ribbonPreviewBound = 'true'
        input.addEventListener('change', () => {
          syncRibbonPreviewControls(cfg)
          refreshRibbonOverlayPreview(cfg)
        })
      })
    }

    const bindLanguageCountPreviewInputs = (cfg) => {
      if (cfg?.id !== 'overlay_language_count' || !cfg.container) return
      const templateName = cfg.container.dataset.overlayTemplate
      if (!templateName) return
      const toggleKeys = getToggleFamilyChildKeys(cfg, 'language_count')
      toggleKeys.forEach((toggleKey) => {
        const input = cfg.container.querySelector(`[name="${templateName}[${toggleKey}]"]`)
        if (!input || input.dataset.languageCountPreviewBound === 'true') return
        input.dataset.languageCountPreviewBound = 'true'
        input.addEventListener('change', () => {
          syncLanguageCountPreviewControls(cfg)
          refreshLanguageCountOverlayPreview(cfg)
        })
      })
      const subtitlesInput = cfg.container.querySelector(`[name="${templateName}[use_subtitles]"]`)
      if (subtitlesInput && subtitlesInput.dataset.languageCountVariantBound !== 'true') {
        subtitlesInput.dataset.languageCountVariantBound = 'true'
        subtitlesInput.addEventListener('change', () => {
          refreshLanguageCountOverlayPreview(cfg)
        })
      }
    }

    const bindSingleBadgeOverlayPreviewInputs = (cfg) => {
      if (!cfg?.container || !['overlay_network', 'overlay_studio'].includes(cfg.id)) return
      getBundledOverlayPreviewKeyOptions(cfg).then(() => {
        syncSingleBadgeOverlayPreviewControls(cfg)
      })
      syncSingleBadgeOverlayPreviewControls(cfg)
    }

    const refreshAudioCodecOverlayPreview = (cfg) => {
      if (cfg?.id !== 'overlay_audio_codec' || !cfg.layer) return
      buildBackdropDataUrl(cfg).then(dataUrl => {
        if (!dataUrl) return
        cfg.layer.src = dataUrl
      })
    }

    const refreshRatingsOverlayPreview = (cfg) => {
      if (cfg?.id !== 'overlay_ratings' || !cfg.layer) return
      buildBackdropDataUrl(cfg).then(dataUrl => {
        if (!dataUrl) return
        cfg.layer.src = dataUrl
        applyPosition(cfg)
      })
    }

    const refreshSingleBadgeOverlayPreview = (cfg) => {
      if (!cfg?.layer || !['overlay_network', 'overlay_studio'].includes(cfg.id)) return
      buildBackdropDataUrl(cfg).then(dataUrl => {
        if (!dataUrl) return
        cfg.layer.src = dataUrl
      })
    }

    const refreshStreamingOverlayPreview = (cfg) => {
      if (cfg?.id !== 'overlay_streaming' || !cfg.layer) return
      buildBackdropDataUrl(cfg).then(dataUrl => {
        if (!dataUrl) return
        cfg.layer.src = dataUrl
      })
    }

    const refreshRibbonOverlayPreview = (cfg) => {
      if (cfg?.id !== 'overlay_ribbon' || !cfg.layer) return
      buildRibbonCompositeDataUrl(cfg).then(dataUrl => {
        if (!dataUrl) return
        cfg.layer.src = dataUrl
      })
    }

    const refreshLanguageCountOverlayPreview = (cfg) => {
      if (cfg?.id !== 'overlay_language_count' || !cfg.layer) return
      buildBackdropDataUrl(cfg).then(dataUrl => {
        if (!dataUrl) return
        cfg.layer.src = dataUrl
      })
    }

    const refreshFixedBadgeOverlayPreview = (cfg) => {
      if (!cfg?.layer || !getFixedBadgeOverlayFamily(cfg)) return
      buildBackdropDataUrl(cfg).then(dataUrl => {
        if (!dataUrl) return
        cfg.layer.src = dataUrl
      })
    }

    const getOverlaySourceOverrideActiveConfigName = () => {
      return String(document.getElementById('qs-active-config-input')?.value || '').trim()
    }

    const isManagedOverlaySourceLocation = (value) => {
      const normalized = String(value || '').trim().replace(/\\/g, '/').toLowerCase()
      if (!normalized) return false
      return normalized.startsWith('config/') && normalized.includes('/overlay_images/')
    }

    const getTrackedManagedOverlaySourceLocation = (row) => {
      const tracked = String(row?.dataset?.overlaySourceManagedLocation || '').trim()
      return isManagedOverlaySourceLocation(tracked) ? tracked : ''
    }

    const setTrackedManagedOverlaySourceLocation = (row, value) => {
      if (!row) return
      const normalized = String(value || '').trim()
      if (isManagedOverlaySourceLocation(normalized)) {
        row.dataset.overlaySourceManagedLocation = normalized
      } else {
        delete row.dataset.overlaySourceManagedLocation
      }
    }

    const collectManagedOverlaySourceRetainLocations = (cfg, config, section) => {
      const hiddenHost = section?.querySelector('[data-overlay-source-hidden]')
      if (!hiddenHost) return []
      return readOverlaySourceOverrideState(cfg, config, hiddenHost)
        .filter(entry => entry.sourceType === 'file' && isManagedOverlaySourceLocation(entry.value))
        .map(entry => String(entry.value || '').trim())
    }

    const cleanupManagedOverlaySourceImages = async (cfg, config, section, options = {}) => {
      if (!cfg?.container || !config || !section) return null

      const configName = getOverlaySourceOverrideActiveConfigName()
      const libraryId = String(cfg.container.dataset.libraryId || '').trim()
      const overlayId = String(cfg.id || '').trim()
      if (!configName || !libraryId || !overlayId) return null

      const removeLocations = Array.isArray(options.removeLocations)
        ? options.removeLocations.map(value => String(value || '').trim()).filter(Boolean)
        : []
      const sweep = Boolean(options.sweep)
      if (!removeLocations.length && !sweep) return null

      const retainLocations = collectManagedOverlaySourceRetainLocations(cfg, config, section)
      try {
        const response = await fetch('/overlay-source-cleanup', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            config_name: configName,
            library_id: libraryId,
            overlay_id: overlayId,
            remove_locations: removeLocations,
            retain_locations: retainLocations,
            sweep
          })
        })
        const payload = await response.json().catch(() => ({}))
        if (!response.ok || payload.valid === false) {
          console.warn('[OverlaySourceOverrides] Cleanup request failed', { overlayId, payload })
          return null
        }
        return payload
      } catch (error) {
        console.warn('[OverlaySourceOverrides] Cleanup request errored', { overlayId, error })
        return null
      }
    }

    const updateOverlaySourceOverrideRowActions = (row) => {
      if (!row) return
      const sourceSelect = row.querySelector('[data-overlay-source-type="true"]')
      const makeLocalBtn = row.querySelector('[data-overlay-source-make-local="true"]')
      if (!sourceSelect || !makeLocalBtn) return

      const sourceType = String(sourceSelect.value || '').trim()
      const validationState = String(row.dataset.overlaySourceValidationState || '').trim()
      const payload = row._overlaySourceValidationPayload || null
      const isRemote = ['url', 'git', 'repo'].includes(sourceType)
      const canMakeLocal = isRemote && (validationState === 'valid' || validationState === 'warn') && Boolean(payload?.resolved_url)

      makeLocalBtn.classList.toggle('d-none', !isRemote)
      makeLocalBtn.disabled = !canMakeLocal || row.dataset.overlaySourceMakingLocal === 'true'
    }

    const setOverlaySourceOverrideRowState = (row, state, message = '') => {
      if (!row) return
      const status = row.querySelector('[data-overlay-source-status="true"]')
      const keySelect = row.querySelector('[data-overlay-source-key="true"]')
      const sourceSelect = row.querySelector('[data-overlay-source-type="true"]')
      const valueInput = row.querySelector('[data-overlay-source-value="true"]')

      row.dataset.overlaySourceValidationState = state || ''
      row.classList.remove('border-danger', 'border-warning', 'border-success')
      keySelect?.classList.remove('is-invalid')
      sourceSelect?.classList.remove('is-invalid')
      valueInput?.classList.remove('is-invalid', 'is-valid')

      if (state === 'invalid') {
        row.classList.add('border-danger')
        valueInput?.classList.add('is-invalid')
      } else if (state === 'warn') {
        row.classList.add('border-warning')
      } else if (state === 'valid') {
        row.classList.add('border-success')
        valueInput?.classList.add('is-valid')
      }

      if (!status) return
      if (message) {
        const className = state === 'invalid'
          ? 'small mt-2 text-danger'
          : state === 'warn'
            ? 'small mt-2 text-warning'
            : state === 'pending'
              ? 'small mt-2 text-muted'
              : 'small mt-2 text-success'
        status.className = className
        status.textContent = message
        status.classList.remove('d-none')
      } else {
        status.textContent = ''
        status.className = 'small mt-2 d-none'
      }

      updateOverlaySourceOverrideRowActions(row)
    }

    const collectOverlaySourceOverrideRowPayload = (cfg, row) => {
      const keySelect = row.querySelector('[data-overlay-source-key="true"]')
      const sourceSelect = row.querySelector('[data-overlay-source-type="true"]')
      const valueInput = row.querySelector('[data-overlay-source-value="true"]')
      const badgeKey = String(keySelect?.value || '').trim()
      const sourceType = String(sourceSelect?.value || '').trim()
      const sourceValue = String(valueInput?.value || '').trim()
      return {
        badgeKey,
        sourceType,
        sourceValue,
        templateKey: encodeOverlaySourceOverrideVarName(sourceType, badgeKey)
      }
    }

    const validateOverlaySourceOverrideRow = async (cfg, config, section, row) => {
      if (!cfg?.container || !row || !section) return

      const { badgeKey, sourceType, sourceValue, templateKey } = collectOverlaySourceOverrideRowPayload(cfg, row)
      const valueInput = row.querySelector('[data-overlay-source-value="true"]')
      if (!badgeKey || !sourceType || !sourceValue) {
        setOverlaySourceOverrideRowState(row, '', '')
        syncOverlaySourceOverrideRows(cfg, config, section)
        return
      }

      if (row._overlaySourceAbortController) {
        row._overlaySourceAbortController.abort()
      }
      const controller = new AbortController()
      row._overlaySourceAbortController = controller

      const previousManagedLocation = getTrackedManagedOverlaySourceLocation(row)
      row._overlaySourceValidationPayload = null
      setOverlaySourceOverrideRowState(row, 'pending', 'Validating image source...')

      try {
        const response = await fetch('/validate_overlay_source_override', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            config_name: getOverlaySourceOverrideActiveConfigName(),
            library_id: String(cfg.container.dataset.libraryId || '').trim(),
            overlay_id: String(cfg.id || '').trim(),
            template_key: templateKey,
            source_type: sourceType,
            source_value: sourceValue
          }),
          signal: controller.signal
        })

        const payload = await response.json().catch(() => ({}))
        if (!response.ok || payload.valid === false) {
          setOverlaySourceOverrideRowState(row, 'invalid', String(payload.error || 'Overlay image validation failed.').trim())
          syncOverlaySourceOverrideRows(cfg, config, section)
          return
        }

        if (sourceType === 'file' && payload.normalized_location && valueInput) {
          valueInput.value = String(payload.normalized_location).trim()
        }

        const nextManagedLocation = sourceType === 'file' && payload.normalized_location
          ? String(payload.normalized_location || '').trim()
          : ''
        setTrackedManagedOverlaySourceLocation(row, nextManagedLocation)
        row._overlaySourceValidationPayload = payload
        const message = String(payload.warning || payload.message || 'Validated overlay image source.').trim()
        const state = payload.warning ? 'warn' : 'valid'
        setOverlaySourceOverrideRowState(row, state, message)
        if (cfg.id === 'overlay_resolution' && badgeKey) {
          const family = getResolutionToggleFamilyForBadgeKey(badgeKey)
          if (family) {
            setResolutionPreviewSelectedKey(cfg, family, badgeKey)
            syncResolutionPreviewControls(cfg)
            refreshResolutionOverlayPreview(cfg)
          }
        } else if (cfg.id === 'overlay_audio_codec' && badgeKey) {
          setAudioCodecPreviewSelectedKey(cfg, badgeKey)
          syncAudioCodecPreviewControls(cfg)
          refreshAudioCodecOverlayPreview(cfg)
        } else if (cfg.id === 'overlay_streaming' && badgeKey) {
          setStreamingPreviewSelectedKey(cfg, badgeKey)
          syncStreamingPreviewControls(cfg)
          refreshStreamingOverlayPreview(cfg)
        } else if (cfg.id === 'overlay_ribbon' && badgeKey) {
          setRibbonPreviewSelectedKey(cfg, badgeKey)
          syncRibbonPreviewControls(cfg)
          refreshRibbonOverlayPreview(cfg)
        } else if (cfg.id === 'overlay_language_count' && badgeKey) {
          setLanguageCountPreviewSelectedKey(cfg, badgeKey)
          syncLanguageCountPreviewControls(cfg)
          refreshLanguageCountOverlayPreview(cfg)
        } else if (cfg.id === 'overlay_ratings') {
          refreshRatingsOverlayPreview(cfg)
        } else if (isRegionalContentRatingOverlay(cfg) && badgeKey) {
          setContentRatingPreviewSelectedKey(cfg, badgeKey)
          syncContentRatingPreviewControls(cfg)
          refreshContentRatingOverlayPreview(cfg)
        } else if (isCommonsenseContentRatingOverlay(cfg)) {
          refreshContentRatingOverlayPreview(cfg)
        } else if ((cfg.id === 'overlay_network' || cfg.id === 'overlay_studio') && badgeKey) {
          setSingleBadgeOverlayPreviewSelectedKey(cfg, badgeKey)
          syncSingleBadgeOverlayPreviewControls(cfg)
          refreshSingleBadgeOverlayPreview(cfg)
        } else if (getFixedBadgeOverlayFamily(cfg)) {
          refreshFixedBadgeOverlayPreview(cfg)
        }
        syncOverlaySourceOverrideRows(cfg, config, section)
        if (previousManagedLocation && previousManagedLocation !== nextManagedLocation) {
          await cleanupManagedOverlaySourceImages(cfg, config, section, {
            removeLocations: [previousManagedLocation],
            sweep: true
          })
        }
      } catch (error) {
        if (error?.name === 'AbortError') return
        setOverlaySourceOverrideRowState(row, 'invalid', 'Overlay image validation request failed.')
        syncOverlaySourceOverrideRows(cfg, config, section)
      } finally {
        if (row._overlaySourceAbortController === controller) {
          row._overlaySourceAbortController = null
        }
      }
    }

    const makeOverlaySourceOverrideRowLocal = async (cfg, config, section, row) => {
      if (!cfg?.container || !row || !section) return

      const { badgeKey, sourceType, sourceValue, templateKey } = collectOverlaySourceOverrideRowPayload(cfg, row)
      const sourceSelect = row.querySelector('[data-overlay-source-type="true"]')
      const valueInput = row.querySelector('[data-overlay-source-value="true"]')
      const makeLocalBtn = row.querySelector('[data-overlay-source-make-local="true"]')
      if (!sourceSelect || !valueInput || !makeLocalBtn) return
      if (!['url', 'git', 'repo'].includes(sourceType)) return

      if (row._overlaySourceAbortController) {
        row._overlaySourceAbortController.abort()
      }

      const originalText = makeLocalBtn.textContent
      row.dataset.overlaySourceMakingLocal = 'true'
      makeLocalBtn.textContent = 'Making local...'
      updateOverlaySourceOverrideRowActions(row)
      setOverlaySourceOverrideRowState(row, 'pending', 'Saving local copy of overlay image...')
      const previousManagedLocation = getTrackedManagedOverlaySourceLocation(row)

      try {
        const response = await fetch('/overlay-source-make-local', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            config_name: getOverlaySourceOverrideActiveConfigName(),
            library_id: String(cfg.container.dataset.libraryId || '').trim(),
            overlay_id: String(cfg.id || '').trim(),
            template_key: templateKey,
            badge_key: badgeKey,
            source_type: sourceType,
            source_value: sourceValue
          })
        })

        const payload = await response.json().catch(() => ({}))
        if (!response.ok || payload.valid === false) {
          row._overlaySourceValidationPayload = null
          setOverlaySourceOverrideRowState(row, 'invalid', String(payload.error || 'Failed to make overlay image local.').trim())
          syncOverlaySourceOverrideRows(cfg, config, section)
          return
        }

        sourceSelect.value = 'file'
        valueInput.value = String(payload.normalized_location || '').trim()
        const nextManagedLocation = String(payload.normalized_location || '').trim()
        setTrackedManagedOverlaySourceLocation(row, nextManagedLocation)
        row._overlaySourceValidationPayload = payload

        const message = String(payload.warning || payload.message || 'Saved overlay image into managed storage.').trim()
        const state = payload.warning ? 'warn' : 'valid'
        setOverlaySourceOverrideRowState(row, state, message)
        syncOverlaySourceOverrideRows(cfg, config, section)

        if (cfg.id === 'overlay_resolution' && badgeKey) {
          const family = getResolutionToggleFamilyForBadgeKey(badgeKey)
          if (family) {
            setResolutionPreviewSelectedKey(cfg, family, badgeKey)
            syncResolutionPreviewControls(cfg)
            refreshResolutionOverlayPreview(cfg)
          }
        } else if (cfg.id === 'overlay_audio_codec' && badgeKey) {
          setAudioCodecPreviewSelectedKey(cfg, badgeKey)
          syncAudioCodecPreviewControls(cfg)
          refreshAudioCodecOverlayPreview(cfg)
        } else if (cfg.id === 'overlay_streaming' && badgeKey) {
          setStreamingPreviewSelectedKey(cfg, badgeKey)
          syncStreamingPreviewControls(cfg)
          refreshStreamingOverlayPreview(cfg)
        } else if (cfg.id === 'overlay_ribbon' && badgeKey) {
          setRibbonPreviewSelectedKey(cfg, badgeKey)
          syncRibbonPreviewControls(cfg)
          refreshRibbonOverlayPreview(cfg)
        } else if (cfg.id === 'overlay_language_count' && badgeKey) {
          setLanguageCountPreviewSelectedKey(cfg, badgeKey)
          syncLanguageCountPreviewControls(cfg)
          refreshLanguageCountOverlayPreview(cfg)
        } else if (cfg.id === 'overlay_ratings') {
          refreshRatingsOverlayPreview(cfg)
        } else if (isRegionalContentRatingOverlay(cfg) && badgeKey) {
          setContentRatingPreviewSelectedKey(cfg, badgeKey)
          syncContentRatingPreviewControls(cfg)
          refreshContentRatingOverlayPreview(cfg)
        } else if (isCommonsenseContentRatingOverlay(cfg)) {
          refreshContentRatingOverlayPreview(cfg)
        } else if ((cfg.id === 'overlay_network' || cfg.id === 'overlay_studio') && badgeKey) {
          setSingleBadgeOverlayPreviewSelectedKey(cfg, badgeKey)
          syncSingleBadgeOverlayPreviewControls(cfg)
          refreshSingleBadgeOverlayPreview(cfg)
        } else if (getFixedBadgeOverlayFamily(cfg)) {
          refreshFixedBadgeOverlayPreview(cfg)
        }
        if (previousManagedLocation && previousManagedLocation !== nextManagedLocation) {
          await cleanupManagedOverlaySourceImages(cfg, config, section, {
            removeLocations: [previousManagedLocation],
            sweep: true
          })
        }
      } catch {
        row._overlaySourceValidationPayload = null
        setOverlaySourceOverrideRowState(row, 'invalid', 'Failed to save overlay image locally.')
        syncOverlaySourceOverrideRows(cfg, config, section)
      } finally {
        delete row.dataset.overlaySourceMakingLocal
        makeLocalBtn.textContent = originalText
        updateOverlaySourceOverrideRowActions(row)
      }
    }

    const buildOverlaySourceOverrideRow = (cfg, config, keyOptions, entry = {}) => {
      const row = document.createElement('div')
      row.className = 'border rounded-3 p-2'
      row.dataset.overlaySourceRow = 'true'

      const layout = document.createElement('div')
      layout.className = 'row g-2 align-items-start'
      row.appendChild(layout)

      const keyCol = document.createElement('div')
      keyCol.className = 'col-12 col-xl-4'
      const requestedKey = String(entry.badgeKey || '').trim()
      const useBundledPreviewKeys = config.keyMode === 'bundled_preview_keys'
      const useFixedKey = config.keyMode === 'fixed_key'
      const useSelectKeys = config.keyMode === 'from_use_toggles' || config.keyMode === 'from_select_options'
      const useFreeTextKey = !useSelectKeys && !useFixedKey && !useBundledPreviewKeys
      let keySelect
      if (useFixedKey) {
        keySelect = document.createElement('input')
        keySelect.type = 'hidden'
        keySelect.value = requestedKey || config.fixedKey || ''
        const fixedKeyLabel = document.createElement('div')
        fixedKeyLabel.className = 'form-control form-control-sm bg-body-secondary-subtle'
        fixedKeyLabel.textContent = keySelect.value || 'Badge key'
        keyCol.appendChild(fixedKeyLabel)
      } else if (useBundledPreviewKeys) {
        keySelect = document.createElement('input')
        keySelect.type = 'text'
        keySelect.className = 'form-control form-control-sm'
        keySelect.placeholder = config.keyPlaceholder || 'Badge key'
        keySelect.value = requestedKey
        const dataList = document.createElement('datalist')
        dataList.id = `${cfg.instanceId}__overlay-source-key-list__${Math.random().toString(36).slice(2, 10)}`
        dataList.dataset.overlaySourceKeyList = 'true'
        keyOptions.forEach(option => {
          const el = document.createElement('option')
          el.value = option.value
          dataList.appendChild(el)
        })
        keySelect.setAttribute('list', dataList.id)
        keyCol.appendChild(keySelect)
        keyCol.appendChild(dataList)
      } else if (useFreeTextKey) {
        keySelect = document.createElement('input')
        keySelect.type = 'text'
        keySelect.className = 'form-control form-control-sm'
        keySelect.placeholder = config.keyPlaceholder || 'Badge key'
        keySelect.value = requestedKey
      } else {
        keySelect = document.createElement('select')
        keySelect.className = 'form-select form-select-sm'
        keyOptions.forEach(option => {
          const opt = document.createElement('option')
          opt.value = option.value
          opt.textContent = option.label
          keySelect.appendChild(opt)
        })
        if (requestedKey && !keyOptions.some(option => option.value === requestedKey)) {
          const opt = document.createElement('option')
          opt.value = requestedKey
          opt.textContent = requestedKey
          keySelect.appendChild(opt)
        }
        keySelect.value = requestedKey
      }
      keySelect.dataset.overlaySourceKey = 'true'
      if (!useBundledPreviewKeys) {
        keyCol.appendChild(keySelect)
      }
      layout.appendChild(keyCol)

      const sourceCol = document.createElement('div')
      sourceCol.className = 'col-12 col-md-4 col-xl-2'
      const sourceSelect = document.createElement('select')
      sourceSelect.className = 'form-select form-select-sm'
      sourceSelect.dataset.overlaySourceType = 'true'
      config.sourceTypes.forEach(sourceType => {
        const opt = document.createElement('option')
        opt.value = sourceType
        opt.textContent = sourceType
        sourceSelect.appendChild(opt)
      })
      sourceSelect.value = String(entry.sourceType || config.sourceTypes[0] || 'file').trim()
      sourceCol.appendChild(sourceSelect)
      layout.appendChild(sourceCol)

      const valueCol = document.createElement('div')
      valueCol.className = 'col-12 col-md-8 col-xl-4'
      const valueInput = document.createElement('input')
      valueInput.type = 'text'
      valueInput.className = 'form-control form-control-sm'
      valueInput.dataset.overlaySourceValue = 'true'
      valueInput.dataset.skipLibraryInputBubble = 'true'
      valueInput.value = String(entry.value || '').trim()
      if (String(entry.sourceType || '').trim() === 'file' && isManagedOverlaySourceLocation(entry.value)) {
        row.dataset.overlaySourceManagedLocation = String(entry.value || '').trim()
      }
      valueCol.appendChild(valueInput)
      layout.appendChild(valueCol)

      const actionCol = document.createElement('div')
      actionCol.className = 'col-12 col-xl-2 d-grid gap-2'
      const makeLocalBtn = document.createElement('button')
      makeLocalBtn.type = 'button'
      makeLocalBtn.className = 'btn btn-outline-info btn-sm d-none'
      makeLocalBtn.dataset.overlaySourceMakeLocal = 'true'
      makeLocalBtn.textContent = 'Make Local'
      actionCol.appendChild(makeLocalBtn)

      const removeBtn = document.createElement('button')
      removeBtn.type = 'button'
      removeBtn.className = 'btn btn-outline-danger btn-sm'
      removeBtn.dataset.overlaySourceRemove = 'true'
      removeBtn.innerHTML = '<i class="bi bi-x-lg"></i>'
      removeBtn.setAttribute('aria-label', 'Remove source override')
      actionCol.appendChild(removeBtn)
      layout.appendChild(actionCol)

      const help = document.createElement('div')
      help.className = 'small text-muted mt-2'
      help.dataset.overlaySourceHelp = 'true'
      row.appendChild(help)

      const updatePlaceholder = () => {
        const sourceType = String(sourceSelect.value || '').trim()
        const overlayFolder = String(cfg?.id || '').replace(/^overlay_/, '') || 'custom'
        if (sourceType === 'url') {
          valueInput.placeholder = 'https://example.com/badge.png'
          help.textContent = 'Use a direct URL to a badge image. Quickstart validates the image target and can rehome it into managed storage with Make Local.'
          return
        }
        if (sourceType === 'git') {
          valueInput.placeholder = `defaults/overlays/images/${overlayFolder}/custom.png`
          help.textContent = 'Use a Community-Configs git path. Quickstart validates the resolved image and can rehome it into managed storage with Make Local.'
          return
        }
        if (sourceType === 'repo') {
          valueInput.placeholder = `overlays/${overlayFolder}/custom.png`
          help.textContent = 'Use a custom_repo-backed repo path. Quickstart validates the resolved image and can rehome it into managed storage with Make Local.'
          return
        }
        valueInput.placeholder = `config/overlays/${overlayFolder}/custom.png`
        help.textContent = 'Use a local file path that Kometa can read. Quickstart validates the image and copies it into managed config storage.'
      }

      const status = document.createElement('div')
      status.className = 'small mt-2 d-none'
      status.dataset.overlaySourceStatus = 'true'
      row.appendChild(status)

      updatePlaceholder()
      sourceSelect.addEventListener('change', () => {
        updatePlaceholder()
        row._overlaySourceValidationPayload = null
        setOverlaySourceOverrideRowState(row, '', '')
      })
      updateOverlaySourceOverrideRowActions(row)
      return row
    }

    const syncOverlaySourceOverrideRows = (cfg, config, section) => {
      if (!cfg.container || !section) return
      const hiddenHost = section.querySelector('[data-overlay-source-hidden]')
      const rows = Array.from(section.querySelectorAll('[data-overlay-source-row="true"]'))
      const warning = section.querySelector('[data-overlay-source-warning]')
      if (!hiddenHost || !warning) return

      const seen = new Set()
      const seenValues = new Map()
      const nextState = []
      let warningText = ''
      let asyncInvalidCount = 0
      let asyncWarnCount = 0

      rows.forEach(row => {
        const keySelect = row.querySelector('[data-overlay-source-key="true"]')
        const sourceSelect = row.querySelector('[data-overlay-source-type="true"]')
        const valueInput = row.querySelector('[data-overlay-source-value="true"]')
        if (!keySelect || !sourceSelect || !valueInput) return

        keySelect.classList.remove('is-invalid')
        sourceSelect.classList.remove('is-invalid')
        valueInput.classList.remove('is-invalid')

        const badgeKey = String(keySelect.value || '').trim()
        const sourceType = String(sourceSelect.value || '').trim()
        const value = String(valueInput.value || '').trim()
        if (!value) return

        if (!badgeKey) {
          if (!warningText) {
            warningText = 'Each source override needs a specific badge key.'
          }
          keySelect.classList.add('is-invalid')
          return
        }

        if (!sourceType) {
          if (!warningText) {
            warningText = 'Each source override needs a source type and a value.'
          }
          sourceSelect.classList.toggle('is-invalid', !sourceType)
          return
        }

        const combo = `${sourceType}:${badgeKey}`
        if (seen.has(combo)) {
          if (!warningText) {
            warningText = 'Duplicate source overrides for the same badge and source type are ignored.'
          }
          keySelect.classList.add('is-invalid')
          sourceSelect.classList.add('is-invalid')
          return
        }

        const normalizedValueKey = `${sourceType}:${value.toLowerCase()}`
        const priorBadge = seenValues.get(normalizedValueKey)
        if (priorBadge && priorBadge !== badgeKey) {
          if (!warningText) {
            warningText = 'Different badges cannot reuse the same source override value.'
          }
          keySelect.classList.add('is-invalid')
          valueInput.classList.add('is-invalid')
          return
        }

        seen.add(combo)
        seenValues.set(normalizedValueKey, badgeKey)
        nextState.push({ badgeKey, sourceType, value })

        const rowState = String(row.dataset.overlaySourceValidationState || '').trim()
        if (rowState === 'invalid') {
          asyncInvalidCount += 1
        } else if (rowState === 'warn') {
          asyncWarnCount += 1
        }
      })

      const serializedState = JSON.stringify(nextState)
      const didStateChange = hiddenHost.dataset.overlaySourceSerialized !== serializedState
      if (didStateChange) {
        hiddenHost.replaceChildren()
        nextState.forEach(entry => {
          const varName = encodeOverlaySourceOverrideVarName(entry.sourceType, entry.badgeKey)
          createOverlaySourceOverrideHiddenInput(cfg, hiddenHost, varName, entry.value)
        })
        hiddenHost.dataset.overlaySourceSerialized = serializedState
      }

      if (!warningText && asyncInvalidCount > 0) {
        warningText = asyncInvalidCount === 1
          ? 'One source override failed validation.'
          : `${asyncInvalidCount} source overrides failed validation.`
      } else if (!warningText && asyncWarnCount > 0) {
        warningText = asyncWarnCount === 1
          ? 'One source override is valid but stays external to Quickstart bundles.'
          : `${asyncWarnCount} source overrides are valid but stay external to Quickstart bundles.`
      }

      warning.textContent = warningText
      warning.classList.toggle('d-none', !warningText)

      const emptyState = section.querySelector('[data-overlay-source-empty]')
      if (emptyState) {
        emptyState.classList.toggle('d-none', rows.length > 0)
      }

      if (typeof EventHandler !== 'undefined' && typeof EventHandler.updateAccordionHighlights === 'function') {
        EventHandler.updateAccordionHighlights()
      }
      if (typeof ValidationHandler !== 'undefined' && typeof ValidationHandler.updateValidationState === 'function') {
        ValidationHandler.updateValidationState()
      }
      if (cfg.id === 'overlay_resolution') {
        syncResolutionPreviewControls(cfg)
        if (didStateChange) {
          refreshResolutionOverlayPreview(cfg)
        }
      }
      if (cfg.id === 'overlay_audio_codec') {
        syncAudioCodecPreviewControls(cfg)
        if (didStateChange) {
          refreshAudioCodecOverlayPreview(cfg)
        }
      }
      if (cfg.id === 'overlay_streaming') {
        syncStreamingPreviewControls(cfg)
        if (didStateChange) {
          refreshStreamingOverlayPreview(cfg)
        }
      }
      if (cfg.id === 'overlay_ribbon') {
        syncRibbonPreviewControls(cfg)
        if (didStateChange) {
          refreshRibbonOverlayPreview(cfg)
        }
      }
      if (cfg.id === 'overlay_language_count') {
        syncLanguageCountPreviewControls(cfg)
        if (didStateChange) {
          refreshLanguageCountOverlayPreview(cfg)
        }
      }
      if (cfg.id === 'overlay_ratings' && didStateChange) {
        refreshRatingsOverlayPreview(cfg)
      }
      if (isRegionalContentRatingOverlay(cfg)) {
        syncContentRatingPreviewControls(cfg)
        if (didStateChange) {
          refreshContentRatingOverlayPreview(cfg)
        }
      }
      if (isCommonsenseContentRatingOverlay(cfg) && didStateChange) {
        refreshContentRatingOverlayPreview(cfg)
      }
      if (cfg.id === 'overlay_network' || cfg.id === 'overlay_studio') {
        syncSingleBadgeOverlayPreviewControls(cfg)
        if (didStateChange) {
          refreshSingleBadgeOverlayPreview(cfg)
        }
      }
      if (getFixedBadgeOverlayFamily(cfg) && didStateChange) {
        refreshFixedBadgeOverlayPreview(cfg)
      }
    }

    const renderOverlaySourceOverrideRows = (cfg, config, section, state) => {
      const rowsHost = section.querySelector('[data-overlay-source-rows]')
      const hiddenHost = section.querySelector('[data-overlay-source-hidden]')
      const emptyState = section.querySelector('[data-overlay-source-empty]')
      if (!rowsHost || !hiddenHost) return

      const keyOptions = getOverlaySourceOverrideKeyOptions(cfg, config)
      rowsHost.innerHTML = ''
      const entries = Array.isArray(state) && state.length ? state : []
      entries.forEach(entry => {
        const row = buildOverlaySourceOverrideRow(cfg, config, keyOptions, entry)
        rowsHost.appendChild(row)
      })

      if (emptyState) {
        emptyState.classList.toggle('d-none', rowsHost.children.length > 0)
      }

      rowsHost.querySelectorAll('[data-overlay-source-remove="true"]').forEach(btn => {
        btn.addEventListener('click', () => {
          const row = btn.closest('[data-overlay-source-row="true"]')
          const previousManagedLocation = getTrackedManagedOverlaySourceLocation(row)
          if (row?._overlaySourceAbortController) {
            row._overlaySourceAbortController.abort()
          }
          btn.closest('[data-overlay-source-row="true"]')?.remove()
          syncOverlaySourceOverrideRows(cfg, config, section)
          cleanupManagedOverlaySourceImages(cfg, config, section, {
            removeLocations: previousManagedLocation ? [previousManagedLocation] : [],
            sweep: true
          }).catch(() => {})
        })
      })

      rowsHost.querySelectorAll('[data-overlay-source-make-local="true"]').forEach(btn => {
        btn.addEventListener('click', () => {
          const row = btn.closest('[data-overlay-source-row="true"]')
          makeOverlaySourceOverrideRowLocal(cfg, config, section, row)
        })
      })

      rowsHost.querySelectorAll('[data-overlay-source-key="true"], [data-overlay-source-type="true"]').forEach(input => {
        input.addEventListener('change', () => {
          const row = input.closest('[data-overlay-source-row="true"]')
          row._overlaySourceValidationPayload = null
          setOverlaySourceOverrideRowState(row, '', '')
          syncOverlaySourceOverrideRows(cfg, config, section)
          validateOverlaySourceOverrideRow(cfg, config, section, row)
        })
      })

      rowsHost.querySelectorAll('[data-overlay-source-value="true"]').forEach(input => {
        input.addEventListener('input', () => {
          const row = input.closest('[data-overlay-source-row="true"]')
          row._overlaySourceValidationPayload = null
          setOverlaySourceOverrideRowState(row, '', '')
        })
        input.addEventListener('change', () => {
          const row = input.closest('[data-overlay-source-row="true"]')
          syncOverlaySourceOverrideRows(cfg, config, section)
          validateOverlaySourceOverrideRow(cfg, config, section, row)
        })
        input.addEventListener('blur', () => {
          const row = input.closest('[data-overlay-source-row="true"]')
          validateOverlaySourceOverrideRow(cfg, config, section, row)
        })
      })
    }

    const ensureOverlaySourceOverrideEditor = (cfg) => {
      if (!cfg.container) return
      const config = getOverlaySourceOverrideConfig(cfg)
      if (!config) return

      const details = cfg.container.querySelector('.overlay-template-section')
      if (!details) return

      let section = cfg.container.querySelector('[data-overlay-source-editor="true"]')
      if (!section) {
        section = document.createElement('section')
        section.className = 'border rounded-3 px-3 pt-3 pb-2 mb-3 bg-body-tertiary'
        section.dataset.overlaySourceEditor = 'true'
        section.innerHTML = `
          <div class="d-flex align-items-start justify-content-between gap-2 flex-wrap mb-2">
            <div>
              <div class="small text-uppercase fw-semibold text-secondary">${config.title}</div>
              <div class="form-text">${config.description}</div>
            </div>
            <button type="button" class="btn btn-outline-secondary btn-sm" data-overlay-source-add="true">${config.addLabel}</button>
          </div>
          <div class="alert alert-warning py-2 px-3 small d-none mb-2" data-overlay-source-warning></div>
          <div class="d-flex flex-column gap-2" data-overlay-source-rows></div>
          <div class="small text-muted fst-italic" data-overlay-source-empty>No source overrides configured.</div>
          <div data-overlay-source-hidden class="d-none"></div>
        `
        details.prepend(section)
      }

      const hiddenHost = section.querySelector('[data-overlay-source-hidden]')
      if (!hiddenHost) return

      const state = readOverlaySourceOverrideState(cfg, config, hiddenHost)
      renderOverlaySourceOverrideRows(cfg, config, section, state)
      syncOverlaySourceOverrideRows(cfg, config, section)

      if (config.keyMode === 'bundled_preview_keys' && section.dataset.overlaySourceKeyOptionsLoaded !== 'true') {
        section.dataset.overlaySourceKeyOptionsLoaded = 'loading'
        getBundledOverlayPreviewKeyOptions(cfg).then(() => {
          section.dataset.overlaySourceKeyOptionsLoaded = 'true'
          const nextState = readOverlaySourceOverrideState(cfg, config, hiddenHost)
          renderOverlaySourceOverrideRows(cfg, config, section, nextState)
          syncOverlaySourceOverrideRows(cfg, config, section)
          syncSingleBadgeOverlayPreviewControls(cfg)
        })
      }

      const addBtn = section.querySelector('[data-overlay-source-add="true"]')
      if (addBtn && addBtn.dataset.listenerAdded !== 'true') {
        addBtn.dataset.listenerAdded = 'true'
        addBtn.addEventListener('click', () => {
          const rowsHost = section.querySelector('[data-overlay-source-rows]')
          if (!rowsHost) return
          const keyOptions = getOverlaySourceOverrideKeyOptions(cfg, config)
          const fallbackBadgeKey = config.keyMode === 'fixed_key'
            ? String(config.fixedKey || '').trim()
            : keyOptions[0]?.value || getSingleBadgeOverlayPreviewSelectedKey(cfg) || ''
          rowsHost.appendChild(buildOverlaySourceOverrideRow(cfg, config, keyOptions, {
            sourceType: config.sourceTypes[0] || 'file',
            badgeKey: fallbackBadgeKey,
            value: ''
          }))
          renderOverlaySourceOverrideRows(cfg, config, section, Array.from(rowsHost.querySelectorAll('[data-overlay-source-row="true"]')).map(row => ({
            badgeKey: String(row.querySelector('[data-overlay-source-key="true"]')?.value || '').trim(),
            sourceType: String(row.querySelector('[data-overlay-source-type="true"]')?.value || '').trim(),
            value: String(row.querySelector('[data-overlay-source-value="true"]')?.value || '').trim()
          })))
          syncOverlaySourceOverrideRows(cfg, config, section)
        })
      }

      const resetBtn = cfg.container.querySelector('.reset-offset-btn')
      if (resetBtn && resetBtn.dataset.sourceOverrideResetBound !== 'true') {
        resetBtn.dataset.sourceOverrideResetBound = 'true'
        resetBtn.addEventListener('click', () => {
          const previousManagedLocations = Array.from(section.querySelectorAll('[data-overlay-source-row="true"]'))
            .map(row => getTrackedManagedOverlaySourceLocation(row))
            .filter(Boolean)
          setTimeout(() => {
            const nextState = readOverlaySourceOverrideState(cfg, config, hiddenHost)
            renderOverlaySourceOverrideRows(cfg, config, section, nextState)
            syncOverlaySourceOverrideRows(cfg, config, section)
            cleanupManagedOverlaySourceImages(cfg, config, section, {
              removeLocations: previousManagedLocations,
              sweep: true
            }).catch(() => {})
          }, 0)
        })
      }
    }

    const syncFlagSizeDefaults = (cfg, emit = true) => {
      if (!isFlagsOverlay(cfg)) return
      const sizeInput = getTemplateInput(cfg, 'size')
      const size = (sizeInput?.value || 'small').toLowerCase()
      const fontSize = size === 'big' ? 70 : 50
      const backWidth = size === 'big' ? 216 : 190
      setTemplateNumber(cfg, 'font_size', fontSize, emit)
      setTemplateNumber(cfg, 'back_width', backWidth, emit)
      setTemplateNumber(cfg, 'back_height', 60, emit)
    }

    const RATINGS_IMAGE_BASE = 'https://raw.githubusercontent.com/Kometa-Team/Kometa/refs/heads/nightly/defaults/overlays/images/rating/'
    const RATING_LABEL_MAP = {
      anidb: 'AniDB',
      imdb: 'IMDb',
      letterboxd: 'Letterboxd',
      tmdb: 'TMDb',
      metacritic: 'Metacritic',
      rt_popcorn: 'RT-Aud-Fresh',
      rt_tomato: 'RT-Crit-Fresh',
      trakt: 'Trakt',
      mal: 'MAL',
      mdb: 'MDBList',
      star: 'Star'
    }
    const RATING_TEXT_MAP = {
      critic: '9.0',
      audience: '85%',
      user: '85%'
    }
    const RATING_SAMPLE_BASE = {
      critic: { decimal10: 9.0, decimal5: 4.5, percent: 90, score100: 90 },
      audience: { decimal10: 8.5, decimal5: 4.3, percent: 85, score100: 85 },
      user: { decimal10: 7.5, decimal5: 3.3, percent: 75, score100: 75 }
    }
    const RATING_SAMPLE_JITTER = {
      decimal10: 1.2,
      decimal5: 0.6,
      percent: 12,
      score100: 12
    }
    const RATING_SAMPLE_LIMITS = {
      decimal10: { min: 1.0, max: 9.8 },
      decimal5: { min: 0.5, max: 4.5 },
      percent: { min: 10, max: 95 },
      score100: { min: 10, max: 95 }
    }
    const RATING_SAMPLE_OVERRIDES = {
      rt_tomato: { min: 10, max: 95, scale: 'percent' },
      rt_popcorn: { min: 10, max: 95, scale: 'percent' }
    }
    const RATING_VALUE_FORMAT_MAP = {
      anidb: { scale: 'decimal10', decimals: 1 },
      imdb: { scale: 'decimal10', decimals: 1 },
      letterboxd: { scale: 'decimal5', decimals: 1 },
      tmdb: { scale: 'decimal10', decimals: 1 },
      metacritic: { scale: 'score100', decimals: 0 },
      rt_popcorn: { scale: 'percent', decimals: 0 },
      rt_tomato: { scale: 'percent', decimals: 0 },
      trakt: { scale: 'percent', decimals: 0 },
      mal: { scale: 'decimal10', decimals: 2 },
      mdb: { scale: 'score100', decimals: 0 },
      mdblist: { scale: 'score100', decimals: 0 },
      star: { scale: 'decimal10', decimals: 1 },
      plex_star: { scale: 'decimal10', decimals: 1 }
    }
    const RATING_FILENAME_MAP = {
      rt_popcorn: 'RT-Aud-Fresh',
      rt_tomato: 'RT-Crit-Fresh',
      mdb: 'MDBList',
      mal: 'MAL',
      'rt popcorn': 'RT-Aud-Fresh',
      'rt tomato': 'RT-Crit-Fresh',
      'rt tomatoes': 'RT-Crit-Fresh',
      myanimelist: 'MAL'
    }
    const RT_ROTTEN_THRESHOLD = 60
    const RATING_RT_IMAGE_MAP = {
      rt_tomato: { fresh: 'RT-Crit-Fresh.png', rotten: 'RT-Crit-Rotten.png' },
      rt_popcorn: { fresh: 'RT-Aud-Fresh.png', rotten: 'RT-Aud-Rotten.png' }
    }
    const RATING_FONT_MAP = {
      anidb: 'Arimo-Medium.ttf',
      imdb: 'Roboto-Medium.ttf',
      tmdb: 'Consensus-SemiBold.otf',
      metacritic: 'Montserrat-SemiBold.ttf',
      letterboxd: 'Montserrat-Bold.ttf',
      trakt: 'Figtree-Medium.ttf',
      rt_tomato: 'LibreFranklin-Bold.ttf',
      rt_popcorn: 'LibreFranklin-Bold.ttf',
      'rt tomato': 'LibreFranklin-Bold.ttf',
      'rt popcorn': 'LibreFranklin-Bold.ttf',
      myanimelist: 'Lato-Regular.ttf',
      mal: 'Lato-Regular.ttf',
      mdblist: 'Lato-Regular.ttf',
      mdb: 'Lato-Regular.ttf',
      star: 'Roboto-Medium.ttf',
      plex_star: 'Roboto-Medium.ttf'
    }
    const RATING_MASS_GROUP_MAP = {
      critic: 'mass_critic_rating_update',
      audience: 'mass_audience_rating_update',
      user: 'mass_user_rating_update'
    }
    const RATING_MASS_GROUP_MAP_EPISODE = {
      critic: 'mass_episode_critic_rating_update',
      audience: 'mass_episode_audience_rating_update',
      user: 'mass_episode_user_rating_update'
    }
    const RATING_GROUP_LABEL_MAP = {
      mass_critic_rating_update: 'Mass Critic Rating Update',
      mass_audience_rating_update: 'Mass Audience Rating Update',
      mass_user_rating_update: 'Mass User Rating Update',
      mass_episode_critic_rating_update: 'Mass Episode Critic Rating Update',
      mass_episode_audience_rating_update: 'Mass Episode Audience Rating Update',
      mass_episode_user_rating_update: 'Mass Episode User Rating Update'
    }
    const RATING_SOURCE_MAP = {
      anidb: { any: 'anidb_rating' },
      imdb: { any: 'imdb' },
      letterboxd: { any: 'mdb_letterboxd' },
      tmdb: { any: 'tmdb' },
      metacritic: { critic: 'mdb_metacritic', audience: 'mdb_metacriticuser', user: 'mdb_metacriticuser' },
      rt_tomato: { critic: 'mdb_tomatoes', audience: 'mdb_tomatoesaudience', user: 'mdb_tomatoes' },
      rt_popcorn: { any: 'mdb_tomatoesaudience' },
      trakt: { critic: 'trakt', audience: 'trakt', user: 'trakt_user' },
      mal: { any: 'mal' },
      mdb: { any: 'mdb' }
    }
    const RATING_SOURCE_MAP_EPISODE = {
      imdb: { any: 'imdb' },
      tmdb: { any: 'tmdb' },
      trakt: { critic: 'trakt', audience: 'trakt', user: 'trakt_user' }
    }
    const RATING_SOURCE_LABEL_MAP = {
      anidb_rating: 'Use AniDB Rating',
      imdb: 'Use IMDb Rating',
      mdb_letterboxd: 'Use Letterboxd via MDBList',
      tmdb: 'Use TMDb Rating',
      mdb_metacritic: 'Use Metacritic via MDBList',
      mdb_metacriticuser: 'Use Metacritic via MDBList',
      mdb_tomatoes: 'Use Rotten Tomatoes via MDBList',
      mdb_tomatoesaudience: 'Use RT Audience via MDBList',
      trakt: 'Use Trakt Rating',
      trakt_user: 'Use Trakt Rating',
      mal: 'Use MyAnimeList Score',
      mdb: 'Use MDBList Score'
    }
    const RATING_SOURCE_SERVICE_MAP = {
      anidb_rating: 'anidb',
      mdb_letterboxd: 'mdblist',
      tmdb: 'tmdb',
      mdb_metacritic: 'mdblist',
      mdb_metacriticuser: 'mdblist',
      mdb_tomatoes: 'mdblist',
      mdb_tomatoesaudience: 'mdblist',
      trakt: 'trakt',
      trakt_user: 'trakt',
      mal: 'mal',
      mdb: 'mdblist'
    }
    const SERVICE_VALIDATION_INPUTS = {
      tmdb: 'qs-validate-tmdb',
      mdblist: 'qs-validate-mdblist',
      trakt: 'qs-validate-trakt',
      mal: 'qs-validate-mal',
      myanimelist: 'qs-validate-mal',
      anidb: 'qs-validate-anidb',
      omdb: 'qs-validate-omdb',
      plex: 'qs-validate-plex'
    }
    const SERVICE_LABEL_MAP = {
      tmdb: 'TMDb',
      mdblist: 'MDBList',
      trakt: 'Trakt',
      mal: 'MyAnimeList',
      myanimelist: 'MyAnimeList',
      anidb: 'AniDB',
      omdb: 'OMDb',
      plex: 'Plex'
    }
    const buildRatingFilenameCandidates = (value, label) => {
      const valueKey = (value || '').toString().trim().toLowerCase()
      const labelKey = (label || '').toString().trim().toLowerCase()
      const mapped = RATING_FILENAME_MAP[valueKey] || RATING_FILENAME_MAP[labelKey]
      if (mapped) {
        return [`${RATINGS_IMAGE_BASE}${encodeURIComponent(`${mapped}.png`)}`]
      }
      const raw = (label || RATING_LABEL_MAP[value] || value || '').trim()
      if (!raw) return []
      const normalized = raw.replace(/\s+/g, ' ').trim()
      const noSpaces = normalized.replace(/\s+/g, '')
      const underscored = normalized.replace(/\s+/g, '_')
      const dashed = normalized.replace(/\s+/g, '-')
      const names = []
      ;[normalized, noSpaces, underscored, dashed].forEach(name => {
        if (!name || names.includes(name)) return
        names.push(name)
      })
      return names.map(name => `${RATINGS_IMAGE_BASE}${encodeURIComponent(`${name}.png`)}`)
    }

    const enhanceRatingImageSelects = (ratingScope) => {
      const ratingRoot = ratingScope || document
      ratingRoot.querySelectorAll('select[data-rating-image-select="true"]').forEach(select => {
        if (select.dataset.ratingImageEnhanced) return
        select.dataset.ratingImageEnhanced = 'true'

        const wrapper = document.createElement('div')
        wrapper.className = 'dropdown rating-image-dropdown'

        const toggle = document.createElement('button')
        toggle.type = 'button'
        toggle.className = 'form-select rating-image-dropdown-toggle d-flex align-items-center justify-content-between'
        toggle.setAttribute('data-bs-toggle', 'dropdown')
        toggle.setAttribute('data-bs-auto-close', 'true')
        toggle.setAttribute('aria-expanded', 'false')

        const labelWrap = document.createElement('span')
        labelWrap.className = 'rating-image-dropdown-label d-flex align-items-center gap-2'

        const icon = document.createElement('img')
        icon.className = 'rating-image-dropdown-icon'

        const text = document.createElement('span')
        text.className = 'rating-image-dropdown-text'

        labelWrap.append(icon, text)

        const caret = document.createElement('span')
        caret.className = 'rating-image-dropdown-caret'
        const caretIcon = document.createElement('i')
        caretIcon.className = 'bi bi-chevron-down'
        caret.appendChild(caretIcon)

        toggle.append(labelWrap, caret)

        const menu = document.createElement('div')
        menu.className = 'dropdown-menu rating-image-dropdown-menu'

        const updateDisplay = () => {
          const selected = select.selectedOptions?.[0]
          const value = (selected?.value || '').toString()
          const label = (selected?.textContent || '').trim() || value || 'None'
          const iconUrl = value ? (buildRatingFilenameCandidates(value, label)[0] || '') : ''
          if (iconUrl) {
            icon.src = iconUrl
            icon.alt = label
            icon.classList.remove('is-empty')
          } else {
            icon.removeAttribute('src')
            icon.removeAttribute('alt')
            icon.classList.add('is-empty')
          }
          text.textContent = label

          menu.querySelectorAll('.rating-image-dropdown-item').forEach(item => {
            item.classList.toggle('active', item.dataset.value === value)
          })
        }

        const orderedOptions = (() => {
          const options = Array.from(select.options).map(option => ({
            option,
            value: (option.value || '').toString(),
            label: (option.textContent || '').trim() || option.value || ''
          }))
          const empty = options.filter(item => !item.value)
          const rest = options.filter(item => item.value)
          rest.sort((a, b) => a.label.localeCompare(b.label, undefined, { sensitivity: 'base', numeric: true }))
          return [...empty, ...rest]
        })()

        orderedOptions.forEach(entry => {
          const option = entry.option
          const optionButton = document.createElement('button')
          optionButton.type = 'button'
          optionButton.className = 'dropdown-item d-flex align-items-center gap-2 rating-image-dropdown-item'
          optionButton.dataset.value = (option.value || '').toString()
          if (option.disabled) optionButton.disabled = true

          const itemIcon = document.createElement('img')
          itemIcon.className = 'rating-image-dropdown-icon'
          const label = (option.textContent || '').trim() || option.value
          const iconUrl = option.value ? (buildRatingFilenameCandidates(option.value, label)[0] || '') : ''
          if (iconUrl) {
            itemIcon.src = iconUrl
            itemIcon.alt = label
          } else {
            itemIcon.classList.add('is-empty')
          }

          const itemText = document.createElement('span')
          itemText.textContent = label || 'None'

          optionButton.append(itemIcon, itemText)
          optionButton.addEventListener('click', () => {
            select.value = option.value
            updateDisplay()
            select.dispatchEvent(new Event('change', { bubbles: true }))
          })

          menu.appendChild(optionButton)
        })

        wrapper.append(toggle, menu)

        select.classList.add('rating-image-select-native')
        select.classList.add('visually-hidden')
        select.insertAdjacentElement('afterend', wrapper)

        select.addEventListener('change', updateDisplay)
        updateDisplay()
      })
    }

    enhanceRatingImageSelects(root)

    const loadImageWithFallback = async (urls) => {
      let lastErr = null
      for (const url of urls) {
        try {
          return await loadImage(url)
        } catch (err) {
          lastErr = err
        }
      }
      throw lastErr || new Error('No rating image URL matched')
    }

    const normalizeRatingImageKey = (value, label) => {
      const raw = (value || label || '').toString().trim().toLowerCase()
      if (!raw) return ''
      const normalized = raw.replace(/\s+/g, ' ').trim()
      const mapped = {
        'rt tomato': 'rt_tomato',
        'rt tomatoes': 'rt_tomato',
        'rt popcorn': 'rt_popcorn',
        myanimelist: 'mal',
        mdb: 'mdb'
      }[normalized]
      if (mapped) return mapped
      return normalized.replace(/\s+/g, '_')
    }

    const hashString = (value) => {
      let hash = 2166136261
      const str = String(value || '')
      for (let i = 0; i < str.length; i += 1) {
        hash ^= str.charCodeAt(i)
        hash = Math.imul(hash, 16777619)
      }
      return hash >>> 0
    }

    const seededRandom = (seed) => {
      let t = (seed + 0x6D2B79F5) >>> 0
      t = Math.imul(t ^ (t >>> 15), t | 1)
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296
    }

    const clampNumber = (value, min, max) => Math.min(Math.max(value, min), max)

    const getRatingSampleValue = (ratingType, imageValue, imageLabel, variant = null) => {
      const typeKey = String(ratingType || '').toLowerCase()
      const imageKey = normalizeRatingImageKey(imageValue, imageLabel)
      const format = RATING_VALUE_FORMAT_MAP[imageKey]
      const baseMap = RATING_SAMPLE_BASE[typeKey]
      if (!format || !baseMap) {
        return {
          typeKey,
          imageKey,
          value: null,
          scaleKey: null,
          decimals: null,
          text: RATING_TEXT_MAP[typeKey] || 'NR'
        }
      }
      const scale = format.scale || 'decimal10'
      const baseValue = baseMap[scale]
      if (!Number.isFinite(baseValue)) {
        return {
          typeKey,
          imageKey,
          value: null,
          scaleKey: scale,
          decimals: format.decimals,
          text: RATING_TEXT_MAP[typeKey] || 'NR'
        }
      }
      const overrides = RATING_SAMPLE_OVERRIDES[imageKey]
      const scaleKey = (overrides && overrides.scale) ? overrides.scale : scale
      const limits = overrides || RATING_SAMPLE_LIMITS[scaleKey]
      const seed = hashString(`${imageKey}|${typeKey}|${variant || 'base'}`)
      const rand = seededRandom(seed)
      const jitter = Number.isFinite(RATING_SAMPLE_JITTER[scaleKey]) ? RATING_SAMPLE_JITTER[scaleKey] : 0
      const offset = (rand - 0.5) * 2 * jitter
      let value = Number(baseValue) + offset
      if (limits) {
        let min = limits.min
        let max = limits.max
        if ((imageKey === 'rt_tomato' || imageKey === 'rt_popcorn') && scaleKey === 'percent') {
          if (variant === 'fresh') {
            min = Math.max(RT_ROTTEN_THRESHOLD, min)
          } else if (variant === 'rotten') {
            max = Math.min(RT_ROTTEN_THRESHOLD - 1, max)
          }
        }
        value = clampNumber(value, min, max)
      } else if (scaleKey === 'decimal10') {
        value = clampNumber(value, 0.1, 9.9)
      } else if (scaleKey === 'decimal5') {
        value = clampNumber(value, 0.1, 4.9)
      } else {
        value = clampNumber(value, 1, 99)
      }
      let text = ''
      if (scaleKey === 'percent') {
        text = `${Math.round(value)}%`
      } else if (format.decimals === 0) {
        text = `${Math.round(value)}`
      } else {
        text = Number(value).toFixed(Math.max(0, Number(format.decimals)))
      }
      return {
        typeKey,
        imageKey,
        value,
        scaleKey,
        decimals: format.decimals,
        text
      }
    }

    const getRatingSampleImageUrls = (imageVal, labelVal, sample) => {
      const imageKey = normalizeRatingImageKey(imageVal, labelVal)
      const map = RATING_RT_IMAGE_MAP[imageKey]
      if (map && sample && sample.scaleKey === 'percent' && Number.isFinite(sample.value)) {
        const filename = sample.value >= RT_ROTTEN_THRESHOLD ? map.fresh : map.rotten
        return [`${RATINGS_IMAGE_BASE}${encodeURIComponent(filename)}`]
      }
      return buildRatingFilenameCandidates(imageVal, labelVal)
    }

    const getRatingToggleLabel = (imageKey, source, fallbackLabel) => {
      if (!source) return fallbackLabel
      if (imageKey === 'rt_popcorn') {
        return 'Use RT Audience via MDBList'
      }
      if (imageKey === 'rt_tomato') {
        return 'Use Rotten Tomatoes via MDBList'
      }
      if (source === 'mdb_metacritic' || source === 'mdb_metacriticuser') {
        return 'Use Metacritic via MDBList'
      }
      if (source === 'trakt' || source === 'trakt_user') {
        return 'Use Trakt Rating'
      }
      return fallbackLabel
    }

    const getServiceValidation = (service) => {
      if (!service) return null
      const readBool = (el) => {
        if (!el) return null
        const raw = String(el.value || el.dataset?.plexValid || el.dataset?.validated || '').toLowerCase()
        if (!raw) return null
        return raw === 'true'
      }
      const inputId = SERVICE_VALIDATION_INPUTS[service]
      if (inputId) {
        const input = document.getElementById(inputId)
        const value = readBool(input)
        if (value !== null) return value
      }
      const fallbackIds = {
        plex: ['plex_validated', 'plex_valid'],
        omdb: ['omdb_validated']
      }[service] || []
      for (const id of fallbackIds) {
        const value = readBool(document.getElementById(id))
        if (value !== null) return value
      }
      return null
    }

    const getMassToggleLabel = (libraryId, group, source) => {
      if (!libraryId || !group || !source) return null
      const inputId = `${libraryId}-attribute_${group}_${source}`
      const label = document.querySelector(`label[for="${inputId}"]`)
      if (!label) return null
      return (label.textContent || '').trim()
    }

    const getCurrentMassToggleValue = (libraryId, group) => {
      if (!libraryId || !group) return null
      const inputPrefix = `${libraryId}-attribute_${group}_`
      const toggles = Array.from(document.querySelectorAll(`input.form-check-input[id^="${inputPrefix}"]`))
      const checked = toggles.find(input => input.checked)
      return checked ? checked.id.replace(inputPrefix, '') : null
    }

    const setStatusTooltip = (el, message) => {
      if (!el) return
      el.setAttribute('title', message)
      el.setAttribute('data-bs-original-title', message)
      const Tooltip = window.bootstrap?.Tooltip
      if (!Tooltip) return
      const tooltip = Tooltip.getOrCreateInstance
        ? Tooltip.getOrCreateInstance(el)
        : new Tooltip(el)
      if (tooltip && typeof tooltip.setContent === 'function') {
        tooltip.setContent({ '.tooltip-inner': message })
      }
    }

    const setStatusIcon = (el, status, message) => {
      if (!el) return
      const icon = el.querySelector('i') || el
      icon.classList.remove('bi-check-circle-fill', 'bi-exclamation-circle-fill', 'bi-dash-circle-fill')
      el.classList.remove('text-success', 'text-danger', 'text-secondary')
      if (status === 'ok') {
        icon.classList.add('bi-check-circle-fill')
        el.classList.add('text-success')
      } else if (status === 'warn') {
        icon.classList.add('bi-exclamation-circle-fill')
        el.classList.add('text-danger')
      } else {
        icon.classList.add('bi-dash-circle-fill')
        el.classList.add('text-secondary')
      }
      if (message) {
        setStatusTooltip(el, message)
      }
    }

    const escapeHtml = (value) => {
      const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
      }
      return String(value ?? '').replace(/[&<>"']/g, (match) => map[match])
    }

    const getCurrentMassToggleLabel = (libraryId, group) => {
      if (!libraryId || !group) return null
      const inputPrefix = `${libraryId}-attribute_${group}_`
      const toggles = Array.from(document.querySelectorAll(`input.form-check-input[id^="${inputPrefix}"]`))
      const checked = toggles.filter(input => input.checked)
      if (!checked.length) return null
      const labels = checked
        .map(input => {
          const label = document.querySelector(`label[for="${input.id}"]`)
          return label ? label.textContent.trim() : input.id.replace(inputPrefix, '')
        })
        .filter(Boolean)
      return labels.length ? labels.join(', ') : null
    }

    const captureRatingBeforeMap = (cfg) => {
      if (!cfg?.container) return null
      const overlayType = cfg.container.dataset.overlayType || ''
      const libraryId = cfg.container.dataset.libraryId
      if (!libraryId || !['movie', 'show', 'episode'].includes(overlayType)) return null
      const groupMap = overlayType === 'episode' ? RATING_MASS_GROUP_MAP_EPISODE : RATING_MASS_GROUP_MAP
      const before = {}
      Object.values(groupMap).forEach(group => {
        before[group] = getCurrentMassToggleLabel(libraryId, group) || 'None'
      })
      cfg.container._ratingBeforeMap = before
      return before
    }

    const renderRatingMappingModal = (cfg) => {
      if (!cfg?.container || cfg.id !== 'overlay_ratings') return
      const allEl = cfg.container.querySelector('[data-rating-mapping-all]')
      if (!allEl) return
      const token = `${Date.now()}-${Math.random().toString(16).slice(2)}`
      cfg.container.dataset.ratingMappingToken = token
      const overlayType = cfg.container.dataset.overlayType || ''
      const groupMap = overlayType === 'episode' ? RATING_MASS_GROUP_MAP_EPISODE : RATING_MASS_GROUP_MAP
      const ratingTypes = [
        { key: 'critic', label: 'Critic', group: groupMap.critic },
        { key: 'audience', label: 'Audience', group: groupMap.audience },
        { key: 'user', label: 'User', group: groupMap.user }
      ]
      const libraryId = cfg.container?.dataset?.libraryId || ''
      const normalizeLabel = (value) => (value || '').toString().toLowerCase().replace(/\s+/g, ' ').trim()
      const getGroupSourceOptions = (group) => {
        if (!libraryId || !group) return []
        const selector = `[id^="${libraryId}-attribute_${group}_"]`
        const labels = []
        document.querySelectorAll(selector).forEach(input => {
          const label = document.querySelector(`label[for="${input.id}"]`)
          const text = (label?.textContent || '').trim()
          if (!text || !text.startsWith('Use ')) return
          if (!labels.includes(text)) labels.push(text)
        })
        return labels
      }

      const imageSelect = getTemplateInput(cfg, 'rating1_image') || getTemplateInput(cfg, 'rating2_image') || getTemplateInput(cfg, 'rating3_image')
      const optionMap = new Map()
      if (imageSelect && imageSelect.options) {
        Array.from(imageSelect.options).forEach(opt => {
          const value = (opt.value || '').toString()
          const label = (opt.textContent || '').trim() || value
          const key = `${value}||${label}`
          if (!optionMap.has(key)) {
            optionMap.set(key, { value, label })
          }
        })
      }
      const options = Array.from(optionMap.values()).filter(opt => {
        const value = (opt.value || '').toString().trim()
        const label = (opt.label || '').toString().trim().toLowerCase()
        return value || (label && label !== 'none')
      })
      if (!options.length) {
        allEl.replaceChildren()
        const empty = document.createElement('div')
        empty.className = 'text-muted'
        empty.textContent = 'No badge options found.'
        allEl.appendChild(empty)
      } else {
        const rowsHtml = options.map(opt => {
          const value = opt.value || ''
          const label = opt.label || value
          const imageKey = normalizeRatingImageKey(value, label)
          const sourceMap = overlayType === 'episode'
            ? RATING_SOURCE_MAP_EPISODE[imageKey]
            : RATING_SOURCE_MAP[imageKey]
          const previewUrl = buildRatingFilenameCandidates(value, label)[0] || ''
          const previewHtml = previewUrl
            ? `<img src="${previewUrl}" alt="${escapeHtml(label)}" class="rating-mapping-icon">`
            : '<div class="rating-mapping-icon rating-mapping-icon--empty">?</div>'
          const fontKey = getRatingFontKey(value, label)
          const mappedFont = RATING_FONT_MAP[fontKey] || 'Default'
          const isStarBadge = imageKey === 'star'
          const typeMappings = ratingTypes.map(type => {
            const source = sourceMap ? (sourceMap[type.key] || sourceMap.any || null) : null
            let groupLabel = source ? (RATING_GROUP_LABEL_MAP[type.group] || type.group || '') : '—'
            const baseToggleLabel = source
              ? (getMassToggleLabel(cfg.container.dataset.libraryId, type.group, source) || RATING_SOURCE_LABEL_MAP[source] || source)
              : '—'
            let toggleLabel = getRatingToggleLabel(imageKey, source, baseToggleLabel)
            if (isStarBadge && !source) {
              groupLabel = RATING_GROUP_LABEL_MAP[type.group] || type.group || ''
              toggleLabel = 'Pick a source'
            }
            const serviceKey = source ? (RATING_SOURCE_SERVICE_MAP[source] || null) : null
            const serviceLabel = serviceKey ? (SERVICE_LABEL_MAP[serviceKey] || serviceKey) : 'N/A'
            const hasMapping = toggleLabel !== '—' && groupLabel !== '—'
            return {
              typeKey: type.key,
              typeLabel: type.label,
              groupKey: type.group,
              groupLabel,
              toggleLabel,
              serviceKey,
              serviceLabel,
              hasMapping
            }
          })
          const sourceKeywords = {
            anidb: ['anidb'],
            imdb: ['imdb'],
            letterboxd: ['letterboxd'],
            mdb: ['mdblist score', 'mdblist average score', 'mdblist '],
            metacritic: ['metacritic'],
            rt_tomato: ['rotten tomatoes'],
            rt_popcorn: ['rt audience'],
            trakt: ['trakt'],
            mal: ['myanimelist', 'mal'],
            tmdb: ['tmdb']
          }
          const keywordFilters = sourceKeywords[imageKey] || []
          const groupOptions = [
            ...getGroupSourceOptions(groupMap.critic),
            ...getGroupSourceOptions(groupMap.audience),
            ...getGroupSourceOptions(groupMap.user)
          ]
          const uniqueOptions = Array.from(new Set(groupOptions))
          let filteredOptions = uniqueOptions
          if (imageKey === 'mdb') {
            filteredOptions = uniqueOptions.filter(option => option.startsWith('Use MDBList'))
          } else if (imageKey === 'rt_tomato') {
            filteredOptions = uniqueOptions.filter(option => {
              const normalized = normalizeLabel(option)
              if (normalized.includes('audience')) return false
              return normalized.includes('rotten tomatoes') || normalized.startsWith('use rt')
            })
          } else if (keywordFilters.length) {
            filteredOptions = uniqueOptions.filter(option => {
              const normalized = normalizeLabel(option)
              return keywordFilters.some(keyword => normalized.includes(keyword))
            })
          }
          const pickedLabels = new Set(
            typeMappings
              .map(entry => entry.toggleLabel)
              .filter(toggleLabel => toggleLabel && toggleLabel !== '—' && toggleLabel !== 'Pick a source')
              .map(normalizeLabel)
          )
          const pillJumpMap = {
            tmdb: '020-tmdb',
            mdblist: '060-mdblist',
            anidb: '100-anidb',
            trakt: '130-trakt',
            myanimelist: '140-mal',
            omdb: '050-omdb',
            plex: '010-plex'
          }
          const optionHtml = filteredOptions.length
            ? filteredOptions.map(option => {
              const isPicked = pickedLabels.has(normalizeLabel(option))
              const viaMatch = option.match(/\s+via\s+([A-Za-z0-9]+)/i)
              const baseText = option
              const normalized = normalizeLabel(option)
              let serviceTag = ''
              if (viaMatch) {
                serviceTag = viaMatch[1]
              } else if (normalized === 'use imdb rating') {
                serviceTag = 'N/A'
              } else if (normalized.includes('anidb')) {
                serviceTag = 'AniDB'
              } else if (normalized.includes('imdb')) {
                serviceTag = 'IMDb'
              } else if (normalized.includes('tmdb')) {
                serviceTag = 'TMDb'
              } else if (normalized.includes('trakt')) {
                serviceTag = 'Trakt'
              } else if (normalized.includes('myanimelist') || normalized.includes('mal')) {
                serviceTag = 'MyAnimeList'
              } else if (normalized.includes('letterboxd')) {
                serviceTag = 'Letterboxd'
              } else if (normalized.includes('metacritic')) {
                serviceTag = 'Metacritic'
              } else if (normalized.includes('rotten tomatoes') || normalized.startsWith('use rt')) {
                serviceTag = 'RT'
              } else if (normalized.includes('mdblist')) {
                serviceTag = 'MDBList'
              } else if (normalized.includes('omdb')) {
                serviceTag = 'OMDb'
              } else if (normalized.includes('plex')) {
                serviceTag = 'Plex'
              }
              const labelText = baseText
              const pickedHtml = isPicked
                ? ' <img src="/static/favicon.png" alt="Picked" title="Picked" class="rating-mapping-picked-icon">'
                : ''
              const arrowHtml = serviceTag
                ? ' <i class="bi bi-arrow-left-right rating-mapping-option-arrow" aria-hidden="true"></i>'
                : ''
              const serviceKey = serviceTag ? normalizeLabel(serviceTag) : ''
              const jumpTarget = serviceKey ? pillJumpMap[serviceKey] : null
              let validationStatus = 'neutral'
              if (normalized === 'use imdb rating') {
                validationStatus = 'validated'
              } else if (serviceKey && serviceTag !== 'N/A') {
                const validated = getServiceValidation(serviceKey)
                validationStatus = validated ? 'validated' : 'unvalidated'
              }
              const viaHtml = serviceTag
                ? (jumpTarget && serviceTag !== 'N/A'
                    ? ` <a class="rating-mapping-option-via rating-mapping-option-link rating-mapping-option-via--${validationStatus}" href="javascript:void(0);" onclick="jumpTo('${jumpTarget}')">${escapeHtml(serviceTag)}</a>`
                    : ` <span class="rating-mapping-option-via rating-mapping-option-via--${validationStatus}">${escapeHtml(serviceTag)}</span>`)
                : ''
              return `<div class="rating-mapping-option${isPicked ? ' is-picked' : ''}"><span class="rating-mapping-option-label">${escapeHtml(labelText)}</span>${pickedHtml}${arrowHtml}${viaHtml}</div>`
            }).join('')
            : '<div class="text-muted">No sources found</div>'
          const sourceHtml = `
            <div class="rating-mapping-option-list">
              ${optionHtml}
            </div>
          `
          const fallbackEntry = typeMappings[0] || null
          const sampleEntry = typeMappings.find(entry => entry.hasMapping) || fallbackEntry
          const isRtBadge = imageKey === 'rt_tomato' || imageKey === 'rt_popcorn'
          const sampleHtml = sampleEntry
            ? (isRtBadge
                ? `
                <div class="rating-mapping-sample-variants">
                  <div class="rating-mapping-sample-variant">
                    <div class="rating-mapping-sample-label">Fresh ≥ ${RT_ROTTEN_THRESHOLD}%</div>
                    <img class="rating-mapping-sample is-loading"
                      data-rating-sample
                      data-rating-type="${sampleEntry.typeKey}"
                      data-rating-image-value="${escapeHtml(value)}"
                      data-rating-image-label="${escapeHtml(label)}"
                      data-rating-style-slot="rating1"
                      data-rating-font="${escapeHtml(mappedFont)}"
                      data-rating-variant="fresh"
                      alt="${escapeHtml(label)} ${sampleEntry.typeLabel} fresh sample" />
                  </div>
                  <div class="rating-mapping-sample-variant">
                    <div class="rating-mapping-sample-label">Rotten &lt; ${RT_ROTTEN_THRESHOLD}%</div>
                    <img class="rating-mapping-sample is-loading"
                      data-rating-sample
                      data-rating-type="${sampleEntry.typeKey}"
                      data-rating-image-value="${escapeHtml(value)}"
                      data-rating-image-label="${escapeHtml(label)}"
                      data-rating-style-slot="rating1"
                      data-rating-font="${escapeHtml(mappedFont)}"
                      data-rating-variant="rotten"
                      alt="${escapeHtml(label)} ${sampleEntry.typeLabel} rotten sample" />
                  </div>
                </div>
              `
                : `<img class="rating-mapping-sample is-loading"
                  data-rating-sample
                  data-rating-type="${sampleEntry.typeKey}"
                  data-rating-image-value="${escapeHtml(value)}"
                  data-rating-image-label="${escapeHtml(label)}"
                  data-rating-style-slot="rating1"
                  data-rating-font="${escapeHtml(mappedFont)}"
                  alt="${escapeHtml(label)} ${sampleEntry.typeLabel} sample" />`)
            : '<div class="rating-mapping-sample rating-mapping-sample--empty">N/A</div>'
          return `
            <tr>
              <td class="rating-mapping-col-badge">
                <div class="d-flex align-items-center gap-2">
                  ${previewHtml}
                  <div>
                    <div class="fw-semibold">${escapeHtml(label || 'None')}</div>
                    <div class="text-muted small">${escapeHtml(value || '')}</div>
                  </div>
                </div>
              </td>
              <td class="rating-mapping-col-font">${escapeHtml(mappedFont)}</td>
              <td class="rating-mapping-col-source">${sourceHtml}</td>
              <td class="rating-mapping-sample-cell">
                ${sampleHtml}
              </td>
            </tr>
          `
        }).join('')
        const ratingTypeRowsHtml = ratingTypes.map(type => {
          const groupLabel = RATING_GROUP_LABEL_MAP[type.group] || type.group || ''
          return `
            <tr>
              <td>${escapeHtml(type.label)}</td>
              <td>${escapeHtml(groupLabel)}</td>
            </tr>
          `
        }).join('')
        const tableHelpHtml = `
          <div class="rating-mapping-help small text-muted mb-2">
            Rating Type maps directly to Library Operations toggles. Use this quick reference when reading the
            badge table below.
          </div>
          <div class="table-responsive rating-mapping-type-map mb-3">
            <table class="table table-sm table-dark table-striped align-middle mb-0">
              <thead>
                <tr>
                  <th>Rating Type</th>
                  <th>Attributes | Library Operations</th>
                </tr>
              </thead>
              <tbody>
                ${ratingTypeRowsHtml}
              </tbody>
            </table>
          </div>
          <div class="small text-muted mb-2">
            Source <i class="bi bi-arrow-left-right rating-mapping-option-arrow" aria-hidden="true"></i>
            <span class="rating-mapping-option-via rating-mapping-option-via--header rating-mapping-option-via--neutral">Service</span>
            pills are clickable; colors reflect validation status. Auto-selected entries are highlighted and tagged with
            <img src="/static/favicon.png" alt="Picked" class="rating-mapping-picked-icon">.
          </div>
        `
        const tableHtml = `
          ${tableHelpHtml}
          <div class="table-responsive">
            <table class="table table-sm table-dark table-striped align-middle mb-0 rating-mapping-table">
              <thead>
                <tr>
                  <th class="rating-mapping-col-badge">Rating Image</th>
                  <th class="rating-mapping-col-font">Font</th>
                  <th class="rating-mapping-col-source">
                    Source
                    <i class="bi bi-arrow-left-right rating-mapping-option-arrow" aria-hidden="true"></i>
                    <span class="rating-mapping-option-via rating-mapping-option-via--header rating-mapping-option-via--neutral">Service</span>
                  </th>
                  <th>Sample</th>
                </tr>
              </thead>
              <tbody>
                ${rowsHtml}
              </tbody>
            </table>
          </div>
        `
        allEl.replaceChildren()
        const parser = new DOMParser()
        const doc = parser.parseFromString(`<div>${tableHtml}</div>`, 'text/html')
        const container = doc.body.firstElementChild
        if (container) {
          Array.from(container.childNodes).forEach(node => {
            allEl.appendChild(document.importNode(node, true))
          })
        }
      }

      hydrateRatingMappingSamples(cfg, token)
    }

    const getRatingsPreviewOverrideEntries = (cfg) => {
      const config = getOverlaySourceOverrideConfig(cfg)
      const section = cfg?.container?.querySelector('[data-overlay-source-editor="true"]')
      const hiddenHost = section?.querySelector('[data-overlay-source-hidden]')
      if (!config || !hiddenHost) return []
      return readOverlaySourceOverrideState(cfg, config, hiddenHost)
    }

    const getRatingsPreviewOverrideEntry = (cfg, imageValue, imageLabel = '') => {
      const imageKey = normalizeRatingImageKey(imageValue, imageLabel)
      if (!imageKey) return null
      return getRatingsPreviewOverrideEntries(cfg).find(entry => {
        return entry.badgeKey === imageKey && entry.sourceType && entry.value
      }) || null
    }

    const getTemplateValue = (cfg, key, fallback) => {
      const input = getTemplateInput(cfg, key)
      if (!input) return fallback
      const defaultVal = input.dataset?.default ?? fallback
      if (input.type === 'number') {
        const n = Number(input.value)
        if (Number.isFinite(n)) return n
        const fallbackNum = Number(defaultVal)
        return Number.isFinite(fallbackNum) ? fallbackNum : fallback
      }
      if (input.tagName === 'SELECT') {
        return input.value || defaultVal
      }
      return input.value || defaultVal
    }

    const buildRatingSampleDataUrl = async (cfg, options = {}) => {
      if (!cfg?.container || cfg.id !== 'overlay_ratings') return null
      const {
        slotKey,
        ratingType,
        imageValue,
        imageLabel,
        styleSlotKey,
        fontOverride,
        sampleVariant
      } = options || {}
      const slotDefs = {
        rating1: {
          imageKey: 'rating1_image',
          fontKey: 'rating1_font',
          fontSizeKey: 'rating1_font_size',
          fontColorKey: 'rating1_font_color',
          strokeWidthKey: 'rating1_stroke_width',
          strokeColorKey: 'rating1_stroke_color'
        },
        rating2: {
          imageKey: 'rating2_image',
          fontKey: 'rating2_font',
          fontSizeKey: 'rating2_font_size',
          fontColorKey: 'rating2_font_color',
          strokeWidthKey: 'rating2_stroke_width',
          strokeColorKey: 'rating2_stroke_color'
        },
        rating3: {
          imageKey: 'rating3_image',
          fontKey: 'rating3_font',
          fontSizeKey: 'rating3_font_size',
          fontColorKey: 'rating3_font_color',
          strokeWidthKey: 'rating3_stroke_width',
          strokeColorKey: 'rating3_stroke_color'
        }
      }
      const slot = slotDefs[slotKey] || slotDefs.rating1
      if (!slot) return null
      const styleSlot = slotDefs[styleSlotKey] || slot
      const imageVal = (imageValue || '').toString().trim() ||
        (getTemplateInput(cfg, slot.imageKey)?.value || getTemplateInput(cfg, slot.imageKey)?.dataset?.default || '').toString().trim()
      const labelVal = (imageLabel || '').toString().trim() ||
        (getTemplateInput(cfg, slot.imageKey)?.selectedOptions?.[0]?.textContent || '').trim() ||
        imageVal
      if (!imageVal) return null
      const imageKey = normalizeRatingImageKey(imageVal, labelVal)
      const sample = getRatingSampleValue(ratingType, imageVal, labelVal, sampleVariant)
      let img
      let useStarFallback = false
      const overrideEntry = getRatingsPreviewOverrideEntry(cfg, imageVal, labelVal)
      if (overrideEntry) {
        try {
          img = await loadImage(buildOverlaySourcePreviewUrl(overrideEntry.sourceType, overrideEntry.value))
        } catch (err) {
          console.warn('[OverlayBoards] Failed to load rating override image', {
            value: imageVal,
            label: labelVal,
            override: overrideEntry,
            err
          })
        }
      }
      if (!img) {
        const urls = getRatingSampleImageUrls(imageVal, labelVal, sample)
        if (!urls.length) return null
        try {
          img = await loadImageWithFallback(urls)
        } catch (err) {
          if (imageKey === 'star' || imageKey === 'plex_star') {
            useStarFallback = true
          } else {
            console.warn('[OverlayBoards] Failed to load rating image', { value: imageVal, label: labelVal, err })
            return null
          }
        }
      }
      const overrideFont = (fontOverride || '').toString().trim()
      const fontFile = (overrideFont && overrideFont !== 'Default')
        ? overrideFont
        : getTemplateValue(cfg, styleSlot.fontKey, 'Inter-Medium.ttf')
      const fontSize = getTemplateValue(cfg, styleSlot.fontSizeKey, 55)
      const fontColor = getTemplateValue(cfg, styleSlot.fontColorKey, '#FFFFFFFF')
      const strokeWidth = getTemplateValue(cfg, styleSlot.strokeWidthKey, 1)
      const strokeColor = getTemplateValue(cfg, styleSlot.strokeColorKey, '#00000000')
      const text = sample.text || 'NR'
      const vars = getBackdropVars(cfg)
      const contentWidth = Math.max(1, Number(vars.back_width) || 160)
      const contentHeight = Math.max(1, Number(vars.back_height) || 160)
      const innerPad = Number.isFinite(Number(vars.back_padding))
        ? Math.max(0, Number(vars.back_padding))
        : Math.round(contentHeight * 0.08)
      const boxWidth = contentWidth + (innerPad * 2)
      const boxHeight = contentHeight + (innerPad * 2)
      const canvas = document.createElement('canvas')
      canvas.width = Math.ceil(boxWidth)
      canvas.height = Math.ceil(boxHeight)
      const ctx = canvas.getContext('2d')
      if (!ctx) return null
      const fill = parseHexColor(vars.back_color, { r: 0, g: 0, b: 0, a: 0 })
      const stroke = parseHexColor(vars.back_line_color, { r: 0, g: 0, b: 0, a: 0 })
      const lineWidth = Math.max(0, Number(vars.back_line_width) || 0)
      const radius = Math.max(0, Number(vars.back_radius) || 0)

      drawRoundedRect(ctx, 0, 0, boxWidth, boxHeight, radius)
      if (fill.a > 0) {
        ctx.fillStyle = `rgba(${fill.r}, ${fill.g}, ${fill.b}, ${fill.a})`
        ctx.fill()
      }
      if (lineWidth > 0 && stroke.a > 0) {
        const inset = lineWidth / 2
        const strokeRadius = Math.max(0, radius - inset)
        drawRoundedRect(ctx, inset, inset, boxWidth - (inset * 2), boxHeight - (inset * 2), strokeRadius)
        ctx.strokeStyle = `rgba(${stroke.r}, ${stroke.g}, ${stroke.b}, ${stroke.a})`
        ctx.lineWidth = lineWidth
        ctx.stroke()
      }

      const family = (await ensureRuntimeFontLoaded(fontFile)) || normalizeFontFile(fontFile).family || 'Inter-Medium'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'alphabetic'
      ctx.font = `700 ${Math.max(1, Number(fontSize) || 55)}px "${family}"`
      const textBottom = boxHeight - innerPad
      drawTextWithStroke(ctx, text, boxWidth / 2, textBottom, fontColor, strokeColor, strokeWidth)

      const iconMaxHeight = Math.max(1, boxHeight - (Number(fontSize) || 55) - (innerPad * 2))
      const iconMaxWidth = Math.max(1, boxWidth - (innerPad * 2))
      if (img) {
        const scale = Math.min(iconMaxWidth / img.width, iconMaxHeight / img.height, 1)
        const drawW = img.width * scale
        const drawH = img.height * scale
        const drawX = (boxWidth - drawW) / 2
        const drawY = innerPad + ((iconMaxHeight - drawH) / 2)
        ctx.drawImage(img, drawX, drawY, drawW, drawH)
      } else if (useStarFallback) {
        const centerX = boxWidth / 2
        const centerY = innerPad + (iconMaxHeight / 2)
        const outerRadius = Math.min(iconMaxWidth, iconMaxHeight) * 0.45
        const innerRadius = outerRadius * 0.5
        drawStarShape(ctx, centerX, centerY, 5, outerRadius, innerRadius)
      }

      return canvas.toDataURL('image/png')
    }

    const hydrateRatingMappingSamples = (cfg, token) => {
      if (!cfg?.container) return
      const detailEl = cfg.container.querySelector('[data-rating-mapping-detail]')
      const allEl = cfg.container.querySelector('[data-rating-mapping-all]')
      if (!detailEl && !allEl) return
      const placeholders = []
      if (detailEl) placeholders.push(...Array.from(detailEl.querySelectorAll('[data-rating-sample]')))
      if (allEl) placeholders.push(...Array.from(allEl.querySelectorAll('[data-rating-sample]')))
      if (!placeholders.length) return
      placeholders.forEach(async (imgEl) => {
        const slotKey = imgEl.dataset.ratingSlot
        const ratingType = imgEl.dataset.ratingType
        const imageValue = imgEl.dataset.ratingImageValue
        const imageLabel = imgEl.dataset.ratingImageLabel
        const styleSlotKey = imgEl.dataset.ratingStyleSlot
        const fontOverride = imgEl.dataset.ratingFont
        const sampleVariant = imgEl.dataset.ratingVariant
        const url = await buildRatingSampleDataUrl(cfg, {
          slotKey,
          ratingType,
          imageValue,
          imageLabel,
          styleSlotKey,
          fontOverride,
          sampleVariant
        })
        if (cfg.container.dataset.ratingMappingToken !== token) return
        if (url) {
          imgEl.src = url
          imgEl.classList.remove('is-loading')
          return
        }
        imgEl.replaceWith(Object.assign(document.createElement('div'), {
          className: 'rating-mapping-sample rating-mapping-sample--empty',
          textContent: 'N/A'
        }))
      })
    }

    const updateRatingSyncStatus = (cfg) => {
      if (!cfg?.container) return
      const overlayType = cfg.container.dataset.overlayType || ''
      if (!['movie', 'show', 'episode'].includes(overlayType)) return
      const libraryId = cfg.container.dataset.libraryId
      const slots = [
        { ratingKey: 'rating1', imageKey: 'rating1_image', label: 'Rating 1' },
        { ratingKey: 'rating2', imageKey: 'rating2_image', label: 'Rating 2' },
        { ratingKey: 'rating3', imageKey: 'rating3_image', label: 'Rating 3' }
      ]
      slots.forEach(slot => {
        const statusEl = cfg.container.querySelector(`.rating-sync-status[data-rating-slot="${slot.ratingKey}"]`)
        if (!statusEl) return
        const ratingSelect = getTemplateInput(cfg, slot.ratingKey)
        const imageSelect = getTemplateInput(cfg, slot.imageKey)
        const ratingValRaw = (ratingSelect?.value || ratingSelect?.dataset?.default || '').toString().trim().toLowerCase()
        const imageVal = imageSelect?.value || imageSelect?.dataset?.default
        const ratingLabel = (ratingSelect?.selectedOptions?.[0]?.textContent || '').trim() || ratingValRaw
        const imageLabel = (imageSelect?.selectedOptions?.[0]?.textContent || '').trim() || imageVal || 'None'
        if (!ratingValRaw || !imageVal) {
          setStatusIcon(statusEl, 'neutral', 'Select rating and image to sync with Library Operations.')
          return
        }
        const group = overlayType === 'episode'
          ? RATING_MASS_GROUP_MAP_EPISODE[ratingValRaw]
          : RATING_MASS_GROUP_MAP[ratingValRaw]
        if (!group) {
          setStatusIcon(statusEl, 'neutral', 'Select rating and image to sync with Library Operations.')
          return
        }
        const imageKey = normalizeRatingImageKey(imageVal, imageLabel)
        const sourceMap = overlayType === 'episode'
          ? RATING_SOURCE_MAP_EPISODE[imageKey]
          : RATING_SOURCE_MAP[imageKey]
        const source = sourceMap ? (sourceMap[ratingValRaw] || sourceMap.any || null) : null
        const currentSource = getCurrentMassToggleValue(libraryId, group)
        const effectiveSource = currentSource || source
        if (!effectiveSource) {
          setStatusIcon(statusEl, 'neutral', `${slot.label} (${ratingLabel} + ${imageLabel}) has no matching rating source.`)
          return
        }
        const groupLabel = RATING_GROUP_LABEL_MAP[group] || group
        const toggleLabel = currentSource
          ? (getCurrentMassToggleLabel(libraryId, group) || getMassToggleLabel(libraryId, group, currentSource) || RATING_SOURCE_LABEL_MAP[currentSource] || currentSource)
          : (getMassToggleLabel(libraryId, group, source) || RATING_SOURCE_LABEL_MAP[source] || source)
        let message = `${slot.label} (${ratingLabel} + ${imageLabel}) → ${groupLabel}: ${toggleLabel}`
        if (currentSource && source && currentSource !== source) {
          const defaultLabel = getMassToggleLabel(libraryId, group, source) || RATING_SOURCE_LABEL_MAP[source] || source
          message = `${slot.label} (${ratingLabel} + ${imageLabel}) preserves ${groupLabel}: ${toggleLabel}. Default for this badge would be ${defaultLabel}.`
        }
        const service = RATING_SOURCE_SERVICE_MAP[effectiveSource] || null
        if (!service) {
          message += '. No service required.'
          setStatusIcon(statusEl, 'neutral', message)
          return
        }
        const serviceLabel = SERVICE_LABEL_MAP[service] || service
        const validated = getServiceValidation(service)
        if (validated) {
          message += `. ${serviceLabel} validated.`
          setStatusIcon(statusEl, 'ok', message)
        } else {
          message += `. ${serviceLabel} is not validated; ratings won't update until validated.`
          setStatusIcon(statusEl, 'warn', message)
        }
      })
    }

    const enforceUniqueRatingTypes = (cfg) => {
      if (!cfg?.container || cfg.id !== 'overlay_ratings') return
      const selects = [
        getTemplateInput(cfg, 'rating1'),
        getTemplateInput(cfg, 'rating2'),
        getTemplateInput(cfg, 'rating3')
      ].filter(Boolean)
      if (!selects.length) return
      const counts = {}
      selects.forEach((select) => {
        const value = (select.value || select.dataset?.default || '').toString().trim().toLowerCase()
        if (!value || value === 'none') return
        counts[value] = (counts[value] || 0) + 1
      })
      selects.forEach((select) => {
        const selectedValue = (select.value || select.dataset?.default || '').toString().trim().toLowerCase()
        Array.from(select.options || []).forEach((option) => {
          const optValue = (option.value || '').toString().trim().toLowerCase()
          if (!optValue || optValue === 'none') {
            option.disabled = false
            return
          }
          if (optValue === selectedValue) {
            option.disabled = false
            return
          }
          option.disabled = (counts[optValue] || 0) > 0
        })
      })
      const hasDuplicate = Object.values(counts).some(count => count > 1)
      const existing = cfg.container.querySelector('.rating-unique-warning')
      if (hasDuplicate) {
        if (!existing) {
          const anchor = selects[0].closest('.input-group') || selects[0].parentElement
          if (anchor) {
            const warning = document.createElement('div')
            warning.className = 'alert alert-warning py-1 px-2 mt-2 small rating-unique-warning'
            warning.textContent = 'Each rating type (Critic/Audience/User) can only be used once. Please choose unique values.'
            anchor.insertAdjacentElement('afterend', warning)
          }
        }
      } else if (existing) {
        existing.remove()
      }
    }

    const setMassRatingSource = (libraryId, prefix, source, opts = {}) => {
      if (!libraryId || !prefix) return
      const preserveExisting = Boolean(opts.preserveExisting)
      const current = getCurrentMassToggleValue(libraryId, prefix)
      if (preserveExisting && current) return current
      if (current && current === source) return current
      const inputPrefix = `${libraryId}-attribute_${prefix}_`
      const toggles = document.querySelectorAll(`input.form-check-input[id^="${inputPrefix}"]`)
      toggles.forEach(input => {
        if (input.checked) {
          input.checked = false
          input.dispatchEvent(new Event('change', { bubbles: true }))
        }
      })
      if (!source) return
      const target = document.getElementById(`${inputPrefix}${source}`)
      if (target) {
        target.checked = true
        target.dispatchEvent(new Event('change', { bubbles: true }))
      }
      return source
    }

    const syncRatingSources = (cfg, slot, opts = {}) => {
      if (!cfg?.container) return
      const overlayType = cfg.container.dataset.overlayType || ''
      if (!['movie', 'show', 'episode'].includes(overlayType)) return
      const libraryId = cfg.container.dataset.libraryId
      const ratingSelect = getTemplateInput(cfg, slot.ratingKey)
      const imageSelect = getTemplateInput(cfg, slot.imageKey)
      const ratingVal = (ratingSelect?.value || ratingSelect?.dataset?.default || '').toString().trim().toLowerCase()
      const group = overlayType === 'episode'
        ? RATING_MASS_GROUP_MAP_EPISODE[ratingVal]
        : RATING_MASS_GROUP_MAP[ratingVal]
      if (!group) return
      const imageVal = imageSelect?.value || imageSelect?.dataset?.default
      const imageLabel = imageSelect?.selectedOptions?.[0]?.textContent
      const imageKey = normalizeRatingImageKey(imageVal, imageLabel)
      const sourceMap = overlayType === 'episode'
        ? RATING_SOURCE_MAP_EPISODE[imageKey]
        : RATING_SOURCE_MAP[imageKey]
      const source = sourceMap ? (sourceMap[ratingVal] || sourceMap.any || null) : null
      setMassRatingSource(libraryId, group, source, opts)
    }

    if (typeof window !== 'undefined') {
      window.__qsOverlayTestHooks = window.__qsOverlayTestHooks || {}
      window.__qsOverlayTestHooks.syncRatingSources = syncRatingSources
      window.__qsOverlayTestHooks.getCurrentMassToggleValue = getCurrentMassToggleValue
    }

    const sortRatingImageOptions = (input) => {
      if (!input || input.tagName !== 'SELECT') return
      const options = Array.from(input.options)
      if (!options.length) return
      const selectedValue = input.value
      const noneOption = options.find(opt => opt.value === '')
      const rest = options.filter(opt => opt.value !== '')
      rest.sort((a, b) => {
        const aText = (a.textContent || '').trim().toLowerCase()
        const bText = (b.textContent || '').trim().toLowerCase()
        return aText.localeCompare(bText)
      })
      input.replaceChildren()
      if (noneOption) input.appendChild(noneOption)
      rest.forEach(opt => input.appendChild(opt))
      if (selectedValue) input.value = selectedValue
    }

    const getRatingFontKey = (value, label) => {
      const key = (value || '').toString().trim().toLowerCase()
      if (key) return key
      return (label || '').toString().trim().toLowerCase()
    }

    const ensureFontOption = (input, value) => {
      if (!input || input.tagName !== 'SELECT' || !value) return
      const exists = Array.from(input.options || []).some(opt => opt.value === value)
      if (exists) return
      const option = document.createElement('option')
      option.value = value
      option.textContent = value.split(/[\\/]/).pop()
      input.appendChild(option)
    }

    const shouldAutoUpdateFont = (input) => {
      if (!input) return false
      if (input.dataset.ratingFontUser === 'true') return false
      if (input.dataset.userModified === 'true') return false
      const current = (input.value || '').trim()
      const defaultVal = (input.dataset.default || '').trim()
      const autoVal = (input.dataset.ratingFontAutoValue || '').trim()
      if (!current) return true
      if (current === defaultVal) return true
      return input.dataset.ratingFontAuto === 'true' && current === autoVal
    }

    const applyRatingFontDefaults = (cfg) => {
      if (!cfg || cfg.id !== 'overlay_ratings') return
      const forceFont = cfg.container?.dataset?.ratingFontForce === 'true'
      const slots = [
        { imageKey: 'rating1_image', fontKey: 'rating1_font' },
        { imageKey: 'rating2_image', fontKey: 'rating2_font' },
        { imageKey: 'rating3_image', fontKey: 'rating3_font' }
      ]
      slots.forEach(slot => {
        const imageInput = getTemplateInput(cfg, slot.imageKey)
        const fontInput = getTemplateInput(cfg, slot.fontKey)
        if (!imageInput || !fontInput) return
        sortRatingImageOptions(imageInput)
        const imageVal = imageInput.value || imageInput.dataset?.default
        const label = imageInput.selectedOptions?.[0]?.textContent
        const key = getRatingFontKey(imageVal, label)
        const mapped = RATING_FONT_MAP[key]
        if (!mapped) return
        if (!forceFont && !shouldAutoUpdateFont(fontInput)) return
        ensureFontOption(fontInput, mapped)
        fontInput.value = mapped
        fontInput.dataset.default = mapped
        fontInput.dataset.ratingFontAuto = 'true'
        fontInput.dataset.ratingFontAutoValue = mapped
        if (forceFont) {
          fontInput.dataset.ratingFontUser = 'false'
          fontInput.dataset.userModified = 'false'
        }
        if (typeof window.updateFontPreviewForSelect === 'function') {
          window.updateFontPreviewForSelect(fontInput)
        }
      })
      if (forceFont && cfg.container) {
        delete cfg.container.dataset.ratingFontForce
      }
    }

    const buildRatingsCompositeDataUrl = async (cfg) => {
      if (cfg.id !== 'overlay_ratings') return null
      const fontDefaults = {
        font: 'Inter-Medium.ttf',
        font_size: 63,
        font_color: '#FFFFFFFF',
        stroke_width: 1,
        stroke_color: '#00000000'
      }
      const getInputValue = (input, fallback) => {
        if (!input) return fallback
        const defaultVal = input.dataset?.default ?? fallback
        if (input.type === 'number') {
          const n = Number(input.value)
          if (Number.isFinite(n)) return n
          const fallbackNum = Number(defaultVal)
          return Number.isFinite(fallbackNum) ? fallbackNum : fallback
        }
        if (input.tagName === 'SELECT') {
          return input.value || defaultVal
        }
        return input.value || defaultVal
      }
      const getSlotValue = (key, fallback) => {
        return getInputValue(getTemplateInput(cfg, key), fallback)
      }
      const slots = [
        {
          ratingKey: 'rating1',
          imageKey: 'rating1_image',
          fontKey: 'rating1_font',
          fontSizeKey: 'rating1_font_size',
          fontColorKey: 'rating1_font_color',
          strokeWidthKey: 'rating1_stroke_width',
          strokeColorKey: 'rating1_stroke_color'
        },
        {
          ratingKey: 'rating2',
          imageKey: 'rating2_image',
          fontKey: 'rating2_font',
          fontSizeKey: 'rating2_font_size',
          fontColorKey: 'rating2_font_color',
          strokeWidthKey: 'rating2_stroke_width',
          strokeColorKey: 'rating2_stroke_color'
        },
        {
          ratingKey: 'rating3',
          imageKey: 'rating3_image',
          fontKey: 'rating3_font',
          fontSizeKey: 'rating3_font_size',
          fontColorKey: 'rating3_font_color',
          strokeWidthKey: 'rating3_stroke_width',
          strokeColorKey: 'rating3_stroke_color'
        }
      ]
      const isEmpty = (val) => {
        if (val === null || val === undefined) return true
        const str = String(val).trim()
        return str === '' || str.toLowerCase() === 'none'
      }

      const items = []
      for (const slot of slots) {
        const ratingSelect = getTemplateInput(cfg, slot.ratingKey)
        const imageSelect = getTemplateInput(cfg, slot.imageKey)
        const ratingVal = ratingSelect?.value ?? ratingSelect?.dataset?.default
        const imageVal = imageSelect?.value ?? imageSelect?.dataset?.default
        if (isEmpty(ratingVal) || isEmpty(imageVal)) continue
        const label = imageSelect?.selectedOptions?.[0]?.textContent?.trim()
        const sample = getRatingSampleValue(ratingVal, imageVal, label)
        try {
          const overrideEntry = getRatingsPreviewOverrideEntry(cfg, imageVal, label)
          let img = null
          if (overrideEntry) {
            try {
              img = await loadImage(buildOverlaySourcePreviewUrl(overrideEntry.sourceType, overrideEntry.value))
            } catch (overrideError) {
              console.warn('[OverlayBoards] Failed to load rating override image', {
                value: imageVal,
                label,
                override: overrideEntry,
                err: overrideError
              })
            }
          }
          if (!img) {
            const urls = getRatingSampleImageUrls(imageVal, label, sample)
            if (!urls.length) continue
            img = await loadImageWithFallback(urls)
          }
          const text = sample.text || 'NR'
          const hOffset = Number(getSlotValue(`${slot.ratingKey}_horizontal_offset`, 0))
          const vOffset = Number(getSlotValue(`${slot.ratingKey}_vertical_offset`, 0))
          items.push({
            img,
            text,
            fontFile: getSlotValue(slot.fontKey, fontDefaults.font),
            fontSize: getSlotValue(slot.fontSizeKey, fontDefaults.font_size),
            fontColor: getSlotValue(slot.fontColorKey, fontDefaults.font_color),
            strokeWidth: getSlotValue(slot.strokeWidthKey, fontDefaults.stroke_width),
            strokeColor: getSlotValue(slot.strokeColorKey, fontDefaults.stroke_color),
            hOffset: Number.isFinite(hOffset) ? hOffset : 0,
            vOffset: Number.isFinite(vOffset) ? vOffset : 0
          })
        } catch (err) {
          console.warn('[OverlayBoards] Failed to load rating image', { value: imageVal, label, err })
        }
      }

      if (!items.length) return resolveOverlayImage(cfg)

      const fontFamilyMap = new Map()
      const fontLoads = []
      items.forEach((item) => {
        const fontFile = String(item.fontFile || '').trim()
        if (!fontFile || fontFamilyMap.has(fontFile)) return
        fontFamilyMap.set(fontFile, null)
        fontLoads.push(
          ensureRuntimeFontLoaded(fontFile).then((family) => {
            if (family) {
              fontFamilyMap.set(fontFile, family)
            }
          })
        )
      })
      if (fontLoads.length) {
        await Promise.all(fontLoads)
      }

      const vars = getBackdropVars(cfg)
      const contentWidth = Math.max(1, Number(vars.back_width) || 160)
      const contentHeight = Math.max(1, Number(vars.back_height) || 160)
      const innerPad = Number.isFinite(Number(vars.back_padding))
        ? Math.max(0, Number(vars.back_padding))
        : Math.round(contentHeight * 0.08)
      const boxWidth = contentWidth + (innerPad * 2)
      const boxHeight = contentHeight + (innerPad * 2)
      const alignmentRaw = String(getSlotValue('rating_alignment', 'vertical') || '').toLowerCase()
      const alignment = alignmentRaw === 'horizontal' ? 'horizontal' : 'vertical'
      const addonRaw = String(getSlotValue('addon_position', alignment === 'horizontal' ? 'left' : 'top') || '').toLowerCase()
      const addonPosition = addonRaw === 'left' ? 'left' : 'top'
      const hPosRaw = String(getSlotValue('horizontal_position', 'left') || '').toLowerCase()
      const vPosRaw = String(getSlotValue('vertical_position', 'center') || '').toLowerCase()
      const hPos = (hPosRaw === 'center' || hPosRaw === 'right') ? hPosRaw : 'left'
      const vPos = (vPosRaw === 'top' || vPosRaw === 'bottom') ? vPosRaw : 'center'
      const addonOffset = Math.max(0, Number(getSlotValue('addon_offset', 15)) || 0)
      const canvas = document.createElement('canvas')
      let minX = Infinity
      let minY = Infinity
      let maxX = -Infinity
      let maxY = -Infinity
      items.forEach(item => {
        minX = Math.min(minX, item.hOffset)
        minY = Math.min(minY, item.vOffset)
        maxX = Math.max(maxX, item.hOffset)
        maxY = Math.max(maxY, item.vOffset)
      })
      const boundLeft = minX
      const boundTop = minY
      const boundRight = maxX + boxWidth
      const boundBottom = maxY + boxHeight
      const anchorX = hPos === 'center'
        ? (boundLeft + boundRight) / 2
        : (hPos === 'right' ? boundRight : boundLeft)
      const anchorY = vPos === 'center'
        ? (boundTop + boundBottom) / 2
        : (vPos === 'bottom' ? boundBottom : boundTop)
      const shifted = items.map(item => ({
        ...item,
        renderX: item.hOffset - anchorX,
        renderY: item.vOffset - anchorY
      }))
      let minShiftX = Infinity
      let minShiftY = Infinity
      let maxShiftX = -Infinity
      let maxShiftY = -Infinity
      shifted.forEach(item => {
        minShiftX = Math.min(minShiftX, item.renderX)
        minShiftY = Math.min(minShiftY, item.renderY)
        maxShiftX = Math.max(maxShiftX, item.renderX)
        maxShiftY = Math.max(maxShiftY, item.renderY)
      })
      if (!Number.isFinite(minShiftX) || !Number.isFinite(minShiftY) || !Number.isFinite(maxShiftX) || !Number.isFinite(maxShiftY)) {
        return resolveOverlayImage(cfg)
      }
      const padX = minShiftX < 0 ? -minShiftX : 0
      const padY = minShiftY < 0 ? -minShiftY : 0
      canvas.width = Math.ceil((maxShiftX - minShiftX) + boxWidth)
      canvas.height = Math.ceil((maxShiftY - minShiftY) + boxHeight)
      const ctx = canvas.getContext('2d')
      if (!ctx) return resolveOverlayImage(cfg)

      const fill = parseHexColor(vars.back_color, { r: 0, g: 0, b: 0, a: 0 })
      const stroke = parseHexColor(vars.back_line_color, { r: 0, g: 0, b: 0, a: 0 })
      const lineWidth = Math.max(0, Number(vars.back_line_width) || 0)
      const radius = Math.max(0, Number(vars.back_radius) || 0)

      ctx.textAlign = 'center'
      ctx.textBaseline = 'alphabetic'

      shifted.forEach((item) => {
        const boxLeft = item.renderX + padX
        const boxTop = item.renderY + padY
        drawRoundedRect(ctx, boxLeft, boxTop, boxWidth, boxHeight, radius)
        if (fill.a > 0) {
          ctx.fillStyle = `rgba(${fill.r}, ${fill.g}, ${fill.b}, ${fill.a})`
          ctx.fill()
        }
        if (lineWidth > 0 && stroke.a > 0) {
          const inset = lineWidth / 2
          const strokeRadius = Math.max(0, radius - inset)
          drawRoundedRect(ctx, boxLeft + inset, boxTop + inset, boxWidth - (inset * 2), boxHeight - (inset * 2), strokeRadius)
          ctx.strokeStyle = `rgba(${stroke.r}, ${stroke.g}, ${stroke.b}, ${stroke.a})`
          ctx.lineWidth = lineWidth
          ctx.stroke()
        }

        const fontFile = String(item.fontFile || fontDefaults.font || 'Inter-Medium.ttf')
        const { family: normalizedFamily } = normalizeFontFile(fontFile)
        const fontFamily = fontFamilyMap.get(fontFile) || normalizedFamily || 'Inter-Medium'
        const fontSize = Math.max(1, Number(item.fontSize) || fontDefaults.font_size)
        const fontColor = item.fontColor || fontDefaults.font_color
        const strokeWidth = Math.max(0, Number(item.strokeWidth) || 0)
        const strokeColor = item.strokeColor || fontDefaults.stroke_color

        ctx.font = `700 ${fontSize}px "${fontFamily}"`
        if (addonPosition === 'left') {
          const contentX = boxLeft + innerPad
          const contentY = boxTop + innerPad
          const contentW = boxWidth - (innerPad * 2)
          const contentH = boxHeight - (innerPad * 2)
          const iconMaxHeight = Math.max(1, contentH)
          const scale = iconMaxHeight / item.img.height
          const drawW = item.img.width * scale
          const drawH = item.img.height * scale
          const drawX = contentX
          const drawY = contentY + ((contentH - drawH) / 2)
          ctx.drawImage(item.img, drawX, drawY, drawW, drawH)

          const textRegionX = contentX + drawW + addonOffset
          const textRegionW = Math.max(1, (contentX + contentW) - textRegionX)
          const textX = textRegionX + (textRegionW / 2)
          const textY = contentY + (contentH / 2) + (fontSize * 0.35)
          ctx.textAlign = 'center'
          drawTextWithStroke(ctx, item.text, textX, textY, fontColor, strokeColor, strokeWidth)
          ctx.textAlign = 'center'
        } else {
          const textBottom = boxTop + boxHeight - innerPad
          drawTextWithStroke(ctx, item.text, boxLeft + (boxWidth / 2), textBottom, fontColor, strokeColor, strokeWidth)

          const iconMaxHeight = Math.max(1, boxHeight - fontSize - (innerPad * 2))
          const iconMaxWidth = Math.max(1, boxWidth - (innerPad * 2))
          const scale = Math.min(iconMaxWidth / item.img.width, iconMaxHeight / item.img.height)
          const drawW = item.img.width * scale
          const drawH = item.img.height * scale
          const drawX = boxLeft + (boxWidth - drawW) / 2
          const drawY = boxTop + innerPad + ((iconMaxHeight - drawH) / 2)
          ctx.drawImage(item.img, drawX, drawY, drawW, drawH)
        }
      })

      cfg.naturalWidth = canvas.width
      cfg.naturalHeight = canvas.height
      return canvas.toDataURL('image/png')
    }

    const parseHexColor = (value, fallback = { r: 0, g: 0, b: 0, a: 0 }) => {
      if (!value || typeof value !== 'string') return fallback
      const hex = value.trim().replace(/^#/, '')
      if (![3, 4, 6, 8].includes(hex.length)) return fallback
      const expand = (c) => (c.length === 1 ? `${c}${c}` : c)
      let r
      let g
      let b
      let a = 'ff'
      if (hex.length <= 4) {
        r = expand(hex.slice(0, 1))
        g = expand(hex.slice(1, 2))
        b = expand(hex.slice(2, 3))
        if (hex.length === 4) a = expand(hex.slice(3, 4))
      } else {
        r = hex.slice(0, 2)
        g = hex.slice(2, 4)
        b = hex.slice(4, 6)
        if (hex.length === 8) a = hex.slice(6, 8)
      }
      const toInt = (str, def) => {
        const num = parseInt(str, 16)
        return Number.isFinite(num) ? num : def
      }
      return {
        r: toInt(r, fallback.r),
        g: toInt(g, fallback.g),
        b: toInt(b, fallback.b),
        a: toInt(a, Math.round((fallback.a ?? 0) * 255)) / 255
      }
    }

    const drawTextWithStroke = (ctx, text, x, y, fontColor, strokeColor, strokeWidth) => {
      const width = Math.max(0, Number(strokeWidth) || 0)
      if (width > 0) {
        const stroke = parseHexColor(strokeColor, { r: 0, g: 0, b: 0, a: 0 })
        if (stroke.a > 0) {
          ctx.lineWidth = width
          ctx.strokeStyle = `rgba(${stroke.r}, ${stroke.g}, ${stroke.b}, ${stroke.a})`
          ctx.strokeText(text, x, y)
        }
      }
      ctx.fillStyle = fontColor || '#FFFFFFFF'
      ctx.fillText(text, x, y)
    }

    const drawRoundedRect = (ctx, x, y, width, height, radius) => {
      const safeRadius = Math.max(0, Math.min(radius || 0, Math.min(width, height) / 2))
      ctx.beginPath()
      ctx.moveTo(x + safeRadius, y)
      ctx.arcTo(x + width, y, x + width, y + height, safeRadius)
      ctx.arcTo(x + width, y + height, x, y + height, safeRadius)
      ctx.arcTo(x, y + height, x, y, safeRadius)
      ctx.arcTo(x, y, x + width, y, safeRadius)
      ctx.closePath()
    }

    const drawStarShape = (ctx, cx, cy, spikes, outerRadius, innerRadius) => {
      let rot = Math.PI / 2 * 3
      ctx.beginPath()
      ctx.moveTo(cx, cy - outerRadius)
      for (let i = 0; i < spikes; i += 1) {
        let x = cx + Math.cos(rot) * outerRadius
        let y = cy + Math.sin(rot) * outerRadius
        ctx.lineTo(x, y)
        rot += Math.PI / spikes
        x = cx + Math.cos(rot) * innerRadius
        y = cy + Math.sin(rot) * innerRadius
        ctx.lineTo(x, y)
        rot += Math.PI / spikes
      }
      ctx.lineTo(cx, cy - outerRadius)
      ctx.closePath()
      ctx.fillStyle = '#f4b400'
      ctx.strokeStyle = 'rgba(0, 0, 0, 0.35)'
      ctx.lineWidth = Math.max(1, Math.round(outerRadius * 0.08))
      ctx.fill()
      ctx.stroke()
    }

    const loadImage = (src) => {
      if (!src) return Promise.reject(new Error('Missing image src'))
      const cached = imageCache.get(src)
      if (cached) return cached
      const promise = new Promise((resolve, reject) => {
        const img = new Image()
        img.crossOrigin = 'anonymous'
        img.decoding = 'async'
        img.onload = () => resolve(img)
        img.onerror = (err) => reject(err)
        img.src = src
      })
      imageCache.set(src, promise)
      promise.catch(() => imageCache.delete(src))
      return promise
    }

    const buildFlagsCompositeDataUrl = async (cfg) => {
      if (!isFlagsOverlay(cfg)) return null
      const vars = getFlagVars(cfg)
      const backdrop = getBackdropVars(cfg)
      const size = vars.size === 'big' ? 'big' : 'small'
      const fontSize = size === 'big' ? 70 : 50
      const fontFile = vars.font || 'Inter-Bold.ttf'
      const fontFamily = (await ensureRuntimeFontLoaded(fontFile)) || normalizeFontFile(fontFile).family || 'Inter-Bold'
      const align = cfg.id === 'overlay_languages_subtitles' ? 'right' : 'left'
      const hideText = vars.hide_text
      const textCase = vars.use_lowercase
      const useSquareFlags = vars.style === 'square' || vars.style === 'half'
      const groupAlignment = vars.group_alignment === 'horizontal' ? 'horizontal' : 'vertical'

      const baseBoxWidth = size === 'big' ? 216 : 190
      const boxHeight = 60
      const gap = Number(vars.offset) || 10
      const lineWidth = Math.max(0, Number(backdrop.back_line_width) || 0)
      const radius = vars.style === 'square' ? 0 : 26
      const innerPad = 0
      const fill = parseHexColor(backdrop.back_color, { r: 0, g: 0, b: 0, a: 0 })
      const stroke = parseHexColor(backdrop.back_line_color, { r: 0, g: 0, b: 0, a: 0 })

      const items = buildFlagPreviewItems(cfg)
      if (!items.length) return resolveOverlayImage(cfg)
      let images = []
      try {
        images = await Promise.all(
          items.map(item => loadImage(resolveFlagPreviewImage(cfg, item, useSquareFlags)))
        )
      } catch (err) {
        console.warn('[OverlayBoards] Failed to load flag images', err)
        return resolveOverlayImage(cfg)
      }

      const measureCanvas = document.createElement('canvas')
      const measureCtx = measureCanvas.getContext('2d')
      if (!measureCtx) return resolveOverlayImage(cfg)
      measureCtx.font = `${fontSize}px "${fontFamily}"`

      const rows = items.map((item, idx) => {
        const textValue = hideText ? '' : (textCase ? item.text.toLowerCase() : item.text)
        const metrics = textValue
          ? measureCtx.measureText(textValue)
          : { width: 0, actualBoundingBoxAscent: 0, actualBoundingBoxDescent: 0 }
        const textWidth = Number(metrics.width) || 0
        const textAscent = Number(metrics.actualBoundingBoxAscent) || (fontSize * 0.8)
        const textDescent = Number(metrics.actualBoundingBoxDescent) || (fontSize * 0.2)
        const textHeight = textAscent + textDescent

        const img = images[idx]
        const flagW = img.width
        const flagH = img.height

        const rowWidth = hideText ? flagW : baseBoxWidth
        return {
          textValue,
          textWidth,
          textAscent,
          textDescent,
          textHeight,
          flagW,
          flagH,
          rowWidth
        }
      })

      const maxRowWidth = rows.reduce((max, row) => Math.max(max, row.rowWidth), 0)

      const canvas = document.createElement('canvas')
      if (groupAlignment === 'horizontal') {
        const totalWidth = rows.reduce((sum, row) => sum + row.rowWidth, 0)
        canvas.width = Math.ceil(totalWidth)
        canvas.height = Math.ceil(boxHeight)
      } else {
        canvas.width = Math.ceil(maxRowWidth)
        canvas.height = Math.ceil(boxHeight * rows.length)
      }
      const ctx = canvas.getContext('2d')
      if (!ctx) return resolveOverlayImage(cfg)
      ctx.font = `${fontSize}px "${fontFamily}"`
      ctx.textAlign = align === 'right' ? 'right' : 'left'
      ctx.textBaseline = 'alphabetic'

      let runningX = 0
      rows.forEach((row, idx) => {
        const boxWidth = row.rowWidth
        const boxX = groupAlignment === 'horizontal' ? runningX : 0
        const boxY = groupAlignment === 'horizontal' ? 0 : (boxHeight * idx)

        drawRoundedRect(ctx, boxX, boxY, boxWidth, boxHeight, radius)
        if (fill.a > 0) {
          ctx.fillStyle = `rgba(${fill.r}, ${fill.g}, ${fill.b}, ${fill.a})`
          ctx.fill()
        }
        if (lineWidth > 0 && stroke.a > 0) {
          const inset = lineWidth / 2
          const strokeRadius = Math.max(0, radius - inset)
          drawRoundedRect(ctx, boxX + inset, boxY + inset, boxWidth - (inset * 2), boxHeight - (inset * 2), strokeRadius)
          ctx.strokeStyle = `rgba(${stroke.r}, ${stroke.g}, ${stroke.b}, ${stroke.a})`
          ctx.lineWidth = lineWidth
          ctx.stroke()
        }

        const img = images[idx]
        const centerY = boxY + (boxHeight / 2)
        const textValue = row.textValue
        const flagX = align === 'right'
          ? (boxX + boxWidth - innerPad - row.flagW)
          : (boxX + innerPad)

        const flagY = centerY - (row.flagH / 2)
        ctx.drawImage(img, flagX, flagY, row.flagW, row.flagH)

        if (textValue) {
          const textX = align === 'right'
            ? (flagX - gap)
            : (flagX + row.flagW + gap)
          const textTop = boxY + ((boxHeight - row.textHeight) / 2)
          const textY = textTop + row.textAscent
          const fontColor = parseHexColor(vars.font_color, { r: 255, g: 255, b: 255, a: 1 })
          const fontColorCss = `rgba(${fontColor.r}, ${fontColor.g}, ${fontColor.b}, ${fontColor.a})`
          drawTextWithStroke(ctx, textValue, textX, textY, fontColorCss, vars.stroke_color, vars.stroke_width)
        }

        if (groupAlignment === 'horizontal') {
          runningX += boxWidth
        }
      })

      cfg.naturalWidth = canvas.width
      cfg.naturalHeight = canvas.height
      return canvas.toDataURL('image/png')
    }

    const buildResolutionCompositeDataUrl = async (cfg) => {
      if (cfg.id !== 'overlay_resolution') return null

      const payload = getResolutionRenderPayload(cfg)
      if (!payload.use_resolution && !payload.use_edition) {
        return resolveOverlayImage(cfg)
      }

      try {
        const response = await fetch('/overlay-render-preview', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        })
        if (!response.ok) {
          let message = `HTTP ${response.status}`
          try {
            const errorPayload = await response.json()
            message = errorPayload?.message || errorPayload?.error || message
          } catch {
            // ignore JSON parse failure and keep HTTP message
          }
          throw new Error(message)
        }
        const blob = await response.blob()
        return await blobToDataUrl(blob)
      } catch (err) {
        console.warn('[OverlayBoards] Failed to build server-rendered resolution preview', err)
        return payload.use_resolution
          ? (resolveResolutionPreviewImage(cfg, 'resolution') || resolveOverlayImage(cfg))
          : (resolveResolutionPreviewImage(cfg, 'edition') || cfg.edition?.image || resolveOverlayImage(cfg))
      }
    }

    const buildAudioCodecCompositeDataUrl = async (cfg) => {
      if (cfg.id !== 'overlay_audio_codec') return null

      const payload = getAudioCodecRenderPayload(cfg)
      try {
        const response = await fetch('/overlay-render-preview', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        })
        if (!response.ok) {
          let message = `HTTP ${response.status}`
          try {
            const errorPayload = await response.json()
            message = errorPayload?.message || errorPayload?.error || message
          } catch {
            // ignore JSON parse failure and keep HTTP message
          }
          throw new Error(message)
        }
        const blob = await response.blob()
        return await blobToDataUrl(blob)
      } catch (err) {
        console.warn('[OverlayBoards] Failed to build server-rendered audio codec preview', err)
        const badgeKey = getAudioCodecPreviewSelectedKey(cfg)
        const overrideEntry = getAudioCodecPreviewOverrideEntries(cfg).find(entry => {
          return entry.badgeKey === badgeKey && entry.sourceType && entry.value
        })
        if (overrideEntry) {
          return buildOverlaySourcePreviewUrl(overrideEntry.sourceType, overrideEntry.value)
        }
        return buildBundledOverlayPreviewUrl('audio_codec', badgeKey, getAudioCodecStyle(cfg)) || resolveOverlayImage(cfg)
      }
    }

    const buildStreamingCompositeDataUrl = async (cfg) => {
      if (cfg.id !== 'overlay_streaming') return null

      const payload = getStreamingRenderPayload(cfg)
      try {
        const response = await fetch('/overlay-render-preview', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        })
        if (!response.ok) {
          let message = `HTTP ${response.status}`
          try {
            const errorPayload = await response.json()
            message = errorPayload?.message || errorPayload?.error || message
          } catch {
            // ignore JSON parse failure and keep HTTP message
          }
          throw new Error(message)
        }
        const blob = await response.blob()
        return await blobToDataUrl(blob)
      } catch (err) {
        console.warn('[OverlayBoards] Failed to build server-rendered streaming preview', err)
        const badgeKey = getStreamingPreviewSelectedKey(cfg)
        const overrideEntry = getStreamingPreviewOverrideEntries(cfg).find(entry => {
          return entry.badgeKey === badgeKey && entry.sourceType && entry.value
        })
        if (overrideEntry) {
          return buildOverlaySourcePreviewUrl(overrideEntry.sourceType, overrideEntry.value)
        }
        return buildBundledOverlayPreviewUrl('streaming', badgeKey, getStreamingStyle(cfg)) || resolveOverlayImage(cfg)
      }
    }

    const buildRibbonCompositeDataUrl = async (cfg) => {
      if (cfg.id !== 'overlay_ribbon') return null

      const payload = getRibbonRenderPayload(cfg)
      try {
        const response = await fetch('/overlay-render-preview', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        })
        if (!response.ok) {
          let message = `HTTP ${response.status}`
          try {
            const errorPayload = await response.json()
            message = errorPayload?.message || errorPayload?.error || message
          } catch {
          }
          throw new Error(message)
        }
        const blob = await response.blob()
        return await blobToDataUrl(blob)
      } catch (err) {
        console.warn('[OverlayBoards] Failed to build server-rendered ribbon preview', err)
        const badgeKey = getRibbonPreviewSelectedKey(cfg)
        const overrideEntry = getRibbonPreviewOverrideEntries(cfg).find(entry => {
          return entry.badgeKey === badgeKey && entry.sourceType && entry.value
        })
        if (overrideEntry) {
          return buildOverlaySourcePreviewUrl(overrideEntry.sourceType, overrideEntry.value)
        }
        return buildBundledOverlayPreviewUrl('ribbon', badgeKey, getRibbonStyle(cfg)) || resolveOverlayImage(cfg)
      }
    }

    const buildLanguageCountCompositeDataUrl = async (cfg) => {
      if (cfg.id !== 'overlay_language_count') return null

      const payload = getLanguageCountRenderPayload(cfg)
      try {
        const response = await fetch('/overlay-render-preview', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        })
        if (!response.ok) {
          let message = `HTTP ${response.status}`
          try {
            const errorPayload = await response.json()
            message = errorPayload?.message || errorPayload?.error || message
          } catch {
          }
          throw new Error(message)
        }
        const blob = await response.blob()
        return await blobToDataUrl(blob)
      } catch (err) {
        console.warn('[OverlayBoards] Failed to build server-rendered language count preview', err)
        const badgeKey = getLanguageCountPreviewSelectedKey(cfg)
        const overrideEntry = getLanguageCountPreviewOverrideEntries(cfg).find(entry => {
          return entry.badgeKey === badgeKey && entry.sourceType && entry.value
        })
        if (overrideEntry) {
          return buildOverlaySourcePreviewUrl(overrideEntry.sourceType, overrideEntry.value)
        }
        return buildBundledOverlayPreviewUrl('language_count', badgeKey, getLanguageCountVariant(cfg)) || resolveOverlayImage(cfg)
      }
    }

    const buildNetworkCompositeDataUrl = async (cfg) => {
      if (cfg.id !== 'overlay_network') return null

      const payload = getSingleBadgeOverlayRenderPayload(cfg, 'network', getNetworkStyle)
      try {
        const response = await fetch('/overlay-render-preview', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        })
        if (!response.ok) {
          let message = `HTTP ${response.status}`
          try {
            const errorPayload = await response.json()
            message = errorPayload?.message || errorPayload?.error || message
          } catch {
          }
          throw new Error(message)
        }
        const blob = await response.blob()
        return await blobToDataUrl(blob)
      } catch (err) {
        console.warn('[OverlayBoards] Failed to build server-rendered network preview', err)
        const badgeKey = getSingleBadgeOverlayPreviewSelectedKey(cfg)
        const overrideEntry = getSingleBadgeOverlayPreviewOverrideEntries(cfg).find(entry => {
          return entry.badgeKey === badgeKey && entry.sourceType && entry.value
        })
        if (overrideEntry) {
          return buildOverlaySourcePreviewUrl(overrideEntry.sourceType, overrideEntry.value)
        }
        return buildBundledOverlayPreviewUrl('network', badgeKey, getNetworkStyle(cfg)) || resolveOverlayImage(cfg)
      }
    }

    const buildStudioCompositeDataUrl = async (cfg) => {
      if (cfg.id !== 'overlay_studio') return null

      const payload = getSingleBadgeOverlayRenderPayload(cfg, 'studio', getStudioStyle)
      try {
        const response = await fetch('/overlay-render-preview', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        })
        if (!response.ok) {
          let message = `HTTP ${response.status}`
          try {
            const errorPayload = await response.json()
            message = errorPayload?.message || errorPayload?.error || message
          } catch {
          }
          throw new Error(message)
        }
        const blob = await response.blob()
        return await blobToDataUrl(blob)
      } catch (err) {
        console.warn('[OverlayBoards] Failed to build server-rendered studio preview', err)
        const badgeKey = getSingleBadgeOverlayPreviewSelectedKey(cfg)
        const overrideEntry = getSingleBadgeOverlayPreviewOverrideEntries(cfg).find(entry => {
          return entry.badgeKey === badgeKey && entry.sourceType && entry.value
        })
        if (overrideEntry) {
          return buildOverlaySourcePreviewUrl(overrideEntry.sourceType, overrideEntry.value)
        }
        return buildBundledOverlayPreviewUrl('studio', badgeKey, getStudioStyle(cfg)) || resolveOverlayImage(cfg)
      }
    }

    const buildFixedBadgeCompositeDataUrl = async (cfg) => {
      const family = getFixedBadgeOverlayFamily(cfg)
      if (!family) return null

      const payload = getFixedBadgeOverlayRenderPayload(cfg)
      try {
        const response = await fetch('/overlay-render-preview', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        })
        if (!response.ok) {
          let message = `HTTP ${response.status}`
          try {
            const errorPayload = await response.json()
            message = errorPayload?.message || errorPayload?.error || message
          } catch {
          }
          throw new Error(message)
        }
        const blob = await response.blob()
        return await blobToDataUrl(blob)
      } catch (err) {
        console.warn('[OverlayBoards] Failed to build server-rendered fixed badge preview', { family, err })
        const badgeKey = getFixedBadgeOverlayKey(cfg)
        const overrideEntry = getFixedBadgeOverlayPreviewOverrideEntries(cfg).find(entry => {
          return entry.badgeKey === badgeKey && entry.sourceType && entry.value
        })
        if (overrideEntry) {
          return buildOverlaySourcePreviewUrl(overrideEntry.sourceType, overrideEntry.value)
        }
        return buildBundledOverlayPreviewUrl(family, badgeKey) || resolveOverlayImage(cfg)
      }
    }

    const buildBackdropDataUrl = async (cfg, baseOverride = null) => {
      const vars = getBackdropVars(cfg)
      const pad = Math.max(0, Number(vars.back_padding) || 0)
      const backWidth = Number(vars.back_width) || 0
      const backHeight = Number(vars.back_height) || 0
      const radius = Math.max(0, Number(vars.back_radius) || 0)
      const lineWidth = Math.max(0, Number(vars.back_line_width) || 0)

      let baseImg = baseOverride || resolveOverlayImage(cfg)
      if (!baseOverride && cfg.id === 'overlay_resolution') {
        const composite = await buildResolutionCompositeDataUrl(cfg)
        if (composite) baseImg = composite
      }
      if (!baseOverride && cfg.id === 'overlay_audio_codec') {
        const composite = await buildAudioCodecCompositeDataUrl(cfg)
        if (composite) baseImg = composite
      }
      if (!baseOverride && cfg.id === 'overlay_streaming') {
        const composite = await buildStreamingCompositeDataUrl(cfg)
        if (composite) baseImg = composite
      }
      if (!baseOverride && cfg.id === 'overlay_ribbon') {
        const composite = await buildRibbonCompositeDataUrl(cfg)
        if (composite) baseImg = composite
      }
      if (!baseOverride && cfg.id === 'overlay_language_count') {
        const composite = await buildLanguageCountCompositeDataUrl(cfg)
        if (composite) baseImg = composite
      }
      if (!baseOverride && (isRegionalContentRatingOverlay(cfg) || isCommonsenseContentRatingOverlay(cfg))) {
        const composite = await resolveContentRatingPreviewImage(cfg)
        if (composite) baseImg = composite
      }
      if (!baseOverride && cfg.id === 'overlay_network') {
        const composite = await buildNetworkCompositeDataUrl(cfg)
        if (composite) baseImg = composite
      }
      if (!baseOverride && cfg.id === 'overlay_studio') {
        const composite = await buildStudioCompositeDataUrl(cfg)
        if (composite) baseImg = composite
      }
      if (!baseOverride && getFixedBadgeOverlayFamily(cfg)) {
        const composite = await buildFixedBadgeCompositeDataUrl(cfg)
        if (composite) baseImg = composite
      }
      if (!baseOverride && cfg.id === 'overlay_ratings') {
        const composite = await buildRatingsCompositeDataUrl(cfg)
        if (composite) baseImg = composite
      }
      if (cfg.id === 'overlay_ratings') {
        return baseImg
      }
      let img
      try {
        img = await loadImage(baseImg)
      } catch (err) {
        console.warn('[OverlayBoards] Failed to load overlay image', err)
        return baseImg
      }

      const contentWidth = img.width + pad * 2
      const contentHeight = img.height + pad * 2
      const canvasWidth = backWidth > 0 ? Math.max(backWidth, contentWidth) : contentWidth
      const canvasHeight = backHeight > 0 ? Math.max(backHeight, contentHeight) : contentHeight

      const canvas = document.createElement('canvas')
      canvas.width = Math.ceil(canvasWidth)
      canvas.height = Math.ceil(canvasHeight)
      const ctx = canvas.getContext('2d')
      if (!ctx) return baseImg

      const fill = parseHexColor(vars.back_color, { r: 0, g: 0, b: 0, a: 0 })
      const stroke = parseHexColor(vars.back_line_color, { r: 0, g: 0, b: 0, a: 0 })

      drawRoundedRect(ctx, 0, 0, canvasWidth, canvasHeight, radius)
      if (fill.a > 0) {
        ctx.fillStyle = `rgba(${fill.r}, ${fill.g}, ${fill.b}, ${fill.a})`
        ctx.fill()
      }
      if (lineWidth > 0 && stroke.a > 0) {
        const inset = lineWidth / 2
        const strokeRadius = Math.max(0, radius - inset)
        drawRoundedRect(ctx, inset, inset, canvasWidth - (inset * 2), canvasHeight - (inset * 2), strokeRadius)
        ctx.strokeStyle = `rgba(${stroke.r}, ${stroke.g}, ${stroke.b}, ${stroke.a})`
        ctx.lineWidth = lineWidth
        ctx.stroke()
      }

      const align = vars.back_align
      const centerX = (canvasWidth - img.width) / 2
      const centerY = (canvasHeight - img.height) / 2
      let drawX = centerX
      let drawY = centerY
      if (align === 'left') {
        drawX = pad
        drawY = centerY
      } else if (align === 'right') {
        drawX = canvasWidth - img.width - pad
        drawY = centerY
      } else if (align === 'top') {
        drawX = centerX
        drawY = pad
      } else if (align === 'bottom') {
        drawX = centerX
        drawY = canvasHeight - img.height - pad
      }
      drawX = Math.max(pad, Math.min(drawX, canvasWidth - img.width - pad))
      drawY = Math.max(pad, Math.min(drawY, canvasHeight - img.height - pad))
      ctx.drawImage(img, drawX, drawY)

      cfg.naturalWidth = canvas.width
      cfg.naturalHeight = canvas.height
      return canvas.toDataURL('image/png')
    }

    const buildCommonsenseDataUrl = async (cfg, baseOverride = null) => {
      const container = cfg.container
      const templateName = container?.dataset.overlayTemplate
      const getVal = (key, defaultVal) => {
        if (!container || !templateName) return defaultVal
        const el = container.querySelector(`[name="${templateName}[${key}]"]`)
        if (!el) return defaultVal
        if (el.type === 'number') {
          const n = Number(el.value)
          return Number.isFinite(n) ? n : defaultVal
        }
        return el.value || defaultVal
      }

      const baseImg = baseOverride || cfg.image
      const textVal = normalizeCommonsensePreviewText(getVal('text', 17))
      const postText = getVal('post_text', '+')
      const addonOffset = getVal('addon_offset', 15)
      const font = getVal('font', 'Inter-Medium.ttf')
      const fontSize = getVal('font_size', 55)
      const fontColor = getVal('font_color', '#FFFFFFFF')
      const strokeWidth = getVal('stroke_width', 1)
      const strokeColor = getVal('stroke_color', '#00000000')

      const fontFamily = (await ensureRuntimeFontLoaded(font)) || normalizeFontFile(font).family || 'Inter-Medium'

      const img = await loadImage(baseImg)
      const canvas = document.createElement('canvas')
      const ctx = canvas.getContext('2d')
      ctx.font = `${fontSize}px "${fontFamily}"`
      const effectivePostText = textVal === 'NR' ? '' : postText
      const textString = `${textVal}${effectivePostText || ''}`
      const textBox = getTextBoxMetrics(ctx, textString, fontSize, 10, strokeWidth)

      canvas.width = img.width + addonOffset + textBox.width
      canvas.height = Math.max(img.height, textBox.height)

      ctx.drawImage(img, 0, 0)
      ctx.font = `${fontSize}px "${fontFamily}"`
      ctx.textAlign = 'left'
      ctx.textBaseline = 'alphabetic'
      const textTop = Math.max(0, Math.round((canvas.height - textBox.height) / 2))
      const textX = img.width + addonOffset + textBox.pad + textBox.left
      const textY = textTop + textBox.pad + textBox.ascent
      drawTextWithStroke(ctx, textString, textX, textY, fontColor, strokeColor, strokeWidth)

      return canvas.toDataURL('image/png')
    }

    const buildRuntimeDataUrl = (cfg, loadedFamily = null) => {
      const { text, format, font, font_size: fontSize, font_color: fontColor, stroke_width: strokeWidth, stroke_color: strokeColor } = getRuntimeVars(cfg)
      const { family: normalizedFamily } = normalizeFontFile(font)
      const runtimeMinutes = Number(getOverlayTextPreviewSelectedValue(cfg) || 93) || 93
      const runtimeH = Math.floor(runtimeMinutes / 60)
      const runtimeM = runtimeMinutes % 60
      const rendered = format
        .replace(/<<runtimeH>>/gi, runtimeH)
        .replace(/<<runtimeM>>/gi, runtimeM)
        .replace(/<<runtime_total>>/gi, runtimeMinutes)
        .replace(/<<runtime>>/gi, runtimeMinutes)
      const fullText = `${text}${rendered}`

      // Measure text first to keep the overlay small (so it doesn't block dragging other overlays)
      const measureCanvas = document.createElement('canvas')
      const measureCtx = measureCanvas.getContext('2d')
      if (!measureCtx) return cfg.image
      measureCtx.font = `${fontSize || 55}px "${loadedFamily || normalizedFamily || 'Inter'}"`
      const textBox = getTextBoxMetrics(measureCtx, fullText, fontSize, 10, strokeWidth)
      const canvasWidth = textBox.width
      const canvasHeight = textBox.height

      const canvas = document.createElement('canvas')
      canvas.width = canvasWidth
      canvas.height = canvasHeight
      const ctx = canvas.getContext('2d')
      if (!ctx) return cfg.image

      ctx.clearRect(0, 0, canvas.width, canvas.height)
      const family = loadedFamily || normalizedFamily || 'Inter'
      ctx.font = `${fontSize || 55}px "${family}"`
      ctx.textAlign = 'left'
      ctx.textBaseline = 'alphabetic'
      drawTextWithStroke(ctx, fullText, textBox.pad + textBox.left, textBox.pad + textBox.ascent, fontColor || '#FFFFFF', strokeColor, strokeWidth)

      // Store natural size so dragging/clamping respects the smaller overlay
      cfg.naturalWidth = canvasWidth
      cfg.naturalHeight = canvasHeight

      return canvas.toDataURL('image/png')
    }

    const buildSimpleTextDataUrl = (cfg, vars, loadedFamily = null) => {
      const { text, font, font_size: fontSize, font_color: fontColor, stroke_width: strokeWidth, stroke_color: strokeColor } = vars
      const { family: normalizedFamily } = normalizeFontFile(font)
      const content = text || ''

      const measureCanvas = document.createElement('canvas')
      const measureCtx = measureCanvas.getContext('2d')
      if (!measureCtx) return cfg.image
      measureCtx.font = `${fontSize || 55}px "${loadedFamily || normalizedFamily || 'Inter'}"`
      const textBox = getTextBoxMetrics(measureCtx, content, fontSize, 10, strokeWidth)
      const canvasWidth = textBox.width
      const canvasHeight = textBox.height

      const canvas = document.createElement('canvas')
      canvas.width = canvasWidth
      canvas.height = canvasHeight
      const ctx = canvas.getContext('2d')
      if (!ctx) return cfg.image

      ctx.clearRect(0, 0, canvas.width, canvas.height)
      const family = loadedFamily || normalizedFamily || 'Inter'
      ctx.font = `${fontSize || 55}px "${family}"`
      ctx.textAlign = 'left'
      ctx.textBaseline = 'alphabetic'
      drawTextWithStroke(ctx, content, textBox.pad + textBox.left, textBox.pad + textBox.ascent, fontColor || '#FFFFFFFF', strokeColor, strokeWidth)

      cfg.naturalWidth = canvasWidth
      cfg.naturalHeight = canvasHeight
      return canvas.toDataURL('image/png')
    }

    const openAccordionAncestors = (target) => {
      if (!target) return
      const collapses = []
      let node = target
      while (node) {
        if (node.classList && node.classList.contains('accordion-collapse')) {
          collapses.push(node)
        }
        node = node.parentElement
      }
      collapses.reverse().forEach(collapse => {
        if (collapse.classList.contains('show')) return
        if (window.bootstrap && window.bootstrap.Collapse) {
          const instance = window.bootstrap.Collapse.getOrCreateInstance(collapse, { toggle: false })
          instance.show()
          return
        }
        const headerBtn = collapse.closest('.accordion-item')?.querySelector('.accordion-header .accordion-button')
        headerBtn?.click()
      })
    }

    const highlightJumpTarget = (target) => {
      if (!target) return
      document.querySelectorAll('.overlay-config-target.is-jump-highlight').forEach(node => {
        if (node !== target) node.classList.remove('is-jump-highlight')
      })
      target.classList.add('is-jump-highlight')
      window.setTimeout(() => {
        target.classList.remove('is-jump-highlight')
      }, 1600)
    }

    Array.from(root.querySelectorAll('.overlay-board')).forEach(board => {
      if (board.dataset.boardBound === 'true') return
      board.dataset.boardBound = 'true'

      const canvas = board.querySelector('.overlay-board-canvas')
      if (!canvas) return

      const baseWidth = Number(board.dataset.baseWidth) || defaultDims.default.width
      const baseHeight = Number(board.dataset.baseHeight) || defaultDims.default.height
      const libId = board.dataset.libraryId || ''
      const overlayType = board.dataset.overlayType || ''
      board.classList.toggle('overlay-board--landscape', baseWidth > baseHeight)
      const ratio = baseWidth / baseHeight
      board.style.setProperty('--overlay-board-ratio', `${ratio}`)
      canvas.style.setProperty('--overlay-board-ratio', `${ratio}`)

      const layers = new Map()
      const configsById = new Map()
      let writing = false

      const clamp = (val, min, max) => Math.min(Math.max(val, min), max)
      const ensureNumber = (val, fallback = 0) => {
        const num = Number(val)
        return Number.isFinite(num) ? num : fallback
      }

      const viewport = board.querySelector('.overlay-board-viewport') || canvas
      const toolbar = board.querySelector('.overlay-board-toolbar') ||
        document.querySelector(`.overlay-board-toolbar[data-overlay-board-toolbar][data-library-id="${libId}"][data-overlay-type="${overlayType}"]`)
      const zoomLabel = toolbar?.querySelector('[data-overlay-board-zoom-label]')
      const zoomInBtn = toolbar?.querySelector('[data-overlay-board-zoom="in"]')
      const zoomOutBtn = toolbar?.querySelector('[data-overlay-board-zoom="out"]')
      const zoomResetBtn = toolbar?.querySelector('[data-overlay-board-zoom="reset"]')
      const panToggleBtn = toolbar?.querySelector('[data-overlay-board-toggle="pan"]')
      const gridToggleBtn = toolbar?.querySelector('[data-overlay-board-toggle="grid"]')
      const snapToggleBtn = toolbar?.querySelector('[data-overlay-board-toggle="snap"]')
      const multiSelectToggleBtn = toolbar?.querySelector('[data-overlay-board-toggle="multi"]')
      const snapStepSelect = toolbar?.querySelector('[data-overlay-board-snap-step]')
      const undoBtn = toolbar?.querySelector('[data-overlay-board-history="undo"]')
      const redoBtn = toolbar?.querySelector('[data-overlay-board-history="redo"]')
      const resetPosBtn = toolbar?.querySelector('[data-overlay-board-reset="position"]')
      const nudgeStepSelect = toolbar?.querySelector('[data-overlay-board-nudge-step]')
      const nudgeButtons = toolbar?.querySelectorAll('[data-overlay-board-nudge]') || []
      const alignButtons = toolbar?.querySelectorAll('[data-overlay-board-align]') || []
      const distributeButtons = toolbar?.querySelectorAll('[data-overlay-board-distribute]') || []
      const exportBtn = toolbar?.querySelector('[data-overlay-board-export]')
      const jumpToSettingsBtn = toolbar?.querySelector('[data-overlay-board-jump="config"]')

      const initialGridSize = Number(snapStepSelect?.value) || 25
      board.style.setProperty('--overlay-grid-size', `${initialGridSize}px`)

      const boardState = {
        zoom: 1,
        panX: 0,
        panY: 0,
        gridEnabled: false,
        snapEnabled: false,
        panEnabled: false,
        gridSize: initialGridSize,
        activeLayer: null,
        selectedLayers: new Set(),
        multiSelectEnabled: false,
        history: [],
        historyIndex: -1,
        historyLimit: 100,
        historyLocked: false
      }

      const getActiveLayer = () => boardState.activeLayer || boardState.selectedLayers.values().next().value || null
      const getJumpTargetId = (overlayId) => {
        if (!overlayId) return ''
        const cfg = configsById.get(overlayId)
        if (cfg?.container?.id) return cfg.container.id
        return `${libId}-${overlayType}-${overlayId}-overlay-config`
      }

      const updateJumpButton = () => {
        if (!jumpToSettingsBtn) return
        const activeLayer = getActiveLayer()
        const isEdition = activeLayer?.dataset?.overlayEdition === 'true'
        const overlayId = isEdition ? activeLayer?.dataset?.overlayParentId : activeLayer?.dataset?.overlayId
        const targetId = getJumpTargetId(overlayId)
        if (!targetId) {
          jumpToSettingsBtn.disabled = true
          jumpToSettingsBtn.dataset.jumpTarget = ''
          jumpToSettingsBtn.title = 'Select an overlay on the canvas to jump to its settings'
          return
        }
        jumpToSettingsBtn.disabled = false
        jumpToSettingsBtn.dataset.jumpTarget = targetId
        jumpToSettingsBtn.title = 'Jump to selected overlay settings'
      }

      let recalcAll = () => {}

      if (jumpToSettingsBtn) {
        jumpToSettingsBtn.addEventListener('click', () => {
          const targetId = jumpToSettingsBtn.dataset.jumpTarget
          if (!targetId) return
          const target = document.getElementById(targetId)
          if (!target) return

          const performJump = () => {
            openAccordionAncestors(target)
            window.setTimeout(() => {
              target.scrollIntoView({ behavior: 'smooth', block: 'start' })
              highlightJumpTarget(target)
            }, 150)
          }

          if (board.classList.contains('overlay-board--modal')) {
            const modalEl = board.closest('.modal')
            if (modalEl && window.bootstrap && window.bootstrap.Modal) {
              modalEl.addEventListener('hidden.bs.modal', () => {
                performJump()
              }, { once: true })
              const modalInstance = window.bootstrap.Modal.getOrCreateInstance(modalEl)
              modalInstance.hide()
              return
            }
          }
          performJump()
        })
      }
      updateJumpButton()

      const setToggleState = (btn, active) => {
        if (!btn) return
        btn.classList.toggle('is-active', active)
        btn.setAttribute('aria-pressed', active ? 'true' : 'false')
      }

      const applyBoardTransform = () => {
        canvas.style.transform = `translate(${boardState.panX}px, ${boardState.panY}px) scale(${boardState.zoom})`
      }

      const updateZoomLabel = () => {
        if (zoomLabel) zoomLabel.textContent = `${Math.round(boardState.zoom * 100)}%`
      }

      const setLayerSelected = (layer, selected) => {
        if (!layer) return
        if (selected) {
          boardState.selectedLayers.add(layer)
          layer.classList.add('is-selected')
          return
        }
        boardState.selectedLayers.delete(layer)
        layer.classList.remove('is-selected')
      }

      const clearSelection = () => {
        boardState.selectedLayers.forEach(layer => {
          layer.classList.remove('is-selected')
        })
        boardState.selectedLayers.clear()
        if (boardState.activeLayer) {
          boardState.activeLayer.classList.remove('is-active')
        }
        boardState.activeLayer = null
        updateJumpButton()
      }

      const setActiveLayer = (layer) => {
        if (boardState.activeLayer === layer) return
        canvas.querySelectorAll('.overlay-board-layer.is-active').forEach(node => {
          if (node !== layer) node.classList.remove('is-active')
        })
        boardState.activeLayer = layer || null
        if (layer) {
          layer.classList.add('is-active')
          if (!boardState.selectedLayers.has(layer)) {
            setLayerSelected(layer, true)
          }
        }
        updateJumpButton()
      }

      const selectLayerById = (overlayId) => {
        if (!overlayId) return false
        const layer = layers.get(overlayId)
        if (!layer) return false
        clearSelection()
        setActiveLayer(layer)
        return true
      }

      board._overlaySelectById = selectLayerById

      const getSnapshot = () => {
        const snapshot = {}
        configsById.forEach((cfg, id) => {
          const { hInput, vInput } = getInputs(cfg)
          if (!hInput || !vInput) return
          snapshot[id] = {
            h: ensureNumber(hInput.value, 0),
            v: ensureNumber(vInput.value, 0)
          }
        })
        return snapshot
      }

      const snapshotsEqual = (a, b) => {
        if (!a || !b) return false
        const aKeys = Object.keys(a)
        const bKeys = Object.keys(b)
        if (aKeys.length !== bKeys.length) return false
        for (const key of aKeys) {
          const aVal = a[key]
          const bVal = b[key]
          if (!bVal || aVal.h !== bVal.h || aVal.v !== bVal.v) return false
        }
        return true
      }

      const updateHistoryButtons = () => {
        if (undoBtn) undoBtn.disabled = boardState.historyIndex <= 0
        if (redoBtn) redoBtn.disabled = boardState.historyIndex >= boardState.history.length - 1
      }

      const recordHistory = () => {
        if (boardState.historyLocked) return
        const snapshot = getSnapshot()
        if (boardState.historyIndex >= 0) {
          const current = boardState.history[boardState.historyIndex]
          if (snapshotsEqual(current, snapshot)) {
            updateHistoryButtons()
            return
          }
        }
        if (boardState.historyIndex < boardState.history.length - 1) {
          boardState.history.splice(boardState.historyIndex + 1)
        }
        boardState.history.push(snapshot)
        if (boardState.history.length > boardState.historyLimit) {
          boardState.history.shift()
        }
        boardState.historyIndex = boardState.history.length - 1
        updateHistoryButtons()
      }

      const applySnapshot = (snapshot) => {
        if (!snapshot) return
        boardState.historyLocked = true
        writing = true
        configsById.forEach((cfg, id) => {
          const entry = snapshot[id]
          if (!entry) return
          const { hInput, vInput } = getInputs(cfg)
          if (!hInput || !vInput) return
          hInput.value = entry.h
          vInput.value = entry.v
        })
        writing = false
        boardState.historyLocked = false
        configsById.forEach(cfg => {
          applyPosition(cfg)
          applyEditionPosition(cfg)
        })
        updateHistoryButtons()
      }

      const getBackgroundUrl = () => {
        const style = window.getComputedStyle(canvas)
        const bg = style.backgroundImage || ''
        if (!bg || bg === 'none') return null
        const match = bg.match(/url\(["']?(.*?)["']?\)/i)
        return match ? match[1] : null
      }

      const drawCoverImage = (ctx, img, width, height) => {
        if (!img || !img.width || !img.height) return
        const scale = Math.max(width / img.width, height / img.height)
        const drawW = img.width * scale
        const drawH = img.height * scale
        const drawX = (width - drawW) / 2
        const drawY = (height - drawH) / 2
        ctx.drawImage(img, drawX, drawY, drawW, drawH)
      }

      const exportBoardImage = async () => {
        if (exportBtn) exportBtn.disabled = true
        try {
          const exportCanvas = document.createElement('canvas')
          exportCanvas.width = Math.round(baseWidth)
          exportCanvas.height = Math.round(baseHeight)
          const ctx = exportCanvas.getContext('2d')
          if (!ctx) return

          ctx.fillStyle = '#0f0f0f'
          ctx.fillRect(0, 0, exportCanvas.width, exportCanvas.height)

          const bgUrl = getBackgroundUrl()
          if (bgUrl) {
            const bgImg = await loadImage(bgUrl)
            drawCoverImage(ctx, bgImg, exportCanvas.width, exportCanvas.height)
          }

          const { scaleX, scaleY } = getScale()
          const layerNodes = Array.from(canvas.querySelectorAll('.overlay-board-layer'))
          for (const layer of layerNodes) {
            const style = window.getComputedStyle(layer)
            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue
            const src = layer.currentSrc || layer.src
            if (!src) continue
            const img = await loadImage(src)
            const leftPx = parseFloat(layer.style.left) || 0
            const topPx = parseFloat(layer.style.top) || 0
            const widthPx = parseFloat(layer.style.width) || img.width
            const heightPx = parseFloat(layer.style.height) || img.height
            const x = leftPx / scaleX
            const y = topPx / scaleY
            const w = widthPx / scaleX
            const h = heightPx / scaleY
            ctx.drawImage(img, x, y, w, h)
          }

          const dataUrl = exportCanvas.toDataURL('image/png')
          const link = document.createElement('a')
          link.href = dataUrl
          link.download = `overlay-${libId}-${overlayType}.png`
          document.body.appendChild(link)
          link.click()
          link.remove()
        } catch (err) {
          console.warn('[OverlayBoards] Export failed', err)
        } finally {
          if (exportBtn) exportBtn.disabled = false
        }
      }

      const setZoom = (value) => {
        boardState.zoom = clamp(value, 0.5, 6)
        applyBoardTransform()
        updateZoomLabel()
        recalcAll()
      }

      const snapToGrid = (value, maxVal) => {
        if (!boardState.snapEnabled) return value
        const step = boardState.gridSize || 25
        const snapped = Math.round(value / step) * step
        const threshold = Math.max(2, Math.round(step * 0.24))
        const within = Math.abs(snapped - value) <= threshold
        return within ? clamp(snapped, 0, maxVal) : value
      }

      if (zoomInBtn) {
        zoomInBtn.addEventListener('click', () => setZoom(boardState.zoom + 0.1))
      }
      if (zoomOutBtn) {
        zoomOutBtn.addEventListener('click', () => setZoom(boardState.zoom - 0.1))
      }
      if (zoomResetBtn) {
        zoomResetBtn.addEventListener('click', () => {
          boardState.panX = 0
          boardState.panY = 0
          setZoom(1)
          applyBoardTransform()
        })
      }

      if (panToggleBtn) {
        panToggleBtn.addEventListener('click', () => {
          boardState.panEnabled = !boardState.panEnabled
          board.classList.toggle('overlay-board--pan', boardState.panEnabled)
          setToggleState(panToggleBtn, boardState.panEnabled)
        })
      }

      if (gridToggleBtn) {
        gridToggleBtn.addEventListener('click', () => {
          boardState.gridEnabled = !boardState.gridEnabled
          board.classList.toggle('overlay-board--grid', boardState.gridEnabled)
          setToggleState(gridToggleBtn, boardState.gridEnabled)
        })
      }

      if (snapStepSelect) {
        snapStepSelect.addEventListener('change', () => {
          const nextSize = Math.max(1, Number(snapStepSelect.value) || 25)
          boardState.gridSize = nextSize
          board.style.setProperty('--overlay-grid-size', `${nextSize}px`)
        })
      }

      if (snapToggleBtn) {
        snapToggleBtn.addEventListener('click', () => {
          boardState.snapEnabled = !boardState.snapEnabled
          setToggleState(snapToggleBtn, boardState.snapEnabled)
        })
      }

      if (multiSelectToggleBtn) {
        multiSelectToggleBtn.addEventListener('click', () => {
          boardState.multiSelectEnabled = !boardState.multiSelectEnabled
          setToggleState(multiSelectToggleBtn, boardState.multiSelectEnabled)
          if (!boardState.multiSelectEnabled && boardState.selectedLayers.size > 1) {
            const active = boardState.activeLayer
            boardState.selectedLayers.forEach(layer => {
              if (layer !== active) setLayerSelected(layer, false)
            })
          }
        })
      }

      if (undoBtn) {
        undoBtn.addEventListener('click', () => {
          if (boardState.historyIndex <= 0) return
          boardState.historyIndex -= 1
          applySnapshot(boardState.history[boardState.historyIndex])
        })
      }

      if (redoBtn) {
        redoBtn.addEventListener('click', () => {
          if (boardState.historyIndex >= boardState.history.length - 1) return
          boardState.historyIndex += 1
          applySnapshot(boardState.history[boardState.historyIndex])
        })
      }

      if (resetPosBtn) {
        resetPosBtn.addEventListener('click', () => {
          const entries = getSelectedLayerEntries()
          if (!entries.length) return
          boardState.historyLocked = true
          entries.forEach(entry => {
            const { hInput, vInput } = getInputs(entry.cfg)
            if (!hInput || !vInput) return
            const hDefault = ensureNumber(hInput.dataset?.default, 0)
            const vDefault = ensureNumber(vInput.dataset?.default, 0)
            writeOffsets(entry.cfg, hDefault, vDefault)
            applyPosition(entry.cfg)
          })
          boardState.historyLocked = false
          recordHistory()
        })
      }

      if (nudgeButtons && nudgeButtons.length) {
        nudgeButtons.forEach(btn => {
          btn.addEventListener('click', () => {
            const step = Math.max(1, Number(nudgeStepSelect?.value) || 1)
            const direction = btn.dataset.overlayBoardNudge
            if (!direction) return
            const delta = {
              left: { x: -step, y: 0 },
              right: { x: step, y: 0 },
              up: { x: 0, y: -step },
              down: { x: 0, y: step }
            }[direction]
            if (!delta) return
            const entries = getSelectedLayerEntries()
            if (!entries.length) return
            boardState.historyLocked = true
            entries.forEach(entry => {
              const maxH = Math.max(0, entry.baseW - entry.natW)
              const maxV = Math.max(0, entry.baseH - entry.natH)
              const nextH = clamp(entry.actualH + delta.x, 0, maxH)
              const nextV = clamp(entry.actualV + delta.y, 0, maxV)
              const { inputH, inputV } = getInputsFromActual(
                entry.cfg,
                nextH,
                nextV,
                entry.natW,
                entry.natH,
                entry.baseW,
                entry.baseH
              )
              writeOffsets(entry.cfg, inputH, inputV)
              applyPosition(entry.cfg)
            })
            boardState.historyLocked = false
            recordHistory()
          })
        })
      }

      if (alignButtons && alignButtons.length) {
        alignButtons.forEach(btn => {
          btn.addEventListener('click', () => {
            const direction = btn.dataset.overlayBoardAlign
            if (!direction) return
            if (alignSelectedLayers(direction)) return
            const target = boardState.activeLayer
            if (!target) return
            const overlayId = target.dataset.overlayId || target.alt
            const cfg = configsById.get(overlayId)
            if (!cfg) return
            alignLayer(cfg, target, direction)
            recordHistory()
          })
        })
      }

      if (distributeButtons && distributeButtons.length) {
        distributeButtons.forEach(btn => {
          btn.addEventListener('click', () => {
            boardState.historyLocked = true
            distributeLayers(btn.dataset.overlayBoardDistribute)
            boardState.historyLocked = false
            recordHistory()
          })
        })
      }

      if (exportBtn && exportBtn.dataset.exportBound !== 'true') {
        exportBtn.addEventListener('click', () => {
          exportBoardImage()
        })
        exportBtn.dataset.exportBound = 'true'
      }

      if (viewport) {
        let panning = false
        let startPan = { x: 0, y: 0, panX: 0, panY: 0 }
        const onPanDown = (e) => {
          if (!boardState.panEnabled) return
          if (e.button !== 0) return
          if (e.target.closest('.overlay-board-layer')) return
          e.preventDefault()
          viewport.setPointerCapture(e.pointerId)
          panning = true
          startPan = { x: e.clientX, y: e.clientY, panX: boardState.panX, panY: boardState.panY }
          board.classList.add('overlay-board--panning')
        }
        const onPanMove = (e) => {
          if (!panning) return
          const dx = e.clientX - startPan.x
          const dy = e.clientY - startPan.y
          boardState.panX = startPan.panX + dx
          boardState.panY = startPan.panY + dy
          applyBoardTransform()
        }
        const onPanUp = (e) => {
          if (!panning) return
          panning = false
          viewport.releasePointerCapture(e.pointerId)
          board.classList.remove('overlay-board--panning')
        }
        viewport.addEventListener('pointerdown', onPanDown)
        window.addEventListener('pointermove', onPanMove)
        window.addEventListener('pointerup', onPanUp)
      }

      canvas.addEventListener('pointerdown', (e) => {
        if (e.target.closest('.overlay-board-layer')) return
        clearSelection()
      })

      applyBoardTransform()
      updateZoomLabel()

      const getScale = () => {
        const computed = window.getComputedStyle(canvas)
        const width = canvas.clientWidth || parseFloat(computed.width) || 1
        const height = canvas.clientHeight || parseFloat(computed.height) || (width / ratio)
        return { scaleX: width / baseWidth, scaleY: height / baseHeight }
      }

      const getInputs = (cfg) => {
        const hInput = cfg.hId ? document.getElementById(cfg.hId) : null
        const vInput = cfg.vId ? document.getElementById(cfg.vId) : null
        return { hInput, vInput }
      }

      const getInstanceId = (cfg) => cfg?.instanceId || cfg?.id

      const applyVisibility = (cfg, layer) => {
        const toggle = cfg.toggle
        const resolutionDisabled = cfg.id === 'overlay_resolution' && (() => {
          const { useResolution, useEdition } = getResolutionToggleState(cfg)
          return !useResolution && !useEdition
        })()
        const visible = (!toggle || toggle.checked) && !resolutionDisabled
        layer.style.display = visible ? 'block' : 'none'
        if (!visible) {
          if (boardState.activeLayer === layer) {
            setActiveLayer(null)
          }
          if (boardState.selectedLayers.has(layer)) {
            setLayerSelected(layer, false)
          }
        }
      }

      const parseOrigin = (origin = '') => {
        const originStr = (origin || '').toString().toLowerCase()
        const tokens = originStr.split(/[^a-z]+/).filter(Boolean)
        let hAlign = 'left'
        let vAlign = 'top'
        const hasCenter = tokens.includes('center')
        if (tokens.includes('right')) hAlign = 'right'
        else if (tokens.includes('left')) hAlign = 'left'
        else if (hasCenter) hAlign = 'center'

        if (tokens.includes('bottom')) vAlign = 'bottom'
        else if (tokens.includes('top')) vAlign = 'top'
        else if (hasCenter) vAlign = 'center'

        return { hAlign, vAlign }
      }

      const buildOrigin = (hAlign = 'left', vAlign = 'top') => {
        const safeH = ['left', 'center', 'right'].includes(hAlign) ? hAlign : 'left'
        const safeV = ['top', 'center', 'bottom'].includes(vAlign) ? vAlign : 'top'

        if (safeH === 'center' && safeV === 'center') return 'center'
        if (safeH === 'center') return `${safeV}_center`
        if (safeV === 'center') return `center_${safeH}`
        return `${safeV}_${safeH}`
      }

      const getAlignmentInputs = (cfg) => {
        const templateName = cfg?.container?.dataset?.overlayTemplate
        if (!templateName || !cfg?.container) {
          return { hAlignInput: null, vAlignInput: null }
        }
        return {
          hAlignInput: cfg.container.querySelector(`[name="${templateName}[horizontal_align]"]`),
          vAlignInput: cfg.container.querySelector(`[name="${templateName}[vertical_align]"]`)
        }
      }

      const syncOriginFromAlignmentInputs = (cfg) => {
        const { hAlignInput, vAlignInput } = getAlignmentInputs(cfg)
        if (!hAlignInput && !vAlignInput) return false

        const current = parseOrigin(cfg.origin || '')
        const rawH = (hAlignInput?.value || hAlignInput?.dataset?.default || current.hAlign || '').toString().trim().toLowerCase()
        const rawV = (vAlignInput?.value || vAlignInput?.dataset?.default || current.vAlign || '').toString().trim().toLowerCase()
        const nextH = ['left', 'center', 'right'].includes(rawH) ? rawH : current.hAlign
        const nextV = ['top', 'center', 'bottom'].includes(rawV) ? rawV : current.vAlign
        const nextOrigin = buildOrigin(nextH, nextV)

        if (nextOrigin && cfg.origin !== nextOrigin) {
          cfg.origin = nextOrigin
          return true
        }
        return false
      }

      const getLayerMetrics = (cfg, layer) => {
        const baseW = Number(cfg.baseWidth) || baseWidth
        const baseH = Number(cfg.baseHeight) || baseHeight
        const natW = cfg.naturalWidth || layer.naturalWidth || (baseW * 0.25)
        const natH = cfg.naturalHeight || layer.naturalHeight || (baseH * 0.25)
        return { baseW, baseH, natW, natH }
      }

      const getActualFromInputs = (cfg, natW, natH, baseW, baseH) => {
        const { hInput, vInput } = getInputs(cfg)
        const hValInput = ensureNumber(hInput?.value)
        const vValInput = ensureNumber(vInput?.value)
        const { hAlign, vAlign } = parseOrigin(cfg.origin)
        const centerH = (baseW - natW) / 2
        const centerV = (baseH - natH) / 2
        const actualH = hAlign === 'right'
          ? (baseW - natW - hValInput)
          : hAlign === 'center'
            ? (centerH + hValInput)
            : hValInput
        const actualV = vAlign === 'bottom'
          ? (baseH - natH - vValInput)
          : vAlign === 'center'
            ? (centerV + vValInput)
            : vValInput
        return { actualH, actualV }
      }

      const getInputsFromActual = (cfg, actualH, actualV, natW, natH, baseW, baseH) => {
        const { hAlign, vAlign } = parseOrigin(cfg.origin)
        const centerH = (baseW - natW) / 2
        const centerV = (baseH - natH) / 2
        const inputH = hAlign === 'right'
          ? (baseW - natW - actualH)
          : hAlign === 'center'
            ? (actualH - centerH)
            : actualH
        const inputV = vAlign === 'bottom'
          ? (baseH - natH - actualV)
          : vAlign === 'center'
            ? (actualV - centerV)
            : actualV
        return { inputH, inputV }
      }

      const getSelectedLayerEntries = () => {
        if (!boardState.selectedLayers.size) return []
        const entries = []
        boardState.selectedLayers.forEach(layer => {
          const id = layer.dataset.overlayId || layer.alt
          if (layer.dataset.overlayEdition === 'true') return
          const cfg = configsById.get(id)
          if (!cfg) return
          const style = window.getComputedStyle(layer)
          if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return
          const { baseW, baseH, natW, natH } = getLayerMetrics(cfg, layer)
          const { actualH, actualV } = getActualFromInputs(cfg, natW, natH, baseW, baseH)
          entries.push({ cfg, layer, baseW, baseH, natW, natH, actualH, actualV })
        })
        return entries
      }

      const alignLayer = (cfg, layer, direction) => {
        const { baseW, baseH, natW, natH } = getLayerMetrics(cfg, layer)
        const { actualH, actualV } = getActualFromInputs(cfg, natW, natH, baseW, baseH)
        let nextH = actualH
        let nextV = actualV

        if (direction === 'left') nextH = 0
        if (direction === 'center') nextH = (baseW - natW) / 2
        if (direction === 'right') nextH = baseW - natW
        if (direction === 'top') nextV = 0
        if (direction === 'middle') nextV = (baseH - natH) / 2
        if (direction === 'bottom') nextV = baseH - natH

        const maxH = Math.max(0, baseW - natW)
        const maxV = Math.max(0, baseH - natH)
        nextH = clamp(nextH, 0, maxH)
        nextV = clamp(nextV, 0, maxV)

        const { inputH, inputV } = getInputsFromActual(cfg, nextH, nextV, natW, natH, baseW, baseH)
        writeOffsets(cfg, inputH, inputV)
        applyPosition(cfg)
      }

      const alignSelectedLayers = (direction) => {
        const entries = getSelectedLayerEntries()
        if (entries.length <= 1) return false
        let minH = Infinity
        let maxRight = -Infinity
        let minV = Infinity
        let maxBottom = -Infinity
        entries.forEach(entry => {
          minH = Math.min(minH, entry.actualH)
          maxRight = Math.max(maxRight, entry.actualH + entry.natW)
          minV = Math.min(minV, entry.actualV)
          maxBottom = Math.max(maxBottom, entry.actualV + entry.natH)
        })
        const centerX = (minH + maxRight) / 2
        const centerY = (minV + maxBottom) / 2

        boardState.historyLocked = true
        entries.forEach(entry => {
          let nextH = entry.actualH
          let nextV = entry.actualV
          if (direction === 'left') nextH = minH
          if (direction === 'right') nextH = maxRight - entry.natW
          if (direction === 'center') nextH = centerX - (entry.natW / 2)
          if (direction === 'top') nextV = minV
          if (direction === 'bottom') nextV = maxBottom - entry.natH
          if (direction === 'middle') nextV = centerY - (entry.natH / 2)

          const maxH = Math.max(0, entry.baseW - entry.natW)
          const maxV = Math.max(0, entry.baseH - entry.natH)
          nextH = clamp(nextH, 0, maxH)
          nextV = clamp(nextV, 0, maxV)

          const { inputH, inputV } = getInputsFromActual(
            entry.cfg,
            nextH,
            nextV,
            entry.natW,
            entry.natH,
            entry.baseW,
            entry.baseH
          )
          writeOffsets(entry.cfg, inputH, inputV)
          applyPosition(entry.cfg)
        })
        boardState.historyLocked = false
        recordHistory()
        return true
      }

      const distributeLayers = (direction) => {
        const entries = getSelectedLayerEntries()
        if (entries.length < 3) return

        if (direction === 'horizontal') {
          const sorted = entries.slice().sort((a, b) => (a.actualH + a.natW / 2) - (b.actualH + b.natW / 2))
          const min = sorted[0].actualH + (sorted[0].natW / 2)
          const max = sorted[sorted.length - 1].actualH + (sorted[sorted.length - 1].natW / 2)
          const span = max - min
          if (!Number.isFinite(span) || span === 0) return
          const step = span / (sorted.length - 1)
          sorted.forEach((entry, index) => {
            const targetCenter = min + (step * index)
            const maxH = Math.max(0, entry.baseW - entry.natW)
            const nextH = clamp(targetCenter - (entry.natW / 2), 0, maxH)
            const { inputH, inputV } = getInputsFromActual(
              entry.cfg,
              nextH,
              entry.actualV,
              entry.natW,
              entry.natH,
              entry.baseW,
              entry.baseH
            )
            writeOffsets(entry.cfg, inputH, inputV)
            applyPosition(entry.cfg)
          })
          return
        }

        if (direction === 'vertical') {
          const sorted = entries.slice().sort((a, b) => (a.actualV + a.natH / 2) - (b.actualV + b.natH / 2))
          const min = sorted[0].actualV + (sorted[0].natH / 2)
          const max = sorted[sorted.length - 1].actualV + (sorted[sorted.length - 1].natH / 2)
          const span = max - min
          if (!Number.isFinite(span) || span === 0) return
          const step = span / (sorted.length - 1)
          sorted.forEach((entry, index) => {
            const targetCenter = min + (step * index)
            const maxV = Math.max(0, entry.baseH - entry.natH)
            const nextV = clamp(targetCenter - (entry.natH / 2), 0, maxV)
            const { inputH, inputV } = getInputsFromActual(
              entry.cfg,
              entry.actualH,
              nextV,
              entry.natW,
              entry.natH,
              entry.baseW,
              entry.baseH
            )
            writeOffsets(entry.cfg, inputH, inputV)
            applyPosition(entry.cfg)
          })
        }
      }
      const applyEditionVisibility = (cfg) => {
        if (!cfg.edition || !cfg.edition.layer) return
        if (cfg.id === 'overlay_resolution' && BACKDROP_IMAGE_OVERLAYS.has(cfg.id)) {
          cfg.edition.layer.style.display = 'none'
          return
        }
        const baseVisible = (!cfg.toggle || cfg.toggle.checked)
        const editionToggle = cfg.edition.toggle
        const editionVisible = baseVisible && (!editionToggle || editionToggle.checked)
        cfg.edition.layer.style.display = editionVisible ? 'block' : 'none'
      }

      const writeOffsets = (cfg, h, v) => {
        const { hInput, vInput } = getInputs(cfg)
        if (!hInput || !vInput) return
        // h and v passed in are input-space values (distance from origin if applicable)
        const inputH = h
        const inputV = v
        writing = true
        hInput.value = Math.round(inputH)
        vInput.value = Math.round(inputV)
        hInput.dispatchEvent(new Event('change', { bubbles: true }))
        vInput.dispatchEvent(new Event('change', { bubbles: true }))
        writing = false
        applyEditionPosition(cfg)
      }

      const applyOriginDefault = (cfg, layer) => {
        if (!cfg.origin || cfg.originApplied) return
        const { hInput, vInput } = getInputs(cfg)
        if (!hInput || !vInput) return
        if (hInput.value !== '' || vInput.value !== '') {
          cfg.originApplied = true
          return
        }
        const natW = cfg.naturalWidth || layer.naturalWidth
        const natH = cfg.naturalHeight || layer.naturalHeight
        if (!natW || !natH) return
        const hDefault = ensureNumber(hInput.dataset?.default, 0)
        const vDefault = ensureNumber(vInput.dataset?.default, 0)
        // For origin-based overlays, inputs represent distance from the origin edge (not from top-left)
        const hVal = hDefault
        const vVal = vDefault
        cfg.originApplied = true
        hInput.value = Math.round(hVal)
        vInput.value = Math.round(vVal)
        hInput.dispatchEvent(new Event('change', { bubbles: true }))
        vInput.dispatchEvent(new Event('change', { bubbles: true }))
      }

      const applyPosition = (cfg) => {
        const layer = layers.get(getInstanceId(cfg))
        if (!layer) return
        const { hInput, vInput } = getInputs(cfg)
        if (!hInput || !vInput) return

        syncOriginFromAlignmentInputs(cfg)

        const { scaleX, scaleY } = getScale()
        if (!cfg.naturalWidth && layer.naturalWidth) {
          cfg.naturalWidth = layer.naturalWidth
          cfg.naturalHeight = layer.naturalHeight
        }
        const natW = cfg.naturalWidth || layer.naturalWidth || (baseWidth * 0.25)
        const natH = cfg.naturalHeight || layer.naturalHeight || (baseHeight * 0.25)
        const baseW = Number(cfg.baseWidth) || baseWidth
        const baseH = Number(cfg.baseHeight) || baseHeight

        applyOriginDefault(cfg, layer)

        layer.style.width = `${natW * scaleX}px`
        layer.style.height = `${natH * scaleY}px`

        const hValInput = ensureNumber(hInput.value)
        const vValInput = ensureNumber(vInput.value)
        const { hAlign, vAlign } = parseOrigin(cfg.origin)
        const centerH = (baseW - natW) / 2
        const centerV = (baseH - natH) / 2
        const actualH = hAlign === 'right'
          ? (baseW - natW - hValInput)
          : hAlign === 'center'
            ? (centerH + hValInput)
            : hValInput
        const actualV = vAlign === 'bottom'
          ? (baseH - natH - vValInput)
          : vAlign === 'center'
            ? (centerV + vValInput)
            : vValInput

        layer.style.left = `${actualH * scaleX}px`
        layer.style.top = `${actualV * scaleY}px`
        applyVisibility(cfg, layer)
        applyEditionPosition(cfg)
      }

      const applyEditionPosition = (cfg) => {
        if (!cfg.edition || !cfg.edition.layer) return
        const baseLayer = layers.get(getInstanceId(cfg))
        if (!baseLayer) return

        const { hInput, vInput } = getInputs(cfg)
        if (!hInput || !vInput) return

        const { scaleX, scaleY } = getScale()
        const baseW = Number(cfg.baseWidth) || baseWidth
        const baseH = Number(cfg.baseHeight) || baseHeight
        const { hAlign, vAlign } = parseOrigin(cfg.origin)
        const resNatW = cfg.naturalWidth || baseLayer.naturalWidth || (baseW * 0.25)
        const resNatH = cfg.naturalHeight || baseLayer.naturalHeight || (baseH * 0.2)

        const edition = cfg.edition
        const editionNatW = edition.naturalWidth || edition.layer.naturalWidth || resNatW
        const editionNatH = edition.naturalHeight || edition.layer.naturalHeight || (resNatH * 0.4)

        edition.layer.style.width = `${editionNatW * scaleX}px`
        edition.layer.style.height = `${editionNatH * scaleY}px`

        const hInputVal = ensureNumber(hInput.value)
        const vInputVal = ensureNumber(vInput.value)
        const centerH = (baseW - resNatW) / 2
        const centerV = (baseH - resNatH) / 2
        const baseActualH = hAlign === 'right'
          ? (baseW - resNatW - hInputVal)
          : hAlign === 'center'
            ? (centerH + hInputVal)
            : hInputVal
        const baseActualV = vAlign === 'bottom'
          ? (baseH - resNatH - vInputVal)
          : vAlign === 'center'
            ? (centerV + vInputVal)
            : vInputVal
        const spacing = Number(edition.spacing) || 15
        const editionTop = baseActualV + resNatH + spacing

        edition.layer.style.left = `${baseActualH * scaleX}px`
        edition.layer.style.top = `${editionTop * scaleY}px`
        applyEditionVisibility(cfg)
      }

      const bindDrag = (cfg, layer) => {
        let dragging = false
        let moved = false
        let start = { x: 0, y: 0, h: 0, v: 0 }
        let dragGroup = null
        let dragBounds = null

        const onPointerDown = (e) => {
          e.preventDefault()
          layer.setPointerCapture(e.pointerId)
          const isMultiSelect = e.shiftKey || e.metaKey || e.ctrlKey || boardState.multiSelectEnabled
          if (isMultiSelect) {
            if (boardState.selectedLayers.has(layer)) {
              setLayerSelected(layer, false)
              if (boardState.activeLayer === layer) {
                const next = boardState.selectedLayers.values().next().value || null
                setActiveLayer(next)
              }
            } else {
              setLayerSelected(layer, true)
              setActiveLayer(layer)
            }
          } else {
            clearSelection()
            setLayerSelected(layer, true)
            setActiveLayer(layer)
          }
          moved = false
          dragGroup = null
          dragBounds = null
          const { hInput, vInput } = getInputs(cfg)
          const baseW = Number(cfg.baseWidth) || baseWidth
          const baseH = Number(cfg.baseHeight) || baseHeight
          const natW = cfg.naturalWidth || layer.naturalWidth || (baseWidth * 0.25)
          const natH = cfg.naturalHeight || layer.naturalHeight || (baseHeight * 0.25)
          const { hAlign, vAlign } = parseOrigin(cfg.origin)
          const inputH = ensureNumber(hInput?.value)
          const inputV = ensureNumber(vInput?.value)
          const centerH = (baseW - natW) / 2
          const centerV = (baseH - natH) / 2
          const actualH = hAlign === 'right'
            ? (baseW - natW - inputH)
            : hAlign === 'center'
              ? (centerH + inputH)
              : inputH
          const actualV = vAlign === 'bottom'
            ? (baseH - natH - inputV)
            : vAlign === 'center'
              ? (centerV + inputV)
              : inputV
          start = {
            x: e.clientX,
            y: e.clientY,
            h: actualH,
            v: actualV
          }
          const selectedEntries = getSelectedLayerEntries()
          if (selectedEntries.length > 1 && boardState.selectedLayers.has(layer)) {
            let minDx = -Infinity
            let maxDx = Infinity
            let minDy = -Infinity
            let maxDy = Infinity
            dragGroup = selectedEntries.map(entry => {
              const maxH = Math.max(0, entry.baseW - entry.natW)
              const maxV = Math.max(0, entry.baseH - entry.natH)
              minDx = Math.max(minDx, -entry.actualH)
              maxDx = Math.min(maxDx, maxH - entry.actualH)
              minDy = Math.max(minDy, -entry.actualV)
              maxDy = Math.min(maxDy, maxV - entry.actualV)
              return {
                cfg: entry.cfg,
                natW: entry.natW,
                natH: entry.natH,
                baseW: entry.baseW,
                baseH: entry.baseH,
                startH: entry.actualH,
                startV: entry.actualV
              }
            })
            dragBounds = { minDx, maxDx, minDy, maxDy }
          }
          dragging = true
          layer.classList.add('dragging')
        }

        const onPointerMove = (e) => {
          if (!dragging) return
          moved = true
          const { scaleX, scaleY } = getScale()
          const natW = cfg.naturalWidth || layer.naturalWidth || (baseWidth * 0.25)
          const natH = cfg.naturalHeight || layer.naturalHeight || (baseHeight * 0.25)
          const baseW = Number(cfg.baseWidth) || baseWidth
          const baseH = Number(cfg.baseHeight) || baseHeight
          const { hAlign, vAlign } = parseOrigin(cfg.origin)
          const overlayWidthBase = natW
          const overlayHeightBase = natH

          let deltaX = (e.clientX - start.x) / scaleX
          let deltaY = (e.clientY - start.y) / scaleY
          if (dragBounds) {
            deltaX = clamp(deltaX, dragBounds.minDx, dragBounds.maxDx)
            deltaY = clamp(deltaY, dragBounds.minDy, dragBounds.maxDy)
          }

          if (dragGroup) {
            dragGroup.forEach(entry => {
              const maxH = Math.max(0, entry.baseW - entry.natW)
              const maxV = Math.max(0, entry.baseH - entry.natH)
              const nextH = clamp(entry.startH + deltaX, 0, maxH)
              const nextV = clamp(entry.startV + deltaY, 0, maxV)
              const { inputH, inputV } = getInputsFromActual(
                entry.cfg,
                nextH,
                nextV,
                entry.natW,
                entry.natH,
                entry.baseW,
                entry.baseH
              )
              writeOffsets(entry.cfg, inputH, inputV)
              applyPosition(entry.cfg)
            })
            return
          }

          const maxH = Math.max(0, baseWidth - overlayWidthBase)
          const maxV = Math.max(0, baseHeight - overlayHeightBase)

          const rawActualH = clamp(start.h + deltaX, 0, maxH)
          const rawActualV = clamp(start.v + deltaY, 0, maxV)
          const nextActualH = snapToGrid(rawActualH, maxH)
          const nextActualV = snapToGrid(rawActualV, maxV)

          const centerH = (baseW - natW) / 2
          const centerV = (baseH - natH) / 2
          const nextInputH = hAlign === 'right'
            ? (baseW - natW - nextActualH)
            : hAlign === 'center'
              ? (nextActualH - centerH)
              : nextActualH
          const nextInputV = vAlign === 'bottom'
            ? (baseH - natH - nextActualV)
            : vAlign === 'center'
              ? (nextActualV - centerV)
              : nextActualV

          layer.style.left = `${nextActualH * scaleX}px`
          layer.style.top = `${nextActualV * scaleY}px`
          writeOffsets(cfg, nextInputH, nextInputV)
          applyEditionPosition(cfg)
        }

        const onPointerUp = (e) => {
          if (!dragging) return
          dragging = false
          layer.releasePointerCapture(e.pointerId)
          layer.classList.remove('dragging')
          if (moved) recordHistory()
        }

        layer.addEventListener('pointerdown', onPointerDown)
        window.addEventListener('pointermove', onPointerMove)
        window.addEventListener('pointerup', onPointerUp)
      }

      const bindInputs = (cfg) => {
        const { hInput, vInput } = getInputs(cfg)
        const handleInput = () => {
          if (writing) return
          applyPosition(cfg)
        }
        const handleChange = () => {
          if (writing) return
          applyPosition(cfg)
          if (!boardState.historyLocked) recordHistory()
        }
        hInput?.addEventListener('input', handleInput)
        vInput?.addEventListener('input', handleInput)
        hInput?.addEventListener('change', handleChange)
        vInput?.addEventListener('change', handleChange)
      }

      const bindToggle = (cfg, layer) => {
        const toggle = cfg.toggle
        if (!toggle) return
        const handler = () => {
          applyVisibility(cfg, layer)
          applyEditionPosition(cfg)
        }
        toggle.addEventListener('change', handler)
      }

      const updateFlagsLayer = (cfg, layer) => {
        buildFlagsCompositeDataUrl(cfg).then(dataUrl => {
          layer.src = dataUrl
          applyPosition(cfg)
        })
      }

      const addOverlayLayer = (cfg) => {
        const instanceId = getInstanceId(cfg)
        if (layers.has(instanceId)) return layers.get(instanceId)
        const layer = document.createElement('img')
        layer.className = 'overlay-board-layer'
        layer.alt = instanceId
        layer.dataset.overlayId = instanceId
        layer.dataset.overlayType = cfg.id
        cfg.layer = layer
        layers.set(instanceId, layer)
        canvas.appendChild(layer)

        const handleLoad = () => {
          cfg.naturalWidth = layer.naturalWidth || cfg.naturalWidth
          cfg.naturalHeight = layer.naturalHeight || cfg.naturalHeight
          applyPosition(cfg)
        }

        layer.addEventListener('load', handleLoad)

        let initialSrc = resolveOverlayImage(cfg)
        let shouldAssignInitialSrc = true
        if (isFlagsOverlay(cfg)) {
          shouldAssignInitialSrc = false
          updateFlagsLayer(cfg, layer)
        } else if (cfg.id === 'overlay_ribbon') {
          shouldAssignInitialSrc = false
          buildRibbonCompositeDataUrl(cfg).then(dataUrl => {
            layer.src = dataUrl
            applyPosition(cfg)
          })
        } else if (BACKDROP_IMAGE_OVERLAYS.has(cfg.id)) {
          shouldAssignInitialSrc = false
          buildBackdropDataUrl(cfg).then(dataUrl => {
            layer.src = dataUrl
            applyPosition(cfg)
          })
        } else if (cfg.id && cfg.id.startsWith('overlay_content_rating_') && cfg.id !== 'overlay_content_rating_commonsense') {
          shouldAssignInitialSrc = false
          const applyContentRatingPreview = () => {
            refreshContentRatingOverlayPreview(cfg)
            applyPosition(cfg)
          }
          applyContentRatingPreview()
        } else if (cfg.id === 'overlay_content_rating_commonsense') {
          shouldAssignInitialSrc = false
          const applyContentRatingPreview = () => {
            refreshContentRatingOverlayPreview(cfg)
            applyPosition(cfg)
          }
          applyContentRatingPreview()
        } else if (cfg.id === 'overlay_runtimes') {
          initialSrc = buildRuntimeDataUrl(cfg)
          if (BACKDROP_TEXT_OVERLAYS.has(cfg.id)) {
            shouldAssignInitialSrc = false
            buildBackdropDataUrl(cfg, initialSrc).then(backdropUrl => {
              layer.src = backdropUrl
              applyPosition(cfg)
            })
          }
        } else if (cfg.id === 'overlay_status') {
          initialSrc = buildSimpleTextDataUrl(cfg, getStatusTextVars(cfg))
          if (BACKDROP_TEXT_OVERLAYS.has(cfg.id)) {
            shouldAssignInitialSrc = false
            buildBackdropDataUrl(cfg, initialSrc).then(backdropUrl => {
              layer.src = backdropUrl
              applyPosition(cfg)
            })
          }
        } else if (cfg.id === 'overlay_episode_info') {
          initialSrc = buildSimpleTextDataUrl(cfg, getSimpleTextVars(cfg))
        }
        if (shouldAssignInitialSrc && initialSrc) {
          layer.src = initialSrc
        }
        if (layer.complete) handleLoad()

        bindDrag(cfg, layer)
        bindToggle(cfg, layer)
        bindInputs(cfg)
        if (cfg.styleInput) {
          cfg.styleInput.addEventListener('change', () => {
            if (cfg.id === 'overlay_audio_codec') {
              syncAudioCodecBackdropHeight(cfg, false)
            }
            if (isFlagsOverlay(cfg)) {
              updateFlagsLayer(cfg, layer)
              return
            }
            if (cfg.id === 'overlay_ribbon') {
              buildRibbonCompositeDataUrl(cfg).then(dataUrl => {
                layer.src = dataUrl
                applyPosition(cfg)
              })
              return
            }
            if (BACKDROP_IMAGE_OVERLAYS.has(cfg.id)) {
              buildBackdropDataUrl(cfg).then(dataUrl => {
                layer.src = dataUrl
                applyPosition(cfg)
              })
              return
            }
            layer.src = resolveOverlayImage(cfg)
          })
        }

        if (cfg.id === 'overlay_runtimes' && cfg.container) {
          const templateName = cfg.container.dataset.overlayTemplate
          const runtimeSelectors = [
            `[name="${templateName}[text]"]`,
            `[name="${templateName}[format]"]`,
            `[name="${templateName}[font]"]`,
            `[name="${templateName}[font_size]"]`,
            `[name="${templateName}[font_color]"]`,
            `[name="${templateName}[stroke_width]"]`,
            `[name="${templateName}[stroke_color]"]`
          ]
          if (BACKDROP_TEXT_OVERLAYS.has(cfg.id)) {
            runtimeSelectors.push(
              `[name="${templateName}[back_align]"]`,
              `[name="${templateName}[back_color]"]`,
              `[name="${templateName}[back_height]"]`,
              `[name="${templateName}[back_width]"]`,
              `[name="${templateName}[back_line_color]"]`,
              `[name="${templateName}[back_line_width]"]`,
              `[name="${templateName}[back_padding]"]`,
              `[name="${templateName}[back_radius]"]`
            )
          }
          const runtimeInputs = cfg.container.querySelectorAll(runtimeSelectors.join(', '))
          const refreshRuntime = () => {
            const { font } = getRuntimeVars(cfg)
            ensureRuntimeFontLoaded(font).then(family => {
              const { family: norm } = normalizeFontFile(font)
              const dataUrl = buildRuntimeDataUrl(cfg, family || norm)
              if (BACKDROP_TEXT_OVERLAYS.has(cfg.id)) {
                buildBackdropDataUrl(cfg, dataUrl).then(backdropUrl => {
                  layer.src = backdropUrl
                  applyPosition(cfg)
                })
                return
              }
              layer.src = dataUrl
            })
          }
          runtimeInputs.forEach(input => {
            input.addEventListener('input', refreshRuntime)
            input.addEventListener('change', refreshRuntime)
          })
        }
        if (cfg.id && cfg.id.startsWith('overlay_content_rating_') && cfg.container) {
          const templateName = cfg.container.dataset.overlayTemplate
          const colorInput = cfg.container.querySelector(`[name="${templateName}[color]"]`)
          if (colorInput) {
            const refreshColor = () => {
              if (cfg.id === 'overlay_content_rating_commonsense') return
              refreshContentRatingOverlayPreview(cfg)
              applyPosition(cfg)
            }
            colorInput.addEventListener('change', refreshColor)
            colorInput.addEventListener('input', refreshColor)
          }
          if (cfg.id !== 'overlay_content_rating_commonsense') {
            const refreshBackdrop = () => {
              refreshContentRatingOverlayPreview(cfg)
              applyPosition(cfg)
            }
            const backInputs = cfg.container.querySelectorAll(
              `[name="${templateName}[back_align]"], [name="${templateName}[back_color]"], [name="${templateName}[back_height]"], [name="${templateName}[back_width]"], [name="${templateName}[back_line_color]"], [name="${templateName}[back_line_width]"], [name="${templateName}[back_padding]"], [name="${templateName}[back_radius]"]`
            )
            backInputs.forEach(input => {
              input.addEventListener('input', refreshBackdrop)
              input.addEventListener('change', refreshBackdrop)
            })
          }
        }
        applyPosition(cfg)

        // Optional stacked edition layer (for resolution overlays)
        if (cfg.edition && cfg.edition.image && !cfg.edition.layer) {
          const editionLayer = document.createElement('img')
          editionLayer.className = 'overlay-board-layer'
          editionLayer.alt = `${cfg.id}-edition`
          editionLayer.dataset.overlayId = cfg.edition.id
          editionLayer.dataset.overlayEdition = 'true'
          editionLayer.dataset.overlayParentId = cfg.id
          editionLayer.style.pointerEvents = 'none' // let dragging happen on the base resolution layer
          cfg.edition.layer = editionLayer
          layers.set(cfg.edition.id, editionLayer)
          canvas.appendChild(editionLayer)

          const handleEditionLoad = () => {
            cfg.edition.naturalWidth = editionLayer.naturalWidth || cfg.edition.naturalWidth
            cfg.edition.naturalHeight = editionLayer.naturalHeight || cfg.edition.naturalHeight
            applyEditionPosition(cfg)
          }

          editionLayer.addEventListener('load', handleEditionLoad)
          editionLayer.src = cfg.edition.image
          if (editionLayer.complete) handleEditionLoad()

          if (cfg.edition.toggle) {
            const refreshResolutionMode = () => {
              syncResolutionBackdropHeight(cfg)
              syncResolutionEditionVisibility(cfg)
              syncResolutionChildToggleVisibility(cfg)
              syncResolutionToggleWarning(cfg)
              if (BACKDROP_IMAGE_OVERLAYS.has(cfg.id)) {
                buildBackdropDataUrl(cfg).then(dataUrl => {
                  layer.src = dataUrl
                  applyPosition(cfg)
                })
              }
              applyEditionPosition(cfg)
            }
            cfg.edition.toggle.addEventListener('change', refreshResolutionMode)
            const resolutionTemplateName = cfg.container?.dataset?.overlayTemplate
            const resolutionToggle = resolutionTemplateName
              ? cfg.container.querySelector(`input[name="${resolutionTemplateName}[use_resolution]"]`)
              : null
            if (resolutionToggle) {
              resolutionToggle.addEventListener('change', refreshResolutionMode)
            }
          }

          applyEditionPosition(cfg)
        }
        return layer
      }

      const overlayContainers = Array.from(document.querySelectorAll(`.template-toggle-group[data-overlay-type="${overlayType}"][data-library-id="${libId}"]`))
      const configs = []
      overlayContainers.forEach(container => {
        const cfg = {
          id: container.dataset.overlayId,
          instanceId: container.dataset.overlayTemplate || container.dataset.overlayId,
          image: container.dataset.overlayImage,
          hId: container.dataset.horizontalId,
          vId: container.dataset.verticalId,
          baseWidth,
          baseHeight,
          toggle: container.querySelector('.overlay-toggle'),
          styleInput: (container.dataset.styleInputId && document.getElementById(container.dataset.styleInputId)) || null,
          naturalWidth: null,
          naturalHeight: null,
          edition: null,
          container,
          origin: container.dataset.overlayOrigin || null,
          originApplied: false
        }

        if (!cfg.id || !cfg.image || !cfg.hId || !cfg.vId) return
        if (!document.getElementById(cfg.hId) || !document.getElementById(cfg.vId)) return

        const templateName = container.dataset.overlayTemplate
        const editionImage = container.dataset.overlayEditionImage
        if (cfg.id === 'overlay_resolution' && editionImage) {
          const editionToggle = templateName
            ? container.querySelector(`input[name="${templateName}[use_edition]"]`)
            : null
          cfg.edition = {
            id: `${cfg.instanceId}__edition`,
            image: editionImage,
            toggle: editionToggle,
            naturalWidth: null,
            naturalHeight: null,
            layer: null,
            spacing: 15
          }
        }
        ensureResolutionToggleFamilyGroups(cfg)
        ensureContentRatingPreviewControl(cfg)
        ensureFlagsPreviewControl(cfg)
        ensureOverlayTextPreviewControl(cfg)
        ensureSingleBadgeOverlayPreviewControl(cfg)
        ensureStreamingPreviewControl(cfg)
        ensureAudioCodecPreviewControl(cfg)
        ensureRibbonPreviewControl(cfg)
        ensureLanguageCountPreviewControl(cfg)
        ensureOverlaySourceOverrideEditor(cfg)
        bindResolutionPreviewInputs(cfg)
        bindContentRatingPreviewInputs(cfg)
        bindFlagsPreviewInputs(cfg)
        bindOverlayTextPreviewInputs(cfg)
        bindSingleBadgeOverlayPreviewInputs(cfg)
        bindStreamingPreviewInputs(cfg)
        bindAudioCodecPreviewInputs(cfg)
        bindRibbonPreviewInputs(cfg)
        bindLanguageCountPreviewInputs(cfg)
        syncContentRatingPreviewControls(cfg)
        syncFlagsPreviewControls(cfg)
        syncOverlayTextPreviewControls(cfg)
        syncSingleBadgeOverlayPreviewControls(cfg)
        syncStreamingPreviewControls(cfg)
        syncRibbonPreviewControls(cfg)
        syncLanguageCountPreviewControls(cfg)
        syncAudioCodecBackdropHeight(cfg, false)
        syncAudioCodecPreviewControls(cfg)
        syncResolutionBackdropHeight(cfg, false)
        syncResolutionEditionVisibility(cfg, false)
        syncResolutionChildToggleVisibility(cfg)
        syncResolutionToggleWarning(cfg)
        configs.push(cfg)
        configsById.set(cfg.instanceId, cfg)
        const layer = addOverlayLayer(cfg)
        cfg.layer = layer
        const { hAlignInput, vAlignInput } = getAlignmentInputs(cfg)
        ;[hAlignInput, vAlignInput].forEach(input => {
          if (!input || input.dataset.overlayAlignBound === 'true') return
          const refreshAlignment = () => {
            syncOriginFromAlignmentInputs(cfg)
            applyPosition(cfg)
          }
          input.addEventListener('input', refreshAlignment)
          input.addEventListener('change', refreshAlignment)
          input.dataset.overlayAlignBound = 'true'
        })

        if (cfg.id === 'overlay_runtimes' && layer) {
          const { font } = getRuntimeVars(cfg)
          ensureRuntimeFontLoaded(font).then(family => {
            const { family: norm } = normalizeFontFile(font)
            const dataUrl = buildRuntimeDataUrl(cfg, family || norm)
            if (BACKDROP_TEXT_OVERLAYS.has(cfg.id)) {
              buildBackdropDataUrl(cfg, dataUrl).then(backdropUrl => {
                layer.src = backdropUrl
                applyPosition(cfg)
              })
              return
            }
            layer.src = dataUrl
          })
        }

        if ((cfg.id === 'overlay_video_format' || cfg.id === 'overlay_aspect' || cfg.id === 'overlay_episode_info') && layer && cfg.container) {
          const refreshTextOverlay = () => {
            const vars = getSimpleTextVars(cfg)
            ensureRuntimeFontLoaded(vars.font).then(family => {
              const { family: norm } = normalizeFontFile(vars.font)
              const dataUrl = buildSimpleTextDataUrl(cfg, vars, family || norm)
              if (BACKDROP_TEXT_OVERLAYS.has(cfg.id)) {
                buildBackdropDataUrl(cfg, dataUrl).then(backdropUrl => {
                  layer.src = backdropUrl
                  applyPosition(cfg)
                })
                return
              }
              layer.src = dataUrl
            })
          }

          const overlayTemplateName = cfg.container.dataset.overlayTemplate
          const textSelectors = [
            `[name="${overlayTemplateName}[text]"]`,
            `[name="${overlayTemplateName}[font]"]`,
            `[name="${overlayTemplateName}[font_size]"]`,
            `[name="${overlayTemplateName}[font_color]"]`,
            `[name="${overlayTemplateName}[stroke_width]"]`,
            `[name="${overlayTemplateName}[stroke_color]"]`
          ]
          if (BACKDROP_TEXT_OVERLAYS.has(cfg.id)) {
            textSelectors.push(
              `[name="${overlayTemplateName}[back_align]"]`,
              `[name="${overlayTemplateName}[back_color]"]`,
              `[name="${overlayTemplateName}[back_height]"]`,
              `[name="${overlayTemplateName}[back_width]"]`,
              `[name="${overlayTemplateName}[back_line_color]"]`,
              `[name="${overlayTemplateName}[back_line_width]"]`,
              `[name="${overlayTemplateName}[back_padding]"]`,
              `[name="${overlayTemplateName}[back_radius]"]`
            )
          }
          const inputs = cfg.container.querySelectorAll(textSelectors.join(', '))
          inputs.forEach(input => {
            input.addEventListener('input', refreshTextOverlay)
            input.addEventListener('change', refreshTextOverlay)
          })
          refreshTextOverlay()
        }

        if (cfg.id === 'overlay_status' && layer && cfg.container) {
          const refreshStatus = () => {
            const vars = getStatusTextVars(cfg)
            ensureRuntimeFontLoaded(vars.font).then(family => {
              const { family: norm } = normalizeFontFile(vars.font)
              const dataUrl = buildSimpleTextDataUrl(cfg, vars, family || norm)
              if (BACKDROP_TEXT_OVERLAYS.has(cfg.id)) {
                buildBackdropDataUrl(cfg, dataUrl).then(backdropUrl => {
                  layer.src = backdropUrl
                  applyPosition(cfg)
                })
                return
              }
              layer.src = dataUrl
              applyPosition(cfg)
            })
          }

          const overlayTemplateName = cfg.container.dataset.overlayTemplate
          const statusSelectors = [
            `[name="${overlayTemplateName}[text_airing]"]`,
            `[name="${overlayTemplateName}[text_returning]"]`,
            `[name="${overlayTemplateName}[text_canceled]"]`,
            `[name="${overlayTemplateName}[text_ended]"]`,
            `[name="${overlayTemplateName}[font]"]`,
            `[name="${overlayTemplateName}[font_size]"]`,
            `[name="${overlayTemplateName}[font_color]"]`,
            `[name="${overlayTemplateName}[stroke_width]"]`,
            `[name="${overlayTemplateName}[stroke_color]"]`
          ]
          if (BACKDROP_TEXT_OVERLAYS.has(cfg.id)) {
            statusSelectors.push(
              `[name="${overlayTemplateName}[back_align]"]`,
              `[name="${overlayTemplateName}[back_color]"]`,
              `[name="${overlayTemplateName}[back_height]"]`,
              `[name="${overlayTemplateName}[back_width]"]`,
              `[name="${overlayTemplateName}[back_line_color]"]`,
              `[name="${overlayTemplateName}[back_line_width]"]`,
              `[name="${overlayTemplateName}[back_padding]"]`,
              `[name="${overlayTemplateName}[back_radius]"]`
            )
          }
          const inputs = cfg.container.querySelectorAll(statusSelectors.join(', '))
          inputs.forEach(input => {
            input.addEventListener('input', refreshStatus)
            input.addEventListener('change', refreshStatus)
          })
          refreshStatus()
        }

        if (cfg.id === 'overlay_ratings' && layer && cfg.container) {
          const runRatingsUpdate = (event, forceSync = false, preserveExistingSources = false) => {
            if (cfg.container?.dataset?.resetting === 'true') return
            enforceUniqueRatingTypes(cfg)
            if (event && event.target && cfg.container) {
              const targetName = event.target.name || ''
              if (targetName.includes('[rating1_image]') || targetName.includes('[rating2_image]') || targetName.includes('[rating3_image]')) {
                cfg.container.dataset.ratingFontForce = 'true'
              }
              if (
                targetName.includes('[rating1]') || targetName.includes('[rating2]') || targetName.includes('[rating3]') ||
                targetName.includes('[rating1_image]') || targetName.includes('[rating2_image]') || targetName.includes('[rating3_image]')
              ) {
                forceSync = true
              }
            }
            if (forceSync) {
              captureRatingBeforeMap(cfg)
              const slots = [
                { ratingKey: 'rating1', imageKey: 'rating1_image' },
                { ratingKey: 'rating2', imageKey: 'rating2_image' },
                { ratingKey: 'rating3', imageKey: 'rating3_image' }
              ]
              slots.forEach(slot => syncRatingSources(cfg, slot, { preserveExisting: preserveExistingSources }))
            }
            const positionInput = cfg.container.querySelector(`[name="${templateName}[horizontal_position]"]`)
            const verticalInput = cfg.container.querySelector(`[name="${templateName}[vertical_position]"]`)
            if (positionInput || verticalInput) {
              const rawH = (positionInput?.value || positionInput?.dataset?.default || '').toString().trim().toLowerCase()
              const rawV = (verticalInput?.value || verticalInput?.dataset?.default || '').toString().trim().toLowerCase()
              const { hAlign, vAlign } = parseOrigin(cfg.origin || 'center_left')
              const nextH = (rawH === 'left' || rawH === 'center' || rawH === 'right') ? rawH : hAlign
              const nextV = (rawV === 'top' || rawV === 'center' || rawV === 'bottom') ? rawV : vAlign
              const safeH = (nextH === 'left' || nextH === 'center' || nextH === 'right') ? nextH : 'left'
              const safeV = (nextV === 'top' || nextV === 'center' || nextV === 'bottom') ? nextV : 'center'
              let nextOrigin = ''
              if (safeH === 'center' && safeV === 'center') {
                nextOrigin = 'center'
              } else if (safeH === 'center') {
                nextOrigin = `${safeV}_center`
              } else if (safeV === 'center') {
                nextOrigin = `center_${safeH}`
              } else {
                nextOrigin = `${safeV}_${safeH}`
              }
              if (nextOrigin && cfg.origin !== nextOrigin) {
                cfg.origin = nextOrigin
              }
            }
            applyRatingFontDefaults(cfg)
            updateRatingSyncStatus(cfg)
            renderRatingMappingModal(cfg)
            refreshRatingsOverlayPreview(cfg)
          }
          const scheduleRatingsUpdate = (event, forceSync = false, preserveExistingSources = false) => {
            if (!cfg.container) return
            if (cfg.container.dataset.ratingRefreshScheduled === 'true') {
              if (forceSync) cfg.container.dataset.ratingRefreshForce = 'true'
              if (preserveExistingSources) cfg.container.dataset.ratingRefreshPreserve = 'true'
              return
            }
            cfg.container.dataset.ratingRefreshScheduled = 'true'
            if (forceSync) cfg.container.dataset.ratingRefreshForce = 'true'
            if (preserveExistingSources) cfg.container.dataset.ratingRefreshPreserve = 'true'
            requestAnimationFrame(() => {
              const doForce = cfg.container?.dataset?.ratingRefreshForce === 'true'
              const doPreserve = cfg.container?.dataset?.ratingRefreshPreserve === 'true'
              if (cfg.container) {
                delete cfg.container.dataset.ratingRefreshScheduled
                delete cfg.container.dataset.ratingRefreshForce
                delete cfg.container.dataset.ratingRefreshPreserve
              }
              runRatingsUpdate(null, doForce, doPreserve)
            })
          }
          const overlayTemplateName = cfg.container.dataset.overlayTemplate
          const ratingFontInputs = [
            getTemplateInput(cfg, 'rating1_font'),
            getTemplateInput(cfg, 'rating2_font'),
            getTemplateInput(cfg, 'rating3_font')
          ]
          ratingFontInputs.forEach(input => {
            if (!input || input.dataset.ratingFontWatch === 'true') return
            input.addEventListener('change', (event) => {
              if (event && event.isTrusted) {
                input.dataset.ratingFontUser = 'true'
                input.dataset.ratingFontAuto = 'false'
              }
            })
            input.dataset.ratingFontWatch = 'true'
          })
          const ratingSelectors = [
            `[name="${overlayTemplateName}[rating1]"]`,
            `[name="${overlayTemplateName}[rating1_image]"]`,
            `[name="${overlayTemplateName}[rating1_font]"]`,
            `[name="${overlayTemplateName}[rating1_font_size]"]`,
            `[name="${overlayTemplateName}[rating1_font_color]"]`,
            `[name="${overlayTemplateName}[rating1_stroke_width]"]`,
            `[name="${overlayTemplateName}[rating1_stroke_color]"]`,
            `[name="${overlayTemplateName}[rating2]"]`,
            `[name="${overlayTemplateName}[rating2_image]"]`,
            `[name="${overlayTemplateName}[rating2_font]"]`,
            `[name="${overlayTemplateName}[rating2_font_size]"]`,
            `[name="${overlayTemplateName}[rating2_font_color]"]`,
            `[name="${overlayTemplateName}[rating2_stroke_width]"]`,
            `[name="${overlayTemplateName}[rating2_stroke_color]"]`,
            `[name="${overlayTemplateName}[rating3]"]`,
            `[name="${overlayTemplateName}[rating3_image]"]`,
            `[name="${overlayTemplateName}[rating3_font]"]`,
            `[name="${overlayTemplateName}[rating3_font_size]"]`,
            `[name="${overlayTemplateName}[rating3_font_color]"]`,
            `[name="${overlayTemplateName}[rating3_stroke_width]"]`,
            `[name="${overlayTemplateName}[rating3_stroke_color]"]`,
            `[name="${overlayTemplateName}[horizontal_position]"]`,
            `[name="${overlayTemplateName}[vertical_position]"]`,
            `[name="${overlayTemplateName}[rating_alignment]"]`,
            `[name="${overlayTemplateName}[back_width]"]`,
            `[name="${overlayTemplateName}[back_height]"]`,
            `[name="${overlayTemplateName}[back_padding]"]`,
            `[name="${overlayTemplateName}[addon_position]"]`,
            `[name="${overlayTemplateName}[addon_offset]"]`
          ]
          const inputs = cfg.container.querySelectorAll(ratingSelectors.join(', '))
          inputs.forEach(input => {
            input.addEventListener('input', scheduleRatingsUpdate)
            input.addEventListener('change', scheduleRatingsUpdate)
          })
          if (cfg.toggle && cfg.toggle.dataset.ratingSyncBound !== 'true') {
            cfg.toggle.dataset.ratingSyncBound = 'true'
            cfg.toggle.addEventListener('change', () => {
              if (cfg.toggle.checked) {
                scheduleRatingsUpdate(null, true, true)
              }
            })
          }
          if (cfg.toggle && cfg.toggle.checked) {
            scheduleRatingsUpdate(null, true, true)
          } else {
            scheduleRatingsUpdate()
          }
        }

        if (isFlagsOverlay(cfg) && layer && cfg.container) {
          const overlayTemplateName = cfg.container.dataset.overlayTemplate
          const refreshFlags = () => updateFlagsLayer(cfg, layer)
          const flagSelectors = [
            `[name="${overlayTemplateName}[style]"]`,
            `[name="${overlayTemplateName}[hide_text]"]`,
            `[name="${overlayTemplateName}[use_lowercase]"]`,
            `[name="${overlayTemplateName}[group_alignment]"]`,
            `[name="${overlayTemplateName}[offset]"]`,
            `[name="${overlayTemplateName}[font]"]`,
            `[name="${overlayTemplateName}[font_size]"]`,
            `[name="${overlayTemplateName}[font_color]"]`,
            `[name="${overlayTemplateName}[stroke_width]"]`,
            `[name="${overlayTemplateName}[stroke_color]"]`,
            `[name="${overlayTemplateName}[back_color]"]`,
            `[name="${overlayTemplateName}[back_height]"]`,
            `[name="${overlayTemplateName}[back_width]"]`,
            `[name="${overlayTemplateName}[back_line_color]"]`,
            `[name="${overlayTemplateName}[back_line_width]"]`,
            `[name="${overlayTemplateName}[back_padding]"]`,
            `[name="${overlayTemplateName}[back_radius]"]`
          ]
          const inputs = cfg.container.querySelectorAll(flagSelectors.join(', '))
          inputs.forEach(input => {
            input.addEventListener('input', refreshFlags)
            input.addEventListener('change', refreshFlags)
          })
          const sizeInput = cfg.container.querySelector(`[name="${overlayTemplateName}[size]"]`)
          if (sizeInput) {
            const handleSizeChange = () => {
              syncFlagSizeDefaults(cfg, true)
              refreshFlags()
            }
            sizeInput.addEventListener('input', handleSizeChange)
            sizeInput.addEventListener('change', handleSizeChange)
          }
          refreshFlags()
        }

        if (BACKDROP_IMAGE_OVERLAYS.has(cfg.id) && layer && cfg.container) {
          const refreshBackdrop = () => {
            buildBackdropDataUrl(cfg).then(dataUrl => {
              layer.src = dataUrl
              applyPosition(cfg)
            })
          }
          const overlayTemplateName = cfg.container.dataset.overlayTemplate
          const inputs = cfg.container.querySelectorAll(
            `[name="${overlayTemplateName}[back_align]"], [name="${overlayTemplateName}[back_color]"], [name="${overlayTemplateName}[back_height]"], [name="${overlayTemplateName}[back_width]"], [name="${overlayTemplateName}[back_line_color]"], [name="${overlayTemplateName}[back_line_width]"], [name="${overlayTemplateName}[back_padding]"], [name="${overlayTemplateName}[back_radius]"]`
          )
          inputs.forEach(input => {
            input.addEventListener('input', refreshBackdrop)
            input.addEventListener('change', refreshBackdrop)
          })
          refreshBackdrop()
        }

        if (cfg.id === 'overlay_content_rating_commonsense' && layer && cfg.container) {
          const refreshCommonsense = () => {
            refreshContentRatingOverlayPreview(cfg)
            applyPosition(cfg)
          }
          const overlayTemplateName = cfg.container.dataset.overlayTemplate
          const inputs = cfg.container.querySelectorAll(
            `[name="${overlayTemplateName}[text]"], [name="${overlayTemplateName}[post_text]"], [name="${overlayTemplateName}[addon_offset]"], [name="${overlayTemplateName}[font]"], [name="${overlayTemplateName}[font_size]"], [name="${overlayTemplateName}[font_color]"], [name="${overlayTemplateName}[stroke_width]"], [name="${overlayTemplateName}[stroke_color]"], [name="${overlayTemplateName}[back_align]"], [name="${overlayTemplateName}[back_color]"], [name="${overlayTemplateName}[back_height]"], [name="${overlayTemplateName}[back_width]"], [name="${overlayTemplateName}[back_line_color]"], [name="${overlayTemplateName}[back_line_width]"], [name="${overlayTemplateName}[back_padding]"], [name="${overlayTemplateName}[back_radius]"]`
          )
          inputs.forEach(input => {
            input.addEventListener('input', refreshCommonsense)
            input.addEventListener('change', refreshCommonsense)
          })
          refreshCommonsense()
        }
      })

      // Recompute positions after images load or container resizes
      recalcAll = () => {
        configs.forEach(cfg => {
          applyPosition(cfg)
          applyEditionPosition(cfg)
        })
      }
      recordHistory()
      board._overlayRecalc = recalcAll

      if (typeof ResizeObserver !== 'undefined') {
        let resizeRaf = false
        const resizeObserver = new ResizeObserver(() => {
          if (resizeRaf) return
          resizeRaf = true
          requestAnimationFrame(() => {
            recalcAll()
            resizeRaf = false
          })
        })
        resizeObserver.observe(canvas)
      }

      window.addEventListener('resize', recalcAll)

      const setupModalCanvas = () => {
        const modalBtn = toolbar?.querySelector('[data-overlay-board-open="modal"]') ||
          board.querySelector('[data-overlay-board-open="modal"]')
        if (!modalBtn) return
        if (modalBtn.dataset.listenerAdded) return

        const modalId = modalBtn.dataset.overlayModalId
        const modal = modalId ? document.getElementById(modalId) : null
        const modalHost = modal?.querySelector('[data-overlay-modal-host]')
        if (!modal || !modalHost) return

        const resizeModalBoard = () => {
          if (!board.classList.contains('overlay-board--modal')) return
          const baseW = Number(board.dataset.baseWidth) || defaultDims.default.width
          const baseH = Number(board.dataset.baseHeight) || defaultDims.default.height
          const boardRatio = baseW / baseH
          const toolbarWidth = toolbar?.offsetWidth || 0
          const maxWidthByHeight = (window.innerHeight - 200) * boardRatio
          const maxWidthByWindow = Math.max(0, window.innerWidth - 64 - toolbarWidth)
          const maxWidth = Math.min(maxWidthByWindow || maxWidthByHeight, maxWidthByHeight)
          board.style.maxWidth = `${Math.max(280, Math.floor(maxWidth))}px`
          board.style.width = '100%'
          if (board._overlayRecalc) board._overlayRecalc()
        }

        modal.addEventListener('shown.bs.modal', () => {
          resizeModalBoard()
        })

        modal.addEventListener('hide.bs.modal', () => {
          const active = document.activeElement
          if (active && modal.contains(active)) {
            active.blur()
            const fallback = board._overlayLastFocus || modalBtn
            if (fallback && typeof fallback.focus === 'function') {
              try {
                fallback.focus({ preventScroll: true })
              } catch {
                fallback.focus()
              }
            }
          }
        })

        modal.addEventListener('hidden.bs.modal', () => {
          if (board._overlayOriginParent) {
            board._overlayOriginParent.insertBefore(board, board._overlayPlaceholder || null)
          }
          if (board._overlayPlaceholder && board._overlayPlaceholder.parentNode) {
            board._overlayPlaceholder.parentNode.removeChild(board._overlayPlaceholder)
          }
          board._overlayOriginParent = null
          board._overlayPlaceholder = null
          if (board._overlayModalLayout && board._overlayModalLayout.parentNode) {
            board._overlayModalLayout.parentNode.removeChild(board._overlayModalLayout)
          }
          board._overlayModalLayout = null
          if (toolbar) {
            if (toolbar._overlayOriginParent) {
              toolbar._overlayOriginParent.insertBefore(toolbar, toolbar._overlayPlaceholder || null)
            }
            if (toolbar._overlayPlaceholder && toolbar._overlayPlaceholder.parentNode) {
              toolbar._overlayPlaceholder.parentNode.removeChild(toolbar._overlayPlaceholder)
            }
            toolbar._overlayOriginParent = null
            toolbar._overlayPlaceholder = null
            toolbar.classList.remove('overlay-board-toolbar--modal')
          }
          board.classList.remove('overlay-board--modal')
          board.style.maxWidth = ''
          board.style.width = ''
          if (board._overlayRecalc) board._overlayRecalc()
        })

        modalBtn.addEventListener('click', () => {
          if (!board.parentNode) return
          const lastFocus = document.activeElement
          if (lastFocus && typeof lastFocus.focus === 'function') {
            board._overlayLastFocus = lastFocus
          }
          const placeholder = document.createElement('div')
          placeholder.className = 'overlay-board-placeholder'
          placeholder.style.height = `${board.offsetHeight}px`
          board._overlayOriginParent = board.parentNode
          board._overlayPlaceholder = placeholder
          board.parentNode.insertBefore(placeholder, board)
          const modalLayout = document.createElement('div')
          modalLayout.className = 'overlay-board-modal-layout'
          if (toolbar && toolbar.parentNode) {
            const toolbarPlaceholder = document.createElement('div')
            toolbarPlaceholder.className = 'overlay-board-toolbar-placeholder'
            toolbar._overlayOriginParent = toolbar.parentNode
            toolbar._overlayPlaceholder = toolbarPlaceholder
            toolbar.parentNode.insertBefore(toolbarPlaceholder, toolbar)
            toolbar.classList.add('overlay-board-toolbar--modal')
            modalLayout.appendChild(toolbar)
          }
          modalLayout.appendChild(board)
          modalHost.replaceChildren()
          modalHost.appendChild(modalLayout)
          board._overlayModalLayout = modalLayout
          board.classList.add('overlay-board--modal')
          resizeModalBoard()
          if (window.bootstrap && window.bootstrap.Modal) {
            const modalInstance = window.bootstrap.Modal.getOrCreateInstance(modal)
            modalInstance.show()
          }
        })

        window.addEventListener('resize', resizeModalBoard)
        modalBtn.dataset.listenerAdded = 'true'
      }

      setupModalCanvas()
    })
  },

  initializeJumpButtons: function (scope) {
    const root = scope || document
    const buttons = root.querySelectorAll('.overlay-jump-button')

    buttons.forEach(button => {
      if (button.dataset.jumpBound === 'true') return
      button.dataset.jumpBound = 'true'

      const targetId = button.dataset.jumpTarget
      const target = targetId ? document.getElementById(targetId) : null
      if (!target) return
      const openAccordionAncestors = (node) => {
        if (!node) return
        const collapses = []
        let current = node
        while (current) {
          if (current.classList && current.classList.contains('accordion-collapse')) {
            collapses.push(current)
          }
          current = current.parentElement
        }
        collapses.reverse().forEach(collapse => {
          if (collapse.classList.contains('show')) return
          if (window.bootstrap && window.bootstrap.Collapse) {
            const instance = window.bootstrap.Collapse.getOrCreateInstance(collapse, { toggle: false })
            instance.show()
            return
          }
          const headerBtn = collapse.closest('.accordion-item')?.querySelector('.accordion-header .accordion-button')
          headerBtn?.click()
        })
      }

      button.addEventListener('click', (event) => {
        event.preventDefault()
        event.stopPropagation()
        openAccordionAncestors(target)
        window.setTimeout(() => {
          target.scrollIntoView({ behavior: 'smooth', block: 'center' })
          const overlayGroup = button.closest('.template-toggle-group')
          const overlayId = overlayGroup?.dataset?.overlayTemplate || button.dataset.overlayId
          const overlayToggle = overlayGroup?.querySelector('.overlay-toggle')
          if (overlayId && overlayToggle) {
            if (!overlayToggle.checked) {
              overlayToggle.checked = true
              overlayToggle.dispatchEvent(new Event('change', { bubbles: true }))
            }
            const board = document.getElementById(targetId) || target.closest('.overlay-board')
            if (board && typeof board._overlaySelectById === 'function') {
              window.setTimeout(() => {
                board._overlaySelectById(overlayId)
              }, 50)
            }
          }
        }, 150)
      })
    })
  }
}

function bootstrapOverlayHandler () {
  const separatorPlaceholders = document.querySelectorAll('[data-separator-placeholder-wrapper="true"]')

  separatorPlaceholders.forEach(wrapper => {
    const libraryId = String(wrapper.dataset.libraryPrefix || '').trim()
    const isMovie = wrapper.dataset.libraryType === 'movie'
    if (!libraryId) return

    // 1. Initialize overlay dropdowns and separator preview
    OverlayHandler.initializeOverlays(libraryId, isMovie)
    OverlayHandler.syncSeparatorPlaceholderFields(wrapper, {
      show: String(document.querySelector(`[name="${libraryId}-template_variables[use_separator]"]`)?.value || '').trim() !== 'none'
    })
  })

  // 2. Sync parent/child toggle checked state
  setupParentChildToggleSync()

  // 3. Toggle child wrapper visibility for both collections and overlays
  document.querySelectorAll('input[data-template-group]').forEach(parent => {
    const parentId = parent.id
    const childWrapper = document.querySelector(`.child-toggle-wrapper[data-toggle-parent="${parentId}"]`)
    if (!childWrapper) return

    // Initial visibility
    childWrapper.style.display = parent.checked ? '' : 'none'

    // Toggle visibility on change
    parent.addEventListener('change', () => {
      childWrapper.style.display = parent.checked ? '' : 'none'
    })
  })

  // 4. Initialize overlay previews (combined + per-overlay)
  OverlayHandler.initializeOverlayBoards()
  OverlayHandler.initializeOverlayPositioners()
  OverlayHandler.initializeJumpButtons()
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bootstrapOverlayHandler)
} else {
  bootstrapOverlayHandler()
}

function setupParentChildToggleSync () {
  let syncing = false

  const syncOverlayDetails = (toggle) => {
    if (typeof toggleOverlayTemplateSection === 'function' && toggle?.classList?.contains('overlay-toggle')) {
      toggleOverlayTemplateSection(toggle)
    }
  }

  const parents = document.querySelectorAll('.template-parent-toggle')

  parents.forEach(parent => {
    if (parent.dataset.parentSyncBound === 'true') return
    parent.dataset.parentSyncBound = 'true'

    const groupId = parent.dataset.templateGroup
    const wrapper = document.querySelector(`[data-toggle-parent="${groupId}"]`)
    const isRadioStyle = parent.type === 'radio' || parent.dataset.radioGroup === 'true'
    if (isRadioStyle) {
      parent.dataset.wasChecked = parent.checked ? 'true' : 'false'
    }

    const groupName = parent.name
    const childToggles = wrapper?.querySelectorAll('.template-child-toggle') || []

    parent.addEventListener('click', () => {
      if (syncing) return
      syncing = true

      const isChecked = parent.checked

      if (isRadioStyle) {
        const groupParents = document.querySelectorAll(`input[name="${groupName}"]`)

        groupParents.forEach(other => {
          if (other !== parent) {
            other.checked = false
            other.dataset.wasChecked = 'false'
            syncOverlayDetails(other)
            if (other.classList.contains('overlay-toggle')) {
              other.dispatchEvent(new Event('change', { bubbles: true }))
            }

            const otherWrapper = document.querySelector(`[data-toggle-parent="${other.dataset.templateGroup}"]`)
            const otherChildren = otherWrapper?.querySelectorAll('.template-child-toggle') || []
            otherChildren.forEach(child => {
              child.checked = false
              child.dispatchEvent(new Event('change', { bubbles: true }))
            })
            if (otherWrapper) otherWrapper.style.display = 'none'
          }
        })

        if (isChecked && parent.dataset.wasChecked === 'true') {
          // Toggle OFF previously checked pseudo-radio
          parent.checked = false
          parent.dataset.wasChecked = 'false'
          if (wrapper) wrapper.style.display = 'none'
          childToggles.forEach(child => {
            child.checked = false
            child.dispatchEvent(new Event('change', { bubbles: true }))
          })
          syncOverlayDetails(parent)
          if (parent.classList.contains('overlay-toggle')) {
            parent.dispatchEvent(new Event('change', { bubbles: true }))
          }
        } else {
          parent.dataset.wasChecked = 'true'
          if (wrapper) wrapper.style.display = ''
          childToggles.forEach(child => {
            child.checked = true
            child.dispatchEvent(new Event('change', { bubbles: true }))
          })
        }

        // Always sync hidden input after processing toggle group
        setTimeout(() => {
          const groupToggles = document.querySelectorAll(`input[name="${groupName}"][data-radio-group="true"]`)
          const anyChecked = Array.from(groupToggles).some(t => t.checked)
          const selectedToggle = Array.from(groupToggles).find(t => t.checked)
          const hidden = document.querySelector(`input[type="hidden"][name="${groupName}"]`)
          if (hidden) {
            hidden.value = anyChecked ? (selectedToggle?.value || '') : ''
            console.debug(`[SYNC] Hidden input for ${groupName} = "${hidden.value}"`)
          }
        }, 0)
      }

      syncing = false
    })

    // Sync back from children
    childToggles.forEach(child => {
      child.addEventListener('change', () => {
        if (syncing) return
        syncing = true

        const anyChecked = Array.from(childToggles).some(c => c.checked)
        parent.checked = anyChecked
        if (wrapper) wrapper.style.display = anyChecked ? '' : 'none'

        if (!anyChecked) {
          syncOverlayDetails(parent)
          if (parent.classList.contains('overlay-toggle')) {
            parent.dispatchEvent(new Event('change', { bubbles: true }))
          }
        }

        if (!anyChecked && isRadioStyle) {
          parent.dataset.wasChecked = 'false'

          // Clear hidden if no toggle remains selected
          setTimeout(() => {
            const groupToggles = document.querySelectorAll(`input[name="${groupName}"][data-radio-group="true"]`)
            const anyLeftChecked = Array.from(groupToggles).some(t => t.checked)
            const hidden = document.querySelector(`input[type="hidden"][name="${groupName}"]`)
            if (hidden) {
              hidden.value = anyLeftChecked ? (Array.from(groupToggles).find(t => t.checked)?.value || '') : ''
              console.debug(`[SYNC] Hidden input for ${groupName} = "${hidden.value}"`)
            }
          }, 0)
        }

        syncing = false
      })
    })
  })
}

/* global EventHandler, toggleOverlayTemplateSection, FontFace, Image, requestAnimationFrame, boardState, ResizeObserver */

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
        OverlayHandler.toggleImdbPlaceholder(libraryId, isMovie ? 'movie' : 'show', selectedStyle)
        OverlayHandler.updateHiddenInputs(libraryId, isMovie)
        EventHandler.updateAccordionHighlights()
      })

      separatorDropdown.dataset.listenerAdded = true

      // Apply separator logic on initial page load
      const initialSelected = separatorDropdown.value !== 'none'
      OverlayHandler.updateSeparatorToggles(libraryId, initialSelected)
      OverlayHandler.updateSeparatorPreview(fieldId, separatorDropdown.value)
      OverlayHandler.toggleImdbPlaceholder(libraryId, isMovie ? 'movie' : 'show', initialSelected)
      OverlayHandler.updateHiddenInputs(libraryId, isMovie)
      EventHandler.updateAccordionHighlights()
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

    // Clear IMDb placeholder selection if separator is disabled
    if (!isEnabled) {
      const imdbDropdown = document.querySelector(`#${libraryId}-attribute_template_variables_placeholder_imdb_id`)
      if (imdbDropdown) {
        imdbDropdown.value = ''
        const optionsToRemove = [...imdbDropdown.options].slice(1) // skip the first option
        optionsToRemove.forEach(opt => imdbDropdown.remove(opt.index))
      }
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

  toggleImdbPlaceholder: function (libraryId, mediaType, show) {
    const dropdown = document.getElementById(`${libraryId}-attribute_template_variables_placeholder_imdb_id`)
    if (!dropdown) {
      console.error(`[ERROR] IMDb dropdown not found for libraryId: ${libraryId}`)
      return
    }

    const libraryName = dropdown.dataset.libraryId
    const imdbBlock = document.querySelector(`.imdb-placeholder-wrapper[data-library-id="${libraryName}"]`)
    if (!imdbBlock) {
      console.error(`[ERROR] IMDb block not found for libraryName: ${libraryName}`)
      return
    }

    if (show) {
      imdbBlock.classList.remove('visually-hidden')
      const currentValue = dropdown.value
      OverlayHandler.populateImdbDropdown(dropdown, libraryName, mediaType, currentValue)
    } else {
      imdbBlock.classList.add('visually-hidden')
    }
  },

  populateImdbDropdown: function (dropdown, libraryName, mediaType, placeholderId = '') {
    console.log(`[DEBUG] Fetching top IMDb items for "${libraryName}" (type=${mediaType})`)

    const url = `/get_top_imdb_items/${encodeURIComponent(libraryName)}?type=${mediaType}` + (placeholderId ? `&placeholder_id=${placeholderId}` : '')

    fetch(url)
      .then(res => res.json())
      .then(data => {
        if (data.status === 'success') {
          // Clear existing options
          dropdown.innerHTML = ''

          // Add "None" option
          const noneOption = document.createElement('option')
          noneOption.value = ''
          noneOption.textContent = 'None'
          dropdown.appendChild(noneOption)

          // Add items
          data.items.forEach(item => {
            const option = document.createElement('option')
            option.value = item.id
            option.textContent = `${item.title} (${item.id})`
            dropdown.appendChild(option)
          })

          // Insert saved placeholder item if returned separately
          if (data.saved_item) {
            const savedOption = document.createElement('option')
            savedOption.value = data.saved_item.id
            savedOption.textContent = `${data.saved_item.title} (${data.saved_item.id}) (Not in Top 25)`
            dropdown.appendChild(savedOption)
          }

          // Restore previous selection
          dropdown.value = placeholderId || ''
        } else {
          console.warn(`Failed to load IMDb titles for ${libraryName}:`, data.message)
        }
      })
      .catch(err => {
        console.error(`IMDb fetch failed for ${libraryName}:`, err)
      })
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
          } catch (e) {
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
        return el.type === 'number' ? Number(el.value) || defaultVal : el.value || defaultVal
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
      return {
        text: getVal('text', ''),
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

      const text = getVal('text_airing', 'AIRING')
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

    const syncAudioCodecBackdropHeight = (cfg, emit = true) => {
      if (cfg.id !== 'overlay_audio_codec') return
      const style = (cfg.styleInput?.value || 'compact').toLowerCase()
      const height = style === 'standard' ? 189 : 105
      setBackdropHeight(cfg, height, emit)
    }

    const syncResolutionBackdropHeight = (cfg, emit = true) => {
      if (cfg.id !== 'overlay_resolution') return
      const toggle = getTemplateInput(cfg, 'use_edition')
      const useEdition = toggle ? toggle.checked : true
      const height = useEdition ? 189 : 105
      setBackdropHeight(cfg, height, emit)
    }

    const syncResolutionEditionVisibility = (cfg, emit = true) => {
      if (cfg.id !== 'overlay_resolution') return
      if (!cfg.container) return
      const templateName = cfg.container.dataset.overlayTemplate
      if (!templateName) return
      const toggle = getTemplateInput(cfg, 'use_edition')
      const useEdition = toggle ? toggle.checked : true
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
          group.classList.toggle('d-none', useEdition)
        }
        input.disabled = useEdition
        if (emit) {
          input.dispatchEvent(new Event('change', { bubbles: true }))
        }
      })
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
    const FLAG_PREVIEW_ITEMS = [
      {
        text: 'EN',
        round: 'https://raw.githubusercontent.com/Kometa-Team/Kometa/refs/heads/nightly/defaults/overlays/images/flag/round/us.png',
        square: 'https://raw.githubusercontent.com/Kometa-Team/Kometa/refs/heads/nightly/defaults/overlays/images/flag/square/us.png'
      },
      {
        text: 'DE',
        round: 'https://raw.githubusercontent.com/Kometa-Team/Kometa/refs/heads/nightly/defaults/overlays/images/flag/round/de.png',
        square: 'https://raw.githubusercontent.com/Kometa-Team/Kometa/refs/heads/nightly/defaults/overlays/images/flag/square/de.png'
      },
      {
        text: 'FR',
        round: 'https://raw.githubusercontent.com/Kometa-Team/Kometa/refs/heads/nightly/defaults/overlays/images/flag/round/fr.png',
        square: 'https://raw.githubusercontent.com/Kometa-Team/Kometa/refs/heads/nightly/defaults/overlays/images/flag/square/fr.png'
      }
    ]

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

    const enhanceRatingImageSelects = (scope) => {
      const root = scope || document
      root.querySelectorAll('select[data-rating-image-select="true"]').forEach(select => {
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
        caret.innerHTML = '<i class="bi bi-chevron-down"></i>'

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
        allEl.innerHTML = '<div class="text-muted">No badge options found.</div>'
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
              .filter(label => label && label !== '—' && label !== 'Pick a source')
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
        allEl.innerHTML = `
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
      }

      hydrateRatingMappingSamples(cfg, token)
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
      const urls = getRatingSampleImageUrls(imageVal, labelVal, sample)
      if (!urls.length) return null
      let img
      let useStarFallback = false
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
      const boxWidth = Math.max(1, Number(vars.back_width) || 160)
      const boxHeight = Math.max(1, Number(vars.back_height) || 160)
      const canvas = document.createElement('canvas')
      canvas.width = Math.ceil(boxWidth)
      canvas.height = Math.ceil(boxHeight)
      const ctx = canvas.getContext('2d')
      if (!ctx) return null
      const fill = parseHexColor(vars.back_color, { r: 0, g: 0, b: 0, a: 0 })
      const stroke = parseHexColor(vars.back_line_color, { r: 0, g: 0, b: 0, a: 0 })
      const lineWidth = Math.max(0, Number(vars.back_line_width) || 0)
      const radius = Math.max(0, Number(vars.back_radius) || 0)
      const innerPad = Number.isFinite(Number(vars.back_padding))
        ? Math.max(0, Number(vars.back_padding))
        : Math.round(boxHeight * 0.08)

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
        if (!source) {
          setStatusIcon(statusEl, 'neutral', `${slot.label} (${ratingLabel} + ${imageLabel}) has no matching rating source.`)
          return
        }
        const groupLabel = RATING_GROUP_LABEL_MAP[group] || group
        const toggleLabel = getMassToggleLabel(libraryId, group, source) || RATING_SOURCE_LABEL_MAP[source] || source
        let message = `${slot.label} (${ratingLabel} + ${imageLabel}) → ${groupLabel}: ${toggleLabel}`
        const service = RATING_SOURCE_SERVICE_MAP[source] || null
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

    const setMassRatingSource = (libraryId, prefix, source) => {
      if (!libraryId || !prefix) return
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
    }

    const syncRatingSources = (cfg, slot) => {
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
      setMassRatingSource(libraryId, group, source)
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
      input.innerHTML = ''
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
        font_size: 55,
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
        const urls = getRatingSampleImageUrls(imageVal, label, sample)
        if (!urls.length) continue
        try {
          const img = await loadImageWithFallback(urls)
          const text = sample.text || 'NR'
          items.push({
            img,
            text,
            fontFile: getSlotValue(slot.fontKey, fontDefaults.font),
            fontSize: getSlotValue(slot.fontSizeKey, fontDefaults.font_size),
            fontColor: getSlotValue(slot.fontColorKey, fontDefaults.font_color),
            strokeWidth: getSlotValue(slot.strokeWidthKey, fontDefaults.stroke_width),
            strokeColor: getSlotValue(slot.strokeColorKey, fontDefaults.stroke_color)
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
      const boxWidth = Math.max(1, Number(vars.back_width) || 160)
      const boxHeight = Math.max(1, Number(vars.back_height) || 160)
      const gap = Math.max(6, Math.round(boxHeight * 0.08))
      const canvas = document.createElement('canvas')
      canvas.width = Math.ceil(boxWidth)
      canvas.height = Math.ceil((boxHeight * items.length) + (gap * Math.max(0, items.length - 1)))
      const ctx = canvas.getContext('2d')
      if (!ctx) return resolveOverlayImage(cfg)

      const fill = parseHexColor(vars.back_color, { r: 0, g: 0, b: 0, a: 0 })
      const stroke = parseHexColor(vars.back_line_color, { r: 0, g: 0, b: 0, a: 0 })
      const lineWidth = Math.max(0, Number(vars.back_line_width) || 0)
      const radius = Math.max(0, Number(vars.back_radius) || 0)
      const innerPad = Number.isFinite(Number(vars.back_padding))
        ? Math.max(0, Number(vars.back_padding))
        : Math.round(boxHeight * 0.08)

      ctx.textAlign = 'center'
      ctx.textBaseline = 'alphabetic'

      items.forEach((item, idx) => {
        const boxTop = (boxHeight + gap) * idx
        drawRoundedRect(ctx, 0, boxTop, boxWidth, boxHeight, radius)
        if (fill.a > 0) {
          ctx.fillStyle = `rgba(${fill.r}, ${fill.g}, ${fill.b}, ${fill.a})`
          ctx.fill()
        }
        if (lineWidth > 0 && stroke.a > 0) {
          const inset = lineWidth / 2
          const strokeRadius = Math.max(0, radius - inset)
          drawRoundedRect(ctx, inset, boxTop + inset, boxWidth - (inset * 2), boxHeight - (inset * 2), strokeRadius)
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

        const textBottom = boxTop + boxHeight - innerPad
        ctx.font = `700 ${fontSize}px "${fontFamily}"`
        drawTextWithStroke(ctx, item.text, boxWidth / 2, textBottom, fontColor, strokeColor, strokeWidth)

        const iconMaxHeight = Math.max(1, boxHeight - fontSize - (innerPad * 2))
        const iconMaxWidth = Math.max(1, boxWidth - (innerPad * 2))
        const scale = Math.min(iconMaxWidth / item.img.width, iconMaxHeight / item.img.height, 1)
        const drawW = item.img.width * scale
        const drawH = item.img.height * scale
        const drawX = (boxWidth - drawW) / 2
        const drawY = boxTop + innerPad + ((iconMaxHeight - drawH) / 2)
        ctx.drawImage(item.img, drawX, drawY, drawW, drawH)
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

      const items = FLAG_PREVIEW_ITEMS
      let images = []
      try {
        images = await Promise.all(
          items.map(item => loadImage(useSquareFlags ? item.square : item.round))
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
      const toggle = getTemplateInput(cfg, 'use_edition')
      const useEdition = toggle ? toggle.checked : true
      const baseSrc = resolveOverlayImage(cfg)
      if (!useEdition || !cfg.edition?.image) return baseSrc

      try {
        const [baseImg, editionImg] = await Promise.all([
          loadImage(baseSrc),
          loadImage(cfg.edition.image)
        ])
        const spacing = Number(cfg.edition?.spacing) || 15
        const canvas = document.createElement('canvas')
        canvas.width = Math.max(baseImg.width, editionImg.width)
        canvas.height = baseImg.height + spacing + editionImg.height
        const ctx = canvas.getContext('2d')
        if (!ctx) return baseSrc
        ctx.drawImage(baseImg, 0, 0)
        ctx.drawImage(editionImg, 0, baseImg.height + spacing)
        return canvas.toDataURL('image/png')
      } catch (err) {
        console.warn('[OverlayBoards] Failed to build resolution composite', err)
        return baseSrc
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

    const buildCommonsenseDataUrl = async (cfg) => {
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

      const baseImg = cfg.image
      const textVal = getVal('text', 17)
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
      const textString = `${textVal}${postText || ''}`
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
      const runtimeMinutes = 93
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
      const getJumpTargetId = (overlayId) => (overlayId ? `${libId}-${overlayType}-${overlayId}-overlay-config` : '')

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
          const layers = Array.from(canvas.querySelectorAll('.overlay-board-layer'))
          for (const layer of layers) {
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

      const applyVisibility = (cfg, layer) => {
        const toggle = cfg.toggle
        const visible = !toggle || toggle.checked
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
        const layer = layers.get(cfg.id)
        if (!layer) return
        const { hInput, vInput } = getInputs(cfg)
        if (!hInput || !vInput) return

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
        const baseLayer = layers.get(cfg.id)
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
        if (layers.has(cfg.id)) return layers.get(cfg.id)
        const layer = document.createElement('img')
        layer.className = 'overlay-board-layer'
        layer.alt = cfg.id
        layer.dataset.overlayId = cfg.id
        layers.set(cfg.id, layer)
        canvas.appendChild(layer)

        const handleLoad = () => {
          cfg.naturalWidth = layer.naturalWidth || cfg.naturalWidth
          cfg.naturalHeight = layer.naturalHeight || cfg.naturalHeight
          applyPosition(cfg)
        }

        layer.addEventListener('load', handleLoad)

        let initialSrc = resolveOverlayImage(cfg)
        if (isFlagsOverlay(cfg)) {
          updateFlagsLayer(cfg, layer)
        } else if (BACKDROP_IMAGE_OVERLAYS.has(cfg.id)) {
          buildBackdropDataUrl(cfg).then(dataUrl => {
            layer.src = dataUrl
            applyPosition(cfg)
          })
        } else if (cfg.id && cfg.id.startsWith('overlay_content_rating_') && cfg.id !== 'overlay_content_rating_commonsense') {
          buildBackdropDataUrl(cfg).then(dataUrl => {
            layer.src = dataUrl
            applyPosition(cfg)
          })
        } else if (cfg.id === 'overlay_content_rating_commonsense') {
          buildCommonsenseDataUrl(cfg).then(dataUrl => {
            buildBackdropDataUrl(cfg, dataUrl).then(backdropUrl => {
              layer.src = backdropUrl
              applyPosition(cfg)
            })
          })
        } else if (cfg.id === 'overlay_runtimes') {
          initialSrc = buildRuntimeDataUrl(cfg)
          if (BACKDROP_TEXT_OVERLAYS.has(cfg.id)) {
            buildBackdropDataUrl(cfg, initialSrc).then(backdropUrl => {
              layer.src = backdropUrl
              applyPosition(cfg)
            })
          }
        } else if (cfg.id === 'overlay_status') {
          initialSrc = buildSimpleTextDataUrl(cfg, getStatusTextVars(cfg))
          if (BACKDROP_TEXT_OVERLAYS.has(cfg.id)) {
            buildBackdropDataUrl(cfg, initialSrc).then(backdropUrl => {
              layer.src = backdropUrl
              applyPosition(cfg)
            })
          }
        } else if (cfg.id === 'overlay_episode_info') {
          initialSrc = buildSimpleTextDataUrl(cfg, getSimpleTextVars(cfg))
        }
        layer.src = initialSrc
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
              buildBackdropDataUrl(cfg).then(dataUrl => {
                layer.src = dataUrl
                applyPosition(cfg)
              })
            }
            colorInput.addEventListener('change', refreshColor)
            colorInput.addEventListener('input', refreshColor)
          }
          if (cfg.id !== 'overlay_content_rating_commonsense') {
            const refreshBackdrop = () => {
              buildBackdropDataUrl(cfg).then(dataUrl => {
                layer.src = dataUrl
                applyPosition(cfg)
              })
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
            cfg.edition.toggle.addEventListener('change', () => {
              syncResolutionBackdropHeight(cfg)
              syncResolutionEditionVisibility(cfg)
              if (BACKDROP_IMAGE_OVERLAYS.has(cfg.id)) {
                buildBackdropDataUrl(cfg).then(dataUrl => {
                  layer.src = dataUrl
                  applyPosition(cfg)
                })
              }
              applyEditionPosition(cfg)
            })
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
            id: `${cfg.id}__edition`,
            image: editionImage,
            toggle: editionToggle,
            naturalWidth: null,
            naturalHeight: null,
            layer: null,
            spacing: 15
          }
        }
        syncAudioCodecBackdropHeight(cfg, false)
        syncResolutionBackdropHeight(cfg, false)
        syncResolutionEditionVisibility(cfg, false)
        configs.push(cfg)
        configsById.set(cfg.id, cfg)
        const layer = addOverlayLayer(cfg)

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

          const templateName = cfg.container.dataset.overlayTemplate
          const textSelectors = [
            `[name="${templateName}[text]"]`,
            `[name="${templateName}[font]"]`,
            `[name="${templateName}[font_size]"]`,
            `[name="${templateName}[font_color]"]`,
            `[name="${templateName}[stroke_width]"]`,
            `[name="${templateName}[stroke_color]"]`
          ]
          if (BACKDROP_TEXT_OVERLAYS.has(cfg.id)) {
            textSelectors.push(
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

          const templateName = cfg.container.dataset.overlayTemplate
          const statusSelectors = [
            `[name="${templateName}[text_airing]"]`,
            `[name="${templateName}[text_returning]"]`,
            `[name="${templateName}[text_canceled]"]`,
            `[name="${templateName}[text_ended]"]`,
            `[name="${templateName}[font]"]`,
            `[name="${templateName}[font_size]"]`,
            `[name="${templateName}[font_color]"]`,
            `[name="${templateName}[stroke_width]"]`,
            `[name="${templateName}[stroke_color]"]`
          ]
          if (BACKDROP_TEXT_OVERLAYS.has(cfg.id)) {
            statusSelectors.push(
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
          const inputs = cfg.container.querySelectorAll(statusSelectors.join(', '))
          inputs.forEach(input => {
            input.addEventListener('input', refreshStatus)
            input.addEventListener('change', refreshStatus)
          })
          refreshStatus()
        }

        if (cfg.id === 'overlay_ratings' && layer && cfg.container) {
          const refreshRatings = (event, forceSync = false) => {
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
              slots.forEach(slot => syncRatingSources(cfg, slot))
            }
            const positionInput = cfg.container.querySelector(`[name="${templateName}[horizontal_position]"]`)
            if (positionInput) {
              const raw = (positionInput.value || positionInput.dataset?.default || '').toString().trim().toLowerCase()
              if (raw === 'left' || raw === 'center' || raw === 'right') {
                const { vAlign } = parseOrigin(cfg.origin || '')
                let nextOrigin = ''
                if (vAlign === 'center') {
                  nextOrigin = raw === 'center' ? 'center' : `center_${raw}`
                } else {
                  nextOrigin = raw === 'center' ? vAlign : `${vAlign}_${raw}`
                }
                if (nextOrigin && cfg.origin !== nextOrigin) {
                  cfg.origin = nextOrigin
                }
              }
            }
            applyRatingFontDefaults(cfg)
            updateRatingSyncStatus(cfg)
            renderRatingMappingModal(cfg)
            buildBackdropDataUrl(cfg).then(dataUrl => {
              layer.src = dataUrl
              applyPosition(cfg)
            })
          }
          const templateName = cfg.container.dataset.overlayTemplate
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
            `[name="${templateName}[rating1]"]`,
            `[name="${templateName}[rating1_image]"]`,
            `[name="${templateName}[rating1_font]"]`,
            `[name="${templateName}[rating1_font_size]"]`,
            `[name="${templateName}[rating1_font_color]"]`,
            `[name="${templateName}[rating1_stroke_width]"]`,
            `[name="${templateName}[rating1_stroke_color]"]`,
            `[name="${templateName}[rating2]"]`,
            `[name="${templateName}[rating2_image]"]`,
            `[name="${templateName}[rating2_font]"]`,
            `[name="${templateName}[rating2_font_size]"]`,
            `[name="${templateName}[rating2_font_color]"]`,
            `[name="${templateName}[rating2_stroke_width]"]`,
            `[name="${templateName}[rating2_stroke_color]"]`,
            `[name="${templateName}[rating3]"]`,
            `[name="${templateName}[rating3_image]"]`,
            `[name="${templateName}[rating3_font]"]`,
            `[name="${templateName}[rating3_font_size]"]`,
            `[name="${templateName}[rating3_font_color]"]`,
            `[name="${templateName}[rating3_stroke_width]"]`,
            `[name="${templateName}[rating3_stroke_color]"]`,
            `[name="${templateName}[horizontal_position]"]`
          ]
          const inputs = cfg.container.querySelectorAll(ratingSelectors.join(', '))
          inputs.forEach(input => {
            input.addEventListener('input', refreshRatings)
            input.addEventListener('change', refreshRatings)
          })
          if (cfg.toggle && cfg.toggle.dataset.ratingSyncBound !== 'true') {
            cfg.toggle.dataset.ratingSyncBound = 'true'
            cfg.toggle.addEventListener('change', () => {
              if (cfg.toggle.checked) {
                refreshRatings(null, true)
              }
            })
          }
          if (cfg.toggle && cfg.toggle.checked) {
            refreshRatings(null, true)
          } else {
            refreshRatings()
          }
        }

        if (isFlagsOverlay(cfg) && layer && cfg.container) {
          const templateName = cfg.container.dataset.overlayTemplate
          const refreshFlags = () => updateFlagsLayer(cfg, layer)
          const flagSelectors = [
            `[name="${templateName}[style]"]`,
            `[name="${templateName}[hide_text]"]`,
            `[name="${templateName}[use_lowercase]"]`,
            `[name="${templateName}[group_alignment]"]`,
            `[name="${templateName}[offset]"]`,
            `[name="${templateName}[font]"]`,
            `[name="${templateName}[font_size]"]`,
            `[name="${templateName}[font_color]"]`,
            `[name="${templateName}[stroke_width]"]`,
            `[name="${templateName}[stroke_color]"]`,
            `[name="${templateName}[back_color]"]`,
            `[name="${templateName}[back_height]"]`,
            `[name="${templateName}[back_width]"]`,
            `[name="${templateName}[back_line_color]"]`,
            `[name="${templateName}[back_line_width]"]`,
            `[name="${templateName}[back_padding]"]`,
            `[name="${templateName}[back_radius]"]`
          ]
          const inputs = cfg.container.querySelectorAll(flagSelectors.join(', '))
          inputs.forEach(input => {
            input.addEventListener('input', refreshFlags)
            input.addEventListener('change', refreshFlags)
          })
          const sizeInput = cfg.container.querySelector(`[name="${templateName}[size]"]`)
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
          const templateName = cfg.container.dataset.overlayTemplate
          const inputs = cfg.container.querySelectorAll(
            `[name="${templateName}[back_align]"], [name="${templateName}[back_color]"], [name="${templateName}[back_height]"], [name="${templateName}[back_width]"], [name="${templateName}[back_line_color]"], [name="${templateName}[back_line_width]"], [name="${templateName}[back_padding]"], [name="${templateName}[back_radius]"]`
          )
          inputs.forEach(input => {
            input.addEventListener('input', refreshBackdrop)
            input.addEventListener('change', refreshBackdrop)
          })
          refreshBackdrop()
        }

        if (cfg.id === 'overlay_content_rating_commonsense' && layer && cfg.container) {
          const refreshCommonsense = () => {
            buildCommonsenseDataUrl(cfg).then(dataUrl => {
              buildBackdropDataUrl(cfg, dataUrl).then(backdropUrl => {
                layer.src = backdropUrl
                applyPosition(cfg)
              })
            })
          }
          const templateName = cfg.container.dataset.overlayTemplate
          const inputs = cfg.container.querySelectorAll(
            `[name="${templateName}[text]"], [name="${templateName}[post_text]"], [name="${templateName}[addon_offset]"], [name="${templateName}[font]"], [name="${templateName}[font_size]"], [name="${templateName}[font_color]"], [name="${templateName}[stroke_width]"], [name="${templateName}[stroke_color]"], [name="${templateName}[back_align]"], [name="${templateName}[back_color]"], [name="${templateName}[back_height]"], [name="${templateName}[back_width]"], [name="${templateName}[back_line_color]"], [name="${templateName}[back_line_width]"], [name="${templateName}[back_padding]"], [name="${templateName}[back_radius]"]`
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
          const ratio = baseW / baseH
          const toolbarWidth = toolbar?.offsetWidth || 0
          const maxWidthByHeight = (window.innerHeight - 200) * ratio
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
              } catch (err) {
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
          modalHost.innerHTML = ''
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
          const overlayId = button.dataset.overlayId
          const overlayToggle = button.closest('.template-toggle-group')?.querySelector('.overlay-toggle')
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

document.addEventListener('DOMContentLoaded', function () {
  const imdbDropdowns = document.querySelectorAll('.placeholder-imdb-dropdown')

  imdbDropdowns.forEach(dropdown => {
    const libraryId = dropdown.id.split('-attribute_template_variables')[0]
    const isMovie = dropdown.dataset.libraryType === 'movie'
    const libraryName = dropdown.dataset.libraryId

    // 1. Initialize overlay dropdowns and separator preview
    OverlayHandler.initializeOverlays(libraryId, isMovie)

    // 2. Populate IMDb dropdown options
    const currentValue = dropdown.value
    OverlayHandler.populateImdbDropdown(dropdown, libraryName, isMovie ? 'movie' : 'show', currentValue)
  })

  // 3. Sync parent/child toggle checked state
  setupParentChildToggleSync()

  // 4. Toggle child wrapper visibility for both collections and overlays
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

  // 5. Initialize overlay previews (combined + per-overlay)
  OverlayHandler.initializeOverlayBoards()
  OverlayHandler.initializeOverlayPositioners()
  OverlayHandler.initializeJumpButtons()
})

// eslint-disable-next-line no-unused-vars
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

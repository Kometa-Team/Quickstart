/* global EventHandler, toggleOverlayTemplateSection, FontFace, Image */

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

          const deltaX = (e.clientX - start.x) / scaleX
          const deltaY = (e.clientY - start.y) / scaleY

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

    // Runtime overlay specific: ensure selected font is loaded before drawing
    const runtimeFontCache = new Map()
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
      const face = new FontFace(family, `url(/static/fonts/${encodeURIComponent(file)})`)
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
        font_color: getVal('font_color', '#FFFFFF')
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
        font_color: getVal('font_color', '#FFFFFFFF')
      }
    }

    const loadImage = (src) => {
      return new Promise((resolve, reject) => {
        const img = new Image()
        img.crossOrigin = 'anonymous'
        img.onload = () => resolve(img)
        img.onerror = (err) => reject(err)
        img.src = src
      })
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

      const fontFamily = (await ensureRuntimeFontLoaded(font)) || normalizeFontFile(font).family || 'Inter-Medium'

      const img = await loadImage(baseImg)
      const canvas = document.createElement('canvas')
      const ctx = canvas.getContext('2d')
      ctx.font = `${fontSize}px "${fontFamily}"`
      const textString = `${textVal}${postText || ''}`
      const textMetrics = ctx.measureText(textString)
      const textWidth = Math.ceil(textMetrics.width)
      const textHeight = Math.ceil(
        (textMetrics.actualBoundingBoxAscent || fontSize * 0.8) +
        (textMetrics.actualBoundingBoxDescent || fontSize * 0.2)
      )

      canvas.width = img.width + addonOffset + textWidth
      canvas.height = Math.max(img.height, textHeight)

      ctx.drawImage(img, 0, 0)
      ctx.font = `${fontSize}px "${fontFamily}"`
      ctx.fillStyle = fontColor
      ctx.textBaseline = 'middle'
      const textY = canvas.height / 2
      ctx.fillText(textString, img.width + addonOffset, textY)

      return canvas.toDataURL('image/png')
    }

    const buildRuntimeDataUrl = (cfg, loadedFamily = null) => {
      const { text, format, font, font_size: fontSize, font_color: fontColor } = getRuntimeVars(cfg)
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
      const metrics = measureCtx.measureText(fullText)
      const textWidth = Math.ceil(metrics.width)
      const textHeight = Math.ceil(
        (metrics.actualBoundingBoxAscent || fontSize * 0.8) +
        (metrics.actualBoundingBoxDescent || fontSize * 0.2)
      )
      const padding = 10
      const canvasWidth = textWidth + padding * 2
      const canvasHeight = textHeight + padding * 2

      const canvas = document.createElement('canvas')
      canvas.width = canvasWidth
      canvas.height = canvasHeight
      const ctx = canvas.getContext('2d')
      if (!ctx) return cfg.image

      ctx.clearRect(0, 0, canvas.width, canvas.height)
      ctx.fillStyle = fontColor || '#FFFFFF'
      const family = loadedFamily || normalizedFamily || 'Inter'
      ctx.font = `${fontSize || 55}px "${family}"`
      ctx.textAlign = 'right'
      ctx.textBaseline = 'bottom'
      ctx.fillText(fullText, canvas.width - padding, canvas.height - padding)

      // Store natural size so dragging/clamping respects the smaller overlay
      cfg.naturalWidth = canvasWidth
      cfg.naturalHeight = canvasHeight

      return canvas.toDataURL('image/png')
    }

    const buildSimpleTextDataUrl = (cfg, vars, loadedFamily = null) => {
      const { text, font, font_size: fontSize, font_color: fontColor } = vars
      const { family: normalizedFamily } = normalizeFontFile(font)
      const content = text || ''

      const measureCanvas = document.createElement('canvas')
      const measureCtx = measureCanvas.getContext('2d')
      if (!measureCtx) return cfg.image
      measureCtx.font = `${fontSize || 55}px "${loadedFamily || normalizedFamily || 'Inter'}"`
      const metrics = measureCtx.measureText(content)
      const textWidth = Math.ceil(metrics.width)
      const textHeight = Math.ceil(
        (metrics.actualBoundingBoxAscent || fontSize * 0.8) +
        (metrics.actualBoundingBoxDescent || fontSize * 0.2)
      )
      const padding = 10
      const canvasWidth = textWidth + padding * 2
      const canvasHeight = textHeight + padding * 2

      const canvas = document.createElement('canvas')
      canvas.width = canvasWidth
      canvas.height = canvasHeight
      const ctx = canvas.getContext('2d')
      if (!ctx) return cfg.image

      ctx.clearRect(0, 0, canvas.width, canvas.height)
      ctx.fillStyle = fontColor || '#FFFFFFFF'
      const family = loadedFamily || normalizedFamily || 'Inter'
      ctx.font = `${fontSize || 55}px "${family}"`
      ctx.textAlign = 'right'
      ctx.textBaseline = 'bottom'
      ctx.fillText(content, canvas.width - padding, canvas.height - padding)

      cfg.naturalWidth = canvasWidth
      cfg.naturalHeight = canvasHeight
      return canvas.toDataURL('image/png')
    }

    Array.from(root.querySelectorAll('.overlay-board')).forEach(board => {
      if (board.dataset.boardBound === 'true') return
      board.dataset.boardBound = 'true'

      const canvas = board.querySelector('.overlay-board-canvas')
      if (!canvas) return

      const baseWidth = Number(board.dataset.baseWidth) || defaultDims.default.width
      const baseHeight = Number(board.dataset.baseHeight) || defaultDims.default.height
      const ratio = baseWidth / baseHeight
      canvas.style.setProperty('--overlay-board-ratio', `${ratio}`)

      const layers = new Map()
      let writing = false

      const clamp = (val, min, max) => Math.min(Math.max(val, min), max)
      const ensureNumber = (val, fallback = 0) => {
        const num = Number(val)
        return Number.isFinite(num) ? num : fallback
      }

      const getScale = () => {
        const rect = canvas.getBoundingClientRect()
        const computed = window.getComputedStyle(canvas)
        const width = rect.width || canvas.clientWidth || parseFloat(computed.width) || 1
        const height = rect.height || canvas.clientHeight || parseFloat(computed.height) || (width / ratio)
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
      const applyEditionVisibility = (cfg) => {
        if (!cfg.edition || !cfg.edition.layer) return
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
        let start = { x: 0, y: 0, h: 0, v: 0 }

        const onPointerDown = (e) => {
          e.preventDefault()
          layer.setPointerCapture(e.pointerId)
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
          dragging = true
          layer.classList.add('dragging')
        }

        const onPointerMove = (e) => {
          if (!dragging) return
          const { scaleX, scaleY } = getScale()
          const natW = cfg.naturalWidth || layer.naturalWidth || (baseWidth * 0.25)
          const natH = cfg.naturalHeight || layer.naturalHeight || (baseHeight * 0.25)
          const baseW = Number(cfg.baseWidth) || baseWidth
          const baseH = Number(cfg.baseHeight) || baseHeight
          const { hAlign, vAlign } = parseOrigin(cfg.origin)
          const overlayWidthBase = natW
          const overlayHeightBase = natH

          const deltaX = (e.clientX - start.x) / scaleX
          const deltaY = (e.clientY - start.y) / scaleY

          const maxH = Math.max(0, baseWidth - overlayWidthBase)
          const maxV = Math.max(0, baseHeight - overlayHeightBase)

          const nextActualH = clamp(start.h + deltaX, 0, maxH)
          const nextActualV = clamp(start.v + deltaY, 0, maxV)

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
        }

        layer.addEventListener('pointerdown', onPointerDown)
        window.addEventListener('pointermove', onPointerMove)
        window.addEventListener('pointerup', onPointerUp)
      }

      const bindInputs = (cfg) => {
        const { hInput, vInput } = getInputs(cfg)
        const handler = () => {
          if (writing) return
          applyPosition(cfg)
        }
        hInput?.addEventListener('input', handler)
        vInput?.addEventListener('input', handler)
        hInput?.addEventListener('change', handler)
        vInput?.addEventListener('change', handler)
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

      const addOverlayLayer = (cfg) => {
        if (layers.has(cfg.id)) return layers.get(cfg.id)
        const layer = document.createElement('img')
        layer.className = 'overlay-board-layer'
        const initialSrc = cfg.id === 'overlay_runtimes' ? buildRuntimeDataUrl(cfg) : resolveOverlayImage(cfg)
        layer.src = initialSrc
        layer.alt = cfg.id
        layers.set(cfg.id, layer)
        canvas.appendChild(layer)

        layer.addEventListener('load', () => {
          cfg.naturalWidth = layer.naturalWidth || cfg.naturalWidth
          cfg.naturalHeight = layer.naturalHeight || cfg.naturalHeight
          applyPosition(cfg)
        })

        bindDrag(cfg, layer)
        bindToggle(cfg, layer)
        bindInputs(cfg)
        if (cfg.styleInput) {
          cfg.styleInput.addEventListener('change', () => {
            layer.src = resolveOverlayImage(cfg)
          })
        }

        if (cfg.id === 'overlay_runtimes' && cfg.container) {
          const templateName = cfg.container.dataset.overlayTemplate
          const runtimeInputs = cfg.container.querySelectorAll(
            `input[name="${templateName}[text]"], input[name="${templateName}[format]"], input[name="${templateName}[font]"], input[name="${templateName}[font_size]"], input[name="${templateName}[font_color]"], select[name="${templateName}[font]"]`
          )
          const refreshRuntime = () => {
            const { font } = getRuntimeVars(cfg)
            ensureRuntimeFontLoaded(font).then(family => {
              const { family: norm } = normalizeFontFile(font)
              layer.src = buildRuntimeDataUrl(cfg, family || norm)
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
            const refreshColor = () => { layer.src = resolveOverlayImage(cfg) }
            colorInput.addEventListener('change', refreshColor)
            colorInput.addEventListener('input', refreshColor)
          }
        }
        applyPosition(cfg)

        // Optional stacked edition layer (for resolution overlays)
        if (cfg.edition && cfg.edition.image && !cfg.edition.layer) {
          const editionLayer = document.createElement('img')
          editionLayer.className = 'overlay-board-layer'
          editionLayer.src = cfg.edition.image
          editionLayer.alt = `${cfg.id}-edition`
          editionLayer.style.pointerEvents = 'none' // let dragging happen on the base resolution layer
          cfg.edition.layer = editionLayer
          layers.set(cfg.edition.id, editionLayer)
          canvas.appendChild(editionLayer)

          editionLayer.addEventListener('load', () => {
            cfg.edition.naturalWidth = editionLayer.naturalWidth || cfg.edition.naturalWidth
            cfg.edition.naturalHeight = editionLayer.naturalHeight || cfg.edition.naturalHeight
            applyEditionPosition(cfg)
          })

          if (cfg.edition.toggle) {
            cfg.edition.toggle.addEventListener('change', () => applyEditionPosition(cfg))
          }

          applyEditionPosition(cfg)
        }
        return layer
      }

      const libId = board.dataset.libraryId
      const overlayType = board.dataset.overlayType
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
        configs.push(cfg)
        const layer = addOverlayLayer(cfg)

        if (cfg.id === 'overlay_runtimes' && layer) {
          const { font } = getRuntimeVars(cfg)
          ensureRuntimeFontLoaded(font).then(family => {
            const { family: norm } = normalizeFontFile(font)
            layer.src = buildRuntimeDataUrl(cfg, family || norm)
          })
        }

        if ((cfg.id === 'overlay_video_format' || cfg.id === 'overlay_aspect') && layer && cfg.container) {
          const refreshTextOverlay = () => {
            const vars = getSimpleTextVars(cfg)
            ensureRuntimeFontLoaded(vars.font).then(family => {
              const { family: norm } = normalizeFontFile(vars.font)
              layer.src = buildSimpleTextDataUrl(cfg, vars, family || norm)
            })
          }

          const templateName = cfg.container.dataset.overlayTemplate
          const inputs = cfg.container.querySelectorAll(
            `[name="${templateName}[text]"], [name="${templateName}[font]"], [name="${templateName}[font_size]"], [name="${templateName}[font_color]"]`
          )
          inputs.forEach(input => {
            input.addEventListener('input', refreshTextOverlay)
            input.addEventListener('change', refreshTextOverlay)
          })
          refreshTextOverlay()
        }

        if (cfg.id === 'overlay_content_rating_commonsense' && layer && cfg.container) {
          const refreshCommonsense = () => {
            buildCommonsenseDataUrl(cfg).then(dataUrl => {
              layer.src = dataUrl
              applyPosition(cfg)
            })
          }
          const templateName = cfg.container.dataset.overlayTemplate
          const inputs = cfg.container.querySelectorAll(
            `[name="${templateName}[text]"], [name="${templateName}[post_text]"], [name="${templateName}[addon_offset]"], [name="${templateName}[font]"], [name="${templateName}[font_size]"], [name="${templateName}[font_color]"]`
          )
          inputs.forEach(input => {
            input.addEventListener('input', refreshCommonsense)
            input.addEventListener('change', refreshCommonsense)
          })
          refreshCommonsense()
        }
      })

      // Recompute positions after images load or container resizes
      const recalcAll = () => {
        configs.forEach(cfg => {
          applyPosition(cfg)
          applyEditionPosition(cfg)
        })
      }

      window.addEventListener('resize', recalcAll)
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

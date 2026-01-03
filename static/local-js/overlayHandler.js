/* global EventHandler, toggleOverlayTemplateSection */

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
      if (cfg.id === 'overlay_ribbon' && cfg.styleInput) {
        const style = (cfg.styleInput.value || 'yellow').toLowerCase()
        const allowed = ['yellow', 'red', 'black', 'gray']
        const styleSafe = allowed.includes(style) ? style : 'yellow'
        return `https://raw.githubusercontent.com/Kometa-Team/Kometa/refs/heads/nightly/defaults/overlays/images/ribbon/${styleSafe}/oscars.png`
      }
      return cfg.image
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

      const writeOffsets = (cfg, h, v) => {
        const { hInput, vInput } = getInputs(cfg)
        if (!hInput || !vInput) return
        writing = true
        hInput.value = Math.round(h)
        vInput.value = Math.round(v)
        hInput.dispatchEvent(new Event('change', { bubbles: true }))
        vInput.dispatchEvent(new Event('change', { bubbles: true }))
        writing = false
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

        layer.style.width = `${natW * scaleX}px`
        layer.style.height = `${natH * scaleY}px`

        const hVal = ensureNumber(hInput.value)
        const vVal = ensureNumber(vInput.value)

        layer.style.left = `${hVal * scaleX}px`
        layer.style.top = `${vVal * scaleY}px`
        applyVisibility(cfg, layer)
      }

      const bindDrag = (cfg, layer) => {
        let dragging = false
        let start = { x: 0, y: 0, h: 0, v: 0 }

        const onPointerDown = (e) => {
          e.preventDefault()
          layer.setPointerCapture(e.pointerId)
          const { hInput, vInput } = getInputs(cfg)
          start = {
            x: e.clientX,
            y: e.clientY,
            h: ensureNumber(hInput?.value),
            v: ensureNumber(vInput?.value)
          }
          dragging = true
          layer.classList.add('dragging')
        }

        const onPointerMove = (e) => {
          if (!dragging) return
          const { scaleX, scaleY } = getScale()
          const natW = cfg.naturalWidth || layer.naturalWidth || (baseWidth * 0.25)
          const natH = cfg.naturalHeight || layer.naturalHeight || (baseHeight * 0.25)
          const overlayWidthBase = natW
          const overlayHeightBase = natH

          const deltaX = (e.clientX - start.x) / scaleX
          const deltaY = (e.clientY - start.y) / scaleY

          const maxH = Math.max(0, baseWidth - overlayWidthBase)
          const maxV = Math.max(0, baseHeight - overlayHeightBase)

          const nextH = clamp(start.h + deltaX, 0, maxH)
          const nextV = clamp(start.v + deltaY, 0, maxV)

          layer.style.left = `${nextH * scaleX}px`
          layer.style.top = `${nextV * scaleY}px`
          writeOffsets(cfg, nextH, nextV)
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
        const handler = () => applyVisibility(cfg, layer)
        toggle.addEventListener('change', handler)
      }

      const addOverlayLayer = (cfg) => {
        if (layers.has(cfg.id)) return layers.get(cfg.id)
        const layer = document.createElement('img')
        layer.className = 'overlay-board-layer'
        layer.src = resolveOverlayImage(cfg)
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
        applyPosition(cfg)
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
          naturalHeight: null
        }

        if (!cfg.id || !cfg.image || !cfg.hId || !cfg.vId) return
        if (!document.getElementById(cfg.hId) || !document.getElementById(cfg.vId)) return
        configs.push(cfg)
        addOverlayLayer(cfg)
      })

      // Recompute positions after images load or container resizes
      const recalcAll = () => {
        configs.forEach(cfg => applyPosition(cfg))
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

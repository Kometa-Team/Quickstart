export function libraryFileRowMatches (row, kind, entry) {
  const prefix = kind.replace(/_files$/, '-file')
  const type = String(row.querySelector(`[data-${prefix}-type]`)?.value || '').trim()
  const location = String(row.querySelector(`[data-${prefix}-location]`)?.value || '').trim()
  return type === String(entry?.type || '').trim() && location === String(entry?.location || '').trim()
}

export function applyLibraryFileServerErrors (editor, errors, kind, submittedEntries, setStatus) {
  if (!editor || !Array.isArray(errors) || !Array.isArray(submittedEntries)) return false
  const libraryId = String(editor.dataset.libraryId || '').trim()
  if (!libraryId) return false
  const prefix = kind.replace(/_files$/, '-file')
  const rows = Array.from(editor.querySelectorAll(`[data-${prefix}-row]`))
  let applied = false
  errors.forEach(error => {
    const match = String(error || '').trim().match(/^(\S+) (collection_files|metadata_files|overlay_files)\[(\d+)\]:\s*(.+)$/i)
    if (!match || match[1] !== libraryId || match[2] !== kind) return
    const index = Number(match[3]) - 1
    const entry = submittedEntries[index]
    if (!entry) return
    // A response can arrive after rows were removed, reordered, or edited.
    const matchingRows = rows.filter(row => libraryFileRowMatches(row, kind, entry))
    const occurrence = submittedEntries.slice(0, index).filter(item =>
      item.type === entry.type && item.location === entry.location
    ).length
    const row = matchingRows[occurrence]
    if (!row) return
    setStatus(row, 'error', match[4])
    applied = true
  })
  return applied
}

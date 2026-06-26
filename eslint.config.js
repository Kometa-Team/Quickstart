const browserGlobals = {
  window: 'readonly',
  document: 'readonly',
  navigator: 'readonly',
  location: 'readonly',
  localStorage: 'readonly',
  console: 'readonly',
  fetch: 'readonly',
  setTimeout: 'readonly',
  clearTimeout: 'readonly',
  setInterval: 'readonly',
  clearInterval: 'readonly',
  URL: 'readonly',
  URLSearchParams: 'readonly',
  FormData: 'readonly',
  Blob: 'readonly',
  Event: 'readonly',
  AbortController: 'readonly',
  MutationObserver: 'readonly',
  requestAnimationFrame: 'readonly',
  ResizeObserver: 'readonly',
  DOMParser: 'readonly',
  CustomEvent: 'readonly',
  FileReader: 'readonly',
  Image: 'readonly',
  FontFace: 'readonly',
  Element: 'readonly'
}

const quickstartGlobals = {
  $: 'readonly',
  bootstrap: 'readonly',
  validateButton: 'readonly',
  showSpinner: 'readonly',
  hideSpinner: 'readonly',
  showToast: 'readonly',
  PathValidation: 'readonly',
  URLValidation: 'readonly',
  ValidationHandler: 'readonly',
  OverlayHandler: 'readonly',
  EventHandler: 'readonly',
  ImageHandler: 'readonly',
  Sortable: 'readonly',
  setupParentChildToggleSync: 'readonly',
  jumpTo: 'readonly',
  showNavigationLoadingOverlay: 'readonly',
  hideNavigationLoadingOverlay: 'readonly',
  toggleOverlayTemplateSection: 'readonly',
  updateFormData: 'readonly',
  boardState: 'readonly',
  applyPosition: 'readonly',
  initialRadarrRootFolderPath: 'readonly',
  initialRadarrQualityProfile: 'readonly',
  initialSonarrRootFolderPath: 'readonly',
  initialSonarrQualityProfile: 'readonly',
  initialSonarrLanguageProfile: 'readonly'
}

module.exports = [
  {
    files: ['static/local-js/**/*.js'],
    ignores: ['static/local-js/bootstrap.bundle.js'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'script',
      globals: {
        ...browserGlobals,
        ...quickstartGlobals
      }
    },
    rules: {
      'no-undef': 'error',
      'no-unused-vars': ['error', { args: 'none', ignoreRestSiblings: true }],
      'no-shadow': 'error',
      'no-global-assign': 'error',
      'no-implied-eval': 'error'
    }
  }
]

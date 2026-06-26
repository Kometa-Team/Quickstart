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

// Files that have been migrated to ES modules as part of roadmap step 2
// (issue #1346). Keep this list in sync with MODULE_PAGE_SCRIPTS in
// quickstart.py for page scripts. The modules/ subdirectory is always
// module-scoped by virtue of the glob.
const moduleFiles = [
  'static/local-js/modules/**/*.js',
  'static/local-js/000-base.js',
  'static/local-js/pathValidation.js',
  'static/local-js/urlValidation.js',
  'static/local-js/templateStringList.js',
  'static/local-js/010-plex.js',
  'static/local-js/020-tmdb.js',
  'static/local-js/030-tautulli.js',
  'static/local-js/040-github.js',
  'static/local-js/050-omdb.js',
  'static/local-js/060-mdblist.js',
  'static/local-js/070-notifiarr.js',
  'static/local-js/080-gotify.js',
  'static/local-js/085-ntfy.js',
  'static/local-js/087-apprise.js',
  'static/local-js/090-webhooks.js',
  'static/local-js/110-radarr.js',
  'static/local-js/120-sonarr.js',
  'static/local-js/130-trakt.js',
  'static/local-js/140-mal.js'
]

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
  },
  {
    files: moduleFiles,
    languageOptions: {
      sourceType: 'module'
    }
  }
]

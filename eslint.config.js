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

// Quickstart-specific globals. Most are functions defined in 000-base.js
// or one of the classic-script files loaded by 025-libraries.js
// (eventHandler.js, validationHandler.js, etc.). Declaring them here
// suppresses `no-undef` errors in classic scripts that call them bare.
//
// NOTE: `loading` is INTENTIONALLY NOT in this list. PR #1382 retired
// the window.loading shim because the only external caller
// (001-start.js) was migrated to a direct `import { loading }`. Adding
// `loading: 'readonly'` here would silently re-enable bare `loading()`
// calls from classic scripts that would resolve to `undefined` at
// runtime. The `no-restricted-syntax` rule below also bans
// `window.loading = ...` to prevent the shim being re-introduced.
//
// `jumpTo` IS in this list because PR #1383 restored its shim after
// discovering static/local-js/025-libraries.js (a 4600-line classic
// script) calls it bare. When 025-libraries.js is converted to an ES
// module, remove `jumpTo` from this list and add it to the
// `no-restricted-syntax` ban below.
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
  'static/local-js/001-start.js',
  'static/local-js/010-plex.js',
  'static/local-js/020-tmdb.js',
  'static/local-js/027-playlist_files.js',
  'static/local-js/030-tautulli.js',
  'static/local-js/040-github.js',
  'static/local-js/050-omdb.js',
  'static/local-js/060-mdblist.js',
  'static/local-js/070-notifiarr.js',
  'static/local-js/080-gotify.js',
  'static/local-js/085-ntfy.js',
  'static/local-js/087-apprise.js',
  'static/local-js/090-webhooks.js',
  'static/local-js/100-anidb.js',
  'static/local-js/110-radarr.js',
  'static/local-js/120-sonarr.js',
  'static/local-js/130-trakt.js',
  'static/local-js/140-mal.js',
  'static/local-js/150-settings.js',
  'static/local-js/905-analytics.js',
  'static/local-js/915-imagemaid.js'
]

// Selectors for `no-restricted-syntax`. Defined here so the rules block
// below stays readable. ESLint AST selector reference:
// https://eslint.org/docs/latest/extend/selectors
//
// Inline-handler regression guards: these patterns catch the recurring
// foot-gun cleaned up across PRs #1375-#1381 (29 inline event handlers
// + 4 IIFEs eliminated). The cleanup pattern:
//
//   BAD:  innerHTML = '<a onclick="jumpTo(\\'010-plex\\')">click</a>'
//   GOOD: <a href="javascript:void(0);" data-jumpto-page="010-plex">click</a>
//         + delegated click listener
//
// We catch the BAD pattern by inspecting Literal nodes (regular strings)
// and TemplateElement nodes (the static text portions of template
// literals). The regex matches the on-event-name pattern followed by
// optional whitespace and `=`. Wrapped in `\b` so it doesn't trip on
// e.g. `data-onclick-foo="..."` or substrings inside larger identifiers.
const inlineHandlerPattern = '/\\bon(click|input|change|submit|key\\w*|focus|blur|mouse\\w*)\\s*=/'
const inlineHandlerMessage =
  'Inline event-handler attributes (onclick=, oninput=, etc.) are forbidden ' +
  'in JS strings. Use data-attributes + delegated listeners. ' +
  'See static/local-js/000-base.js for the data-jumpto-page / data-nav-action ' +
  'pattern.'

// Shim regression guards. These catch `window.X = ...` assignments for
// names we have deliberately retired. AssignmentExpression selector:
//   left.object.name === 'window' AND left.property.name === 'loading'
// Per-name selectors are easier to read than one selector that matches
// "any retired name".
//
// NOTE: window.jumpTo is INTENTIONALLY NOT in this ban list. See the
// quickstartGlobals comment above for why.
const retiredShimMessage = (name) =>
  `window.${name} = ... is a retired compatibility shim. ` +
  'See PR #1382 (chore/retire-jumpto-loading-shims). The only caller ' +
  'was migrated to a direct ES module import. Adding the shim back ' +
  'would re-introduce window namespace pollution.'

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
      'no-implied-eval': 'error',
      // Modernization rules. Already passing across the codebase; locking
      // them in so they can't regress. The `eqeqeq` 'null' exception
      // allows `x == null` / `x != null` as the idiomatic check for
      // "null or undefined" -- the existing codebase uses this in 15+
      // places, all genuinely intentional.
      'no-var': 'error',
      'prefer-const': 'error',
      eqeqeq: ['error', 'always', { null: 'ignore' }],
      // Regression guards for the inline-handler / shim cleanup sprint.
      'no-restricted-syntax': [
        'error',
        {
          selector: `Literal[value=${inlineHandlerPattern}]`,
          message: inlineHandlerMessage
        },
        {
          selector: `TemplateElement[value.raw=${inlineHandlerPattern}]`,
          message: inlineHandlerMessage
        },
        {
          selector:
            "AssignmentExpression[left.type='MemberExpression']" +
            "[left.object.name='window'][left.property.name='loading']",
          message: retiredShimMessage('loading')
        }
      ]
    }
  },
  {
    files: moduleFiles,
    languageOptions: {
      sourceType: 'module'
    }
  }
]

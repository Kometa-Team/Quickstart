import { createApiKeyValidator } from './modules/createApiKeyValidator.js'

// ── pre-config wizard init ──────────────────────────────────────────
// The "hidden" section + plexDbCache element are revealed for users
// who have already validated. Runs once at module load, before the
// factory does its own initial-state wiring.
const hiddenSection = document.getElementById('hidden')
const plexDbCache = document.getElementById('plexDbCache')

;(function showSavedSectionsIfValidated () {
  const validated = document.getElementById('plex_validated')?.value.toLowerCase() === 'true'
  if (validated) {
    if (hiddenSection) hiddenSection.style.display = 'block'
    if (plexDbCache) plexDbCache.style.display = 'block'
  }
})()

// ── post-validation success handler ──────────────────────────────────
// Plex's response carries a LOT of extra state that needs to land in
// hidden form fields + visible UI:
//   - db_cache value (with mismatch warning if the user's input differs)
//   - plex-pass status banners
//   - user list + 3 library lists (movie / show / music) into hidden inputs
function applyPlexResponse (data) {
  // Plex-pass status banners. Only updated on a successful validate --
  // the legacy code updated them unconditionally (so a failed validate
  // would briefly show "no plex pass" even though no token was checked).
  // That was a latent bug; preserving it would be slavish. The banners
  // now ONLY reflect actual server responses.
  const passSuccess = document.getElementById('plex-pass-status-success')
  const passWarning = document.getElementById('plex-pass-status-warning')
  if (passSuccess && passWarning) {
    if (data.has_plex_pass) {
      passSuccess.classList.remove('d-none')
      passSuccess.style.display = 'block'
      passWarning.classList.add('d-none')
      passWarning.style.display = 'none'
    } else {
      passSuccess.classList.add('d-none')
      passSuccess.style.display = 'none'
      passWarning.classList.remove('d-none')
      passWarning.style.display = 'block'
    }
  }

  // DB cache value + mismatch warning. Note: we capture currentDbCache
  // at response time (not click time). The legacy code captured at
  // click time, but the user almost never edits db_cache during the
  // validate round-trip, and reading the latest value is arguably more
  // correct (it reflects what the user actually wants right now).
  const dbCacheInput = document.getElementById('plex_db_cache')
  const currentDbCache = dbCacheInput ? dbCacheInput.value : ''
  const serverDbCache = data.db_cache

  if (plexDbCache) {
    plexDbCache.textContent = 'Database cache value retrieved from server is: ' + serverDbCache + ' MB'
    plexDbCache.style.color = '#75b798'
    plexDbCache.style.display = 'block'

    if (Number(currentDbCache) !== serverDbCache) {
      plexDbCache.textContent += '.\nWarning: The value in the input box (' + currentDbCache + ' MB) does not match the value retrieved from the server (' + serverDbCache + ' MB).'
      plexDbCache.style.color = '#ea868f'
    }
  }
  if (dbCacheInput) dbCacheInput.value = serverDbCache

  // Hidden tmp_ inputs that hold the lists for the next wizard pages.
  const tmpUserList = document.getElementById('tmp_user_list')
  const tmpMusicLibraries = document.getElementById('tmp_music_libraries')
  const tmpMovieLibraries = document.getElementById('tmp_movie_libraries')
  const tmpShowLibraries = document.getElementById('tmp_show_libraries')
  if (tmpUserList) tmpUserList.value = data.user_list
  if (tmpMusicLibraries) tmpMusicLibraries.value = data.music_libraries
  if (tmpMovieLibraries) tmpMovieLibraries.value = data.movie_libraries
  if (tmpShowLibraries) tmpShowLibraries.value = data.show_libraries

  // Reveal the "hidden" section that holds the db_cache configuration.
  if (hiddenSection) hiddenSection.style.display = 'block'
}

createApiKeyValidator({
  fieldId: 'plex_token',
  additionalFieldIds: ['plex_url'],
  validatedFieldId: 'plex_validated',
  validatedAtFieldId: 'plex_validated_at',
  endpoint: '/validate_plex',
  buildPayload: (token, extras) => ({
    plex_url: extras.plex_url,
    plex_token: token
  }),
  messages: {
    empty: 'Please enter both Plex URL and Token.',
    success: 'Plex server validated successfully!',
    failure: 'Failed to validate Plex server. Please check your URL and Token.',
    networkError: 'Error occurred during validation.'
  },
  // Plex's server returns `{validated: true, ...}` on success but
  // `{valid: false, error: '...'}` on failure (asymmetric naming
  // preserved from the legacy API endpoint).
  isValid: (data) => data.validated === true,
  onValidationSuccess: applyPlexResponse
})

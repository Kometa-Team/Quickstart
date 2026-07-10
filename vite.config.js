// Vite scaffolding for Quickstart frontend (#1334 Step 4).
//
// This config is intentionally dormant: nothing in production currently
// references the build output. Flask still loads JS directly from
// static/local-js/ via <script> tags in templates/000-base.html. The
// purpose of this config is to establish the toolchain so future PRs
// (Alpine widgets for Step 6, Svelte islands for Step 9) can plug into
// it.
//
// What this config does today:
//   - npm run dev      starts the Vite dev server on http://localhost:5173
//   - npm run build    emits production bundles into static/dist/
//   - npm run preview  serves the built bundles for a quick smoke test
//   - npm test         runs the Vitest suite under tests/js/
//
// What this config explicitly does NOT do:
//   - touch templates/000-base.html
//   - change Dockerfile or quickstart.spec
//   - replace the existing ESLint or pre-commit pipelines
//
// CI enforcement: `npm run build` runs as the `vite-build` job in
// .github/workflows/lint.yml, so the build stays green even while
// nothing consumes its output. When a downstream PR flips a template
// switch, the bundle already works.
//
// Multi-entry strategy: every file in static/local-js/*.js whose first
// non-comment/non-whitespace token is `import` or `export` is registered
// as a Vite entry point. We discover the set from disk rather than
// duplicating MODULE_PAGE_SCRIPTS in this file -- the entry set stays
// in sync with the actual module conversions without manual upkeep.
// The exact detection logic (which correctly skips leading docstrings
// and block comments) lives in ./vite.detectModuleEntry.mjs and is
// unit-tested under tests/js/detectModuleEntry.test.js.

import { defineConfig } from 'vite'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { isModuleSource } from './vite.detectModuleEntry.mjs'

const rootDir = fileURLToPath(new URL('.', import.meta.url))
const sourceDir = resolve(rootDir, 'static/local-js')
const outputDir = resolve(rootDir, 'static/dist')

function discoverModuleEntries (dir) {
  // A file is treated as a module entry iff it lives directly in
  // static/local-js/ AND its first non-comment/non-whitespace token is
  // `import` or `export` (see vite.detectModuleEntry.mjs). This matches
  // the browser's own definition of a module: source that syntactically
  // declares import/export at the top level.
  //
  // Files in static/local-js/modules/ are NOT entry points -- they are
  // dependencies imported by other modules.
  //
  // Files that MODULE_PAGE_SCRIPTS lists but which don't actually use
  // import/export (100-anidb.js, 915-imagemaid.js) are skipped -- Vite
  // building them would produce a byte-for-byte copy of the source,
  // providing no value while cluttering static/dist/.
  //
  // As of #1346 finish, imageHandler.js, pathValidation.js,
  // urlValidation.js, and validationHandler.js DO use `export` and
  // therefore are entry points. They also keep their `window.*` shims
  // for backward compat with classic-script consumers (see
  // 915-imagemaid.js) and consumers not yet migrated to `import`.
  const entries = {}
  for (const name of readdirSync(dir)) {
    const fullPath = join(dir, name)
    if (!statSync(fullPath).isFile()) continue
    if (!name.endsWith('.js')) continue
    const source = readFileSync(fullPath, 'utf8')
    if (isModuleSource(source)) {
      const entryName = name.replace(/\.js$/, '')
      entries[entryName] = fullPath
    }
  }
  return entries
}

export default defineConfig({
  root: rootDir,
  // Tell Vite where to resolve bare specifiers relative to. Today everything
  // is relative-path imports, but once we add npm packages (Alpine for
  // Step 6) this will matter.
  resolve: {
    alias: {
      '@local-js': sourceDir
    }
  },
  build: {
    outDir: outputDir,
    // Don't wipe static/dist between builds; only files we own. Vite already
    // scopes cleaning to its own output, but being explicit costs nothing.
    emptyOutDir: true,
    // Emit static/dist/.vite/manifest.json so Flask can look up the hashed
    // filename for each source entry at request time. This is the
    // production analogue of the dev server's on-the-fly resolution and
    // is the pattern all mainstream server-side frameworks (Rails asset
    // pipeline, Django whitenoise, Laravel Mix) use for cache busting.
    //
    // Format: { "static/local-js/000-base.js": { "file": "000-base-<hash>.js", ... } }
    // See modules/vite_manifest.py for the Python-side lookup.
    manifest: true,
    rollupOptions: {
      input: discoverModuleEntries(sourceDir),
      output: {
        // Hash entry and chunk filenames for cache busting. Templates
        // reference these via the asset_url() Jinja global, which reads
        // manifest.json and resolves the source name to the hashed name.
        // Assets (fonts, images if we ever bundle them) keep their
        // extension in the hash so mime-type detection stays sane.
        entryFileNames: '[name]-[hash].js',
        chunkFileNames: 'chunks/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]'
      }
    },
    // Modern browsers only — matches what the rest of the codebase already
    // assumes (the project already uses `<script type="module">`).
    target: 'esnext',
    // Minify with esbuild (Vite's default) for smaller production bundles.
    // Keeps sourcemaps enabled so stack traces in bug reports map back
    // to the original source.
    minify: 'esbuild',
    sourcemap: true
  },
  server: {
    port: 5173,
    strictPort: false,
    // Surface stack traces in the terminal in dev so refactor-time errors
    // are loud.
    hmr: true
  },
  test: {
    // Vitest configuration (PR for #1334 Step 8).
    //
    // jsdom gives our tests a DOM. Every shared module under
    // static/local-js/modules/ either manipulates the DOM directly (e.g.
    // setToggleButtonIcon does replaceChildren) or delegates to a global
    // attached to window — both need a browser-shaped environment.
    environment: 'jsdom',
    // Tests live under tests/js/ to keep them out of static/ (which is
    // shipped to PyInstaller releases) and to mirror the existing tests/
    // convention for Python tests.
    include: ['tests/js/**/*.test.js'],
    // Print a summary even when everything passes. Quiet CI logs hide
    // useful information.
    reporters: 'default',
    // Don't watch in CI; rely on caller using --watch when wanted locally.
    watch: false
  }
})

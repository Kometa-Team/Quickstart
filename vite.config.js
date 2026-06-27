// Vite scaffolding for Quickstart frontend (PR for #1334 Step 4).
//
// This config is intentionally dormant: nothing in production currently
// references the build output. Flask still loads JS directly from
// static/local-js/ via <script> tags in templates/000-base.html. The
// purpose of this PR is to establish the toolchain so subsequent PRs
// (Vitest, the validation widget consolidation, Alpine, etc.) have a
// place to plug into.
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
// Multi-entry strategy: every file in static/local-js/*.js that is already
// served as an ES module (per MODULE_PAGE_SCRIPTS in quickstart.py:410)
// is registered as a Vite entry point. We discover the set from disk by
// detecting top-level `import` statements rather than maintaining a
// duplicate list here — that way the entry set stays in sync with the
// actual module conversions without manual upkeep.

import { defineConfig } from 'vite'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = fileURLToPath(new URL('.', import.meta.url))
const sourceDir = resolve(rootDir, 'static/local-js')
const outputDir = resolve(rootDir, 'static/dist')

function discoverModuleEntries (dir) {
  // A file is treated as a module entry iff it lives directly in
  // static/local-js/ AND begins with an `import` or `export` statement.
  // Files in static/local-js/modules/ are not entry points — they are
  // dependencies imported by other modules.
  const entries = {}
  for (const name of readdirSync(dir)) {
    const fullPath = join(dir, name)
    if (!statSync(fullPath).isFile()) continue
    if (!name.endsWith('.js')) continue
    const head = readFileSync(fullPath, 'utf8').slice(0, 200).trimStart()
    if (head.startsWith('import ') || head.startsWith('import{') ||
        head.startsWith('export ') || head.startsWith('export{')) {
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
    // No hash in filenames yet. When templates start referencing the build
    // output (a later PR) we'll switch to manifest-based lookups and turn
    // hashing back on for cache busting.
    rollupOptions: {
      input: discoverModuleEntries(sourceDir),
      output: {
        entryFileNames: '[name].js',
        chunkFileNames: 'chunks/[name].js',
        assetFileNames: 'assets/[name][extname]'
      }
    },
    // Modern browsers only — matches what the rest of the codebase already
    // assumes (the project already uses `<script type="module">`).
    target: 'esnext',
    minify: false,
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

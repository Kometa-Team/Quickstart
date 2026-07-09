// Tests for vite.detectModuleEntry.js -- the "is this file an ES module
// entry point?" heuristic used by vite.config.js's discoverModuleEntries.
//
// Why these matter: the original heuristic only checked the first 200
// characters of source and required `import` or `export` at position 0.
// That silently dropped 900-kometa.js, 025-libraries.js, 001-start.js,
// and overlayHandler.js -- four of the largest ES modules in the
// codebase -- because they lead with a docstring. This test file locks
// down the fixed behavior so the regression can't reappear.
//
// Test scope:
//   - Positive cases: various leading-comment shapes -> module detected
//   - Negative cases: classic scripts (no import/export) -> NOT detected
//   - Edge cases: unclosed comments, comment-only files, giant headers

import { describe, expect, it } from 'vitest'
import { isModuleSource, stripLeadingCommentsAndWhitespace } from '../../vite.detectModuleEntry.mjs'

describe('stripLeadingCommentsAndWhitespace', () => {
  it('returns 0 for a file that starts with real code', () => {
    expect(stripLeadingCommentsAndWhitespace('import foo from "bar"')).toBe(0)
  })

  it('skips leading whitespace', () => {
    expect(stripLeadingCommentsAndWhitespace('   \n\t import foo')).toBe(6)
  })

  it('skips a single leading line comment', () => {
    const source = '// hello\nimport foo'
    expect(stripLeadingCommentsAndWhitespace(source)).toBe(9)
  })

  it('skips multiple consecutive line comments', () => {
    const source = '// one\n// two\n// three\nimport foo'
    expect(stripLeadingCommentsAndWhitespace(source)).toBe(23)
  })

  it('skips a leading block comment', () => {
    const source = '/* hello */import foo'
    expect(stripLeadingCommentsAndWhitespace(source)).toBe(11)
  })

  it('skips a multi-line block comment', () => {
    const source = '/*\n * docstring\n * spanning lines\n */\nimport foo'
    // The offset points at the newline after `*/`, which whitespace
    // consumption then eats.
    const offset = stripLeadingCommentsAndWhitespace(source)
    expect(source.slice(offset).startsWith('import')).toBe(true)
  })

  it('handles interleaved line + block + whitespace', () => {
    const source = '// header\n/* copyright */\n\n// scope note\nexport function foo() {}'
    const offset = stripLeadingCommentsAndWhitespace(source)
    expect(source.slice(offset).startsWith('export')).toBe(true)
  })

  it('bails out (returns limit) on an unclosed block comment', () => {
    // Defensive: if someone accidentally writes /* without */, we
    // don't want an infinite loop. Return the scan limit so the
    // caller sees "no real code found" and treats the file as a
    // non-module (safer default than throwing).
    const source = '/* forever...'
    const offset = stripLeadingCommentsAndWhitespace(source)
    expect(offset).toBeGreaterThanOrEqual(source.length)
  })

  it('bails out on a comment header that exceeds the 1kb scan window', () => {
    // A file with 2kb of comments before the first real code will
    // have detection give up somewhere in the comment. Treat that
    // as "not a module" -- files with that much header noise are
    // rare enough to accept the false negative.
    const bigComment = '// ' + 'x'.repeat(2000) + '\nimport foo'
    const offset = stripLeadingCommentsAndWhitespace(bigComment)
    // The scanner returns the 1kb window limit; slice from there
    // won't hit `import`, and isModuleSource() will return false.
    expect(offset).toBeLessThanOrEqual(1024)
  })

  it('handles a file that is nothing but a comment', () => {
    const source = '// I am but a lonely comment'
    const offset = stripLeadingCommentsAndWhitespace(source)
    // Whole file consumed -> offset === source.length.
    expect(offset).toBe(source.length)
  })

  it('handles empty source', () => {
    expect(stripLeadingCommentsAndWhitespace('')).toBe(0)
  })
})

describe('isModuleSource', () => {
  describe('positive cases (should be detected as modules)', () => {
    it('detects a file that starts with `import`', () => {
      expect(isModuleSource('import foo from "bar"')).toBe(true)
    })

    it('detects a file that starts with `export`', () => {
      expect(isModuleSource('export function foo() {}')).toBe(true)
    })

    it('detects an ES module hidden behind a single-line comment', () => {
      expect(isModuleSource('// this is a module\nimport foo from "bar"')).toBe(true)
    })

    it('detects an ES module hidden behind a multi-line docstring block', () => {
      const source = [
        '/*',
        ' * This module does the thing.',
        ' * See #1234 for details.',
        ' */',
        '',
        'import { thing } from "./thing.js"'
      ].join('\n')
      expect(isModuleSource(source)).toBe(true)
    })

    it('detects a module with a long stack of // comments before the import', () => {
      // Regression: 900-kometa.js leads with several `//` lines of context.
      const source = [
        '// Global flag so other handlers know an update is in progress',
        'import {',
        '  computeYamlLineCount,',
        '  formatTimestampLocal',
        '} from "./modules/kometaFormatters.js"'
      ].join('\n')
      expect(isModuleSource(source)).toBe(true)
    })

    it('detects a module with mixed comment styles before the import', () => {
      const source = [
        '/* copyright banner */',
        '// scope note',
        '',
        '// implementation note',
        'import foo from "./foo.js"'
      ].join('\n')
      expect(isModuleSource(source)).toBe(true)
    })

    it('detects `import{` (no space, minified-style)', () => {
      expect(isModuleSource('import{foo}from"bar"')).toBe(true)
    })

    it('detects `export{` (no space, re-export style)', () => {
      expect(isModuleSource('export{foo}from"bar"')).toBe(true)
    })

    it('detects `export default`', () => {
      expect(isModuleSource('export default function foo() {}')).toBe(true)
    })
  })

  describe('negative cases (should NOT be detected as modules)', () => {
    it('rejects a classic script starting with const', () => {
      expect(isModuleSource('const foo = 42')).toBe(false)
    })

    it('rejects a classic script starting with function', () => {
      expect(isModuleSource('function foo() {}')).toBe(false)
    })

    it('rejects a classic script starting with an IIFE', () => {
      expect(isModuleSource('(function () { /* ... */ })()')).toBe(false)
    })

    it('rejects a classic script starting with document lookup', () => {
      // Regression: 100-anidb.js and 915-imagemaid.js start like this.
      expect(isModuleSource('const el = document.getElementById("foo")')).toBe(false)
    })

    it('rejects a file that is nothing but a comment', () => {
      expect(isModuleSource('// this file intentionally left blank')).toBe(false)
    })

    it('rejects empty source', () => {
      expect(isModuleSource('')).toBe(false)
    })

    it('rejects a bare identifier that starts with `im...` but is not `import`', () => {
      // Word boundary: `import` must be a complete word.
      expect(isModuleSource('imports = { foo: 1 }')).toBe(false)
    })

    it('rejects a bare identifier that starts with `ex...` but is not `export`', () => {
      expect(isModuleSource('exports.foo = 1')).toBe(false)
    })

    it('rejects a variable named import inside a comment then code', () => {
      // The `// import { ... }` inside the comment must not trigger
      // detection; the real code that follows is classic-script.
      expect(isModuleSource('// example: import { foo } from "bar"\nconst x = 1')).toBe(false)
    })
  })
})

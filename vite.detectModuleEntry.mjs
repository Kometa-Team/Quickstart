// Helper for vite.config.js: given a source string, detect whether the
// file is an ES module (i.e. its first non-comment/non-whitespace token
// is `import` or `export`).
//
// Split out from vite.config.js so it can be unit-tested. The logic
// looks trivial, but got a subtle bug in its first form (checked only
// the first 200 chars, missed files with a leading docstring). This
// module owns the definition of "what counts as a module entry point."
//
// Public API:
//   stripLeadingCommentsAndWhitespace(source) -> number
//     Returns the offset of the first character that is NOT a comment
//     or whitespace. Consumes // line comments, /* block comments */,
//     and any interleaved whitespace. Scans at most the first 1024
//     characters -- if a file has more than 1kb of leading comments,
//     it's suspicious anyway.
//
//   isModuleSource(source) -> boolean
//     Returns true iff the first real token is `import` or `export`.

const SCAN_LIMIT = 1024

export function stripLeadingCommentsAndWhitespace (source) {
  let i = 0
  const limit = Math.min(source.length, SCAN_LIMIT)
  while (i < limit) {
    const ch = source[i]
    if (ch === ' ' || ch === '\t' || ch === '\n' || ch === '\r') {
      i += 1
      continue
    }
    if (ch === '/' && source[i + 1] === '/') {
      // Line comment: skip to end of line (or end of scan window).
      const nl = source.indexOf('\n', i + 2)
      if (nl === -1 || nl >= limit) return limit
      i = nl + 1
      continue
    }
    if (ch === '/' && source[i + 1] === '*') {
      // Block comment: skip to closing */ (or end of scan window).
      const end = source.indexOf('*/', i + 2)
      if (end === -1 || end >= limit) return limit
      i = end + 2
      continue
    }
    break
  }
  return i
}

export function isModuleSource (source) {
  const offset = stripLeadingCommentsAndWhitespace(source)
  // Look at the next word. We only need enough characters to
  // disambiguate `import` / `export` from anything else -- 20 is
  // plenty.
  const head = source.slice(offset, offset + 20)
  return /^(import|export)\b/.test(head)
}

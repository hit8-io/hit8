#!/usr/bin/env node
/**
 * Copies Plus Jakarta Sans font CSS and assets to public/fonts/
 * so they can be loaded non-blocking via <link rel="preload" as="style">.
 * Run: node scripts/copy-fonts.mjs (from apps/site) or pnpm run build:fonts
 */
import { readFileSync, cpSync, mkdirSync, writeFileSync } from 'fs'
import { dirname, join } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const siteRoot = join(__dirname, '..')
const publicFonts = join(siteRoot, 'public', 'fonts')

// Resolve package (works with pnpm hoisting)
const { createRequire } = await import('module')
const require = createRequire(import.meta.url)
const resolved = require.resolve('@fontsource/plus-jakarta-sans/300.css')
const pkgRoot = dirname(resolved)
const { existsSync } = await import('fs')

if (!existsSync(pkgRoot)) {
  console.error('@fontsource/plus-jakarta-sans not found. Run: pnpm install')
  process.exit(1)
}

const weights = ['300', '400', '600', '700']
const cssParts = []
for (const w of weights) {
  const cssPath = join(pkgRoot, `${w}.css`)
  cssParts.push(readFileSync(cssPath, 'utf8'))
}
const combinedCss = cssParts.join('\n')

mkdirSync(publicFonts, { recursive: true })
writeFileSync(join(publicFonts, 'plus-jakarta-sans.css'), combinedCss, 'utf8')

const filesSrc = join(pkgRoot, 'files')
const filesDest = join(publicFonts, 'files')
cpSync(filesSrc, filesDest, { recursive: true })

console.log('Fonts copied to public/fonts/')

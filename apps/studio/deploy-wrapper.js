#!/usr/bin/env node

// Load React hook before anything else - this ensures React is available globally
require('./react-hook.js')

// Now execute the Sanity deploy command with NODE_OPTIONS set
const { spawn } = require('child_process')
const path = require('path')

const reactHookPath = path.resolve(__dirname, 'react-hook.js')
const sanityBin = path.join(__dirname, 'node_modules', '.bin', 'sanity')
const args = process.argv.slice(2)

// Set NODE_OPTIONS to preload the React hook
process.env.NODE_OPTIONS = `-r ${reactHookPath} ${process.env.NODE_OPTIONS || ''}`.trim()

const child = spawn(sanityBin, args, {
  stdio: 'inherit',
  shell: true,
  env: process.env,
})

child.on('exit', (code) => {
  process.exit(code || 0)
})

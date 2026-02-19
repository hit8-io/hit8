// Ensure React is available globally during build/manifest extraction
// This is needed for styled-components v6 which requires React at module initialization
if (typeof globalThis !== 'undefined') {
  try {
    // Only set up if React isn't already available
    if (!globalThis.React) {
      const React = require('react')
      globalThis.React = React
      if (!globalThis.ReactDOM) {
        globalThis.ReactDOM = require('react-dom')
      }
    }
  } catch (e) {
    // Silently fail if React isn't available - it might be in some build contexts
  }
}

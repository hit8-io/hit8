// Node.js require hook to ensure React is available before styled-components loads
// This file gets executed early in the Node.js module loading process via NODE_OPTIONS

const Module = require('module')
const path = require('path')
const originalRequire = Module.prototype.require

// Pre-load React and make it available globally immediately
try {
  // Try to resolve react from the current working directory
  const reactPath = require.resolve('react', { paths: [process.cwd(), __dirname] })
  const React = originalRequire.call(Module, reactPath)
  
  // Make React available globally before any other modules load
  if (typeof global !== 'undefined') {
    global.React = React
    global.ReactDOM = React // styled-components might check for ReactDOM too
  }
  if (typeof globalThis !== 'undefined') {
    globalThis.React = React
    globalThis.ReactDOM = React
  }
} catch (e) {
  // If React can't be loaded here, we'll try again when styled-components loads
}

// Hook into require to ensure React is available when styled-components loads
Module.prototype.require = function(...args) {
  const moduleId = args[0]
  
  // If styled-components is being loaded, ensure React is available first
  if (typeof moduleId === 'string' && (moduleId.includes('styled-components') || moduleId === 'styled-components')) {
    try {
      // Ensure React is available globally
      if ((typeof global === 'undefined' || !global.React) && (typeof globalThis === 'undefined' || !globalThis.React)) {
        const reactPath = require.resolve('react', { paths: [process.cwd(), __dirname] })
        const React = originalRequire.call(this, reactPath)
        
        if (typeof global !== 'undefined') {
          global.React = React
        }
        if (typeof globalThis !== 'undefined') {
          globalThis.React = React
        }
      }
    } catch (e) {
      // If React isn't available, continue anyway
      console.warn('Warning: Could not load React for styled-components:', e.message)
    }
  }
  
  return originalRequire.apply(this, args)
}

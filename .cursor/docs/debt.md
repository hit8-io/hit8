# Technical Debt

This document tracks known technical debt items that should be addressed in the future.

## React Flow nodeTypes/edgeTypes Warning Suppression

**Status:** Workaround implemented  
**Priority:** Low  
**Created:** 2025-01-31

### Issue

React Flow displays a warning in development mode:
```
[React Flow]: It looks like you've created a new nodeTypes or edgeTypes object. 
If this wasn't on purpose please define the nodeTypes/edgeTypes outside of the 
component or memoize them. Help: https://reactflow.dev/error#002
```

### Root Cause

This is a **false positive warning** triggered by React Strict Mode. The warning appears even when:
- `nodeTypes` and `edgeTypes` props are completely omitted from the ReactFlow component
- React Flow's built-in default node/edge types are being used
- All props are properly memoized with stable references

React Strict Mode intentionally double-renders components in development, which causes React Flow's internal `useNodeOrEdgeTypes` hook to incorrectly detect "new" objects even when none are being passed.

### Current Workaround

A `console.warn` interceptor has been added to `frontend/src/components/GraphView.tsx` that suppresses this specific warning in development mode. The interceptor:
- Only suppresses the specific React Flow warning message
- Only runs in development mode (`NODE_ENV === 'development'`)
- Allows all other warnings to pass through normally

### Future Fix Options

1. **Wait for React Flow fix**: Monitor React Flow GitHub issues for a fix to this known Strict Mode false positive
2. **Disable React Strict Mode**: Not recommended as it helps catch real issues in development
3. **Upgrade React Flow**: Check if newer versions have addressed this issue
4. **Remove workaround**: Once React Flow fixes the issue, remove the `console.warn` interceptor

### Related Issues

- React Flow GitHub: https://github.com/xyflow/xyflow/issues/3923
- React Flow Documentation: https://reactflow.dev/learn/troubleshooting/common-errors

### Code Location

- Workaround: `frontend/src/components/GraphView.tsx` (lines 5-18)
- ReactFlow component: `frontend/src/components/GraphView.tsx` (line 373)


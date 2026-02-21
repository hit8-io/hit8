// Centralized formatting styles for reuse across components

export const styles = {
  // Full-screen centered container (for loading/empty states)
  fullScreenCentered: 'min-h-screen bg-background text-white flex items-center justify-center',
  
  // Full-screen centered with padding
  fullScreenCenteredPadded: 'min-h-screen bg-background text-white flex items-center justify-center px-4',
  
  // Text styles
  textCenter: 'text-center',
  textLarge: 'text-xl mb-2',
  textSmall: 'text-sm text-slate-400',
  
  // Page container
  pageContainer: 'bg-background text-slate-300 antialiased selection:bg-indigo-500/30 min-h-screen font-sans',
} as const

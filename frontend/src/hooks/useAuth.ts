import { useState, useEffect, useMemo } from 'react'
import { initializeApp, getApps, FirebaseApp } from 'firebase/app'
import { getAuth, User as FirebaseUser, signOut, onAuthStateChanged, getRedirectResult } from 'firebase/auth'
import { logError } from '../utils/errorHandling'
import { setSentryUser } from '../utils/sentry'
import type { User } from '../types'

interface UseAuthResult {
  user: User | null
  idToken: string | null
  loading: boolean
  firebaseApp: FirebaseApp | null
  isConfigValid: boolean
  logout: () => Promise<void>
}

export function useAuth(): UseAuthResult {
  const [user, setUser] = useState<User | null>(null)
  const [idToken, setIdToken] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [firebaseApp, setFirebaseApp] = useState<FirebaseApp | null>(null)

  const firebaseConfig = useMemo(() => ({
    apiKey: import.meta.env.VITE_GOOGLE_IDENTITY_PLATFORM_KEY,
    authDomain: import.meta.env.VITE_GOOGLE_IDENTITY_PLATFORM_DOMAIN,
    projectId: import.meta.env.VITE_GCP_PROJECT,
  }), [])

  const isConfigValid = !!(firebaseConfig.apiKey && firebaseConfig.authDomain && firebaseConfig.projectId)

  useEffect(() => {
    if (!isConfigValid) {
      setLoading(false)
      return
    }

    // Clear any stale Firebase auth state from sessionStorage BEFORE initializing Firebase
    // This prevents "missing initial state" errors from stale redirect attempts
    try {
      if (typeof window !== 'undefined' && window.sessionStorage) {
        const keys = Object.keys(sessionStorage)
        keys.forEach((key) => {
          if (
            key.startsWith('firebase:authUser:') ||
            key.startsWith('firebase:redirectUser:') ||
            key.includes('firebase:authState')
          ) {
            try {
              sessionStorage.removeItem(key)
            } catch {
              // Ignore errors when clearing storage
            }
          }
        })
      }
    } catch {
      // Ignore errors when accessing sessionStorage
      // This can happen in storage-partitioned environments
    }

    const app = getApps().length === 0 ? initializeApp(firebaseConfig) : getApps()[0]
    setFirebaseApp(app)

    const auth = getAuth(app)
    
    // Handle any pending redirect results on initialization
    // This prevents "missing initial state" errors from stale redirect attempts
    getRedirectResult(auth)
      .then((result) => {
        if (result) {
          // Redirect result handled successfully - auth state will update via onAuthStateChanged
          // No need to do anything here as the state change handler will process it
        }
      })
      .catch((error: unknown) => {
        const err = error as { code?: string; message?: string }
        // Handle specific error codes related to redirect state
        if (
          err.code === 'auth/missing-or-invalid-nonce' ||
          err.code === 'auth/argument-error' ||
          err.message?.includes('missing initial state') ||
          err.message?.includes('Unable to process request')
        ) {
          // This is expected when there's no redirect result or stale state
          // Log the error for debugging but don't treat it as fatal
          logError('useAuth: Redirect result error (non-fatal)', {
            code: err.code,
            message: err.message,
          })
        } else {
          // Other errors should be logged
          logError('useAuth: Error getting redirect result', error)
        }
      })
    
    // Wrap onAuthStateChanged in error handling to catch and suppress Firebase internal errors
    const unsubscribe = onAuthStateChanged(
      auth,
      async (firebaseUser: FirebaseUser | null) => {
      try {
        if (firebaseUser) {
          if (!firebaseUser.email) {
            logError('useAuth: User email is required but not provided', {})
            setUser(null)
            setIdToken(null)
            setLoading(false)
            return
          }
          if (!firebaseUser.displayName) {
            logError('useAuth: User display name is required but not provided', {})
            setUser(null)
            setIdToken(null)
            setLoading(false)
            return
          }
          if (!firebaseUser.photoURL) {
            logError('useAuth: User photo URL is required but not provided', {})
            setUser(null)
            setIdToken(null)
            setLoading(false)
            return
          }
          const token = await firebaseUser.getIdToken(false)
          setIdToken(token)
          const userData: User = {
            id: firebaseUser.uid,
            email: firebaseUser.email,
            name: firebaseUser.displayName,
            picture: firebaseUser.photoURL,
          }
          setUser(userData)
          // Set Sentry user context
          setSentryUser({
            id: userData.id,
            email: userData.email,
            name: userData.name,
          })
        } else {
          setUser(null)
          setIdToken(null)
          // Clear Sentry user context on logout
          setSentryUser(null)
        }
      } catch (error) {
        logError('useAuth: Error in auth state change', error)
        setUser(null)
        setIdToken(null)
      } finally {
        setLoading(false)
      }
      },
      (error: unknown) => {
        // Error callback for onAuthStateChanged
        // This catches Firebase internal errors like "missing initial state"
        const err = error as { code?: string; message?: string }
        if (
          err.code === 'auth/missing-or-invalid-nonce' ||
          err.code === 'auth/argument-error' ||
          err.message?.includes('missing initial state') ||
          err.message?.includes('Unable to process request')
        ) {
          // Suppress this error - it's non-fatal and happens when redirect state is missing
          // The auth state will still be properly initialized
          logError('useAuth: Auth state change error (non-fatal, suppressed)', {
            code: err.code,
            message: err.message,
          })
        } else {
          // Log other auth errors
          logError('useAuth: Auth state change error', error)
        }
        // Don't set loading to false here - let the main handler do it
        // This ensures the app doesn't get stuck in loading state
      }
    )

    return unsubscribe
  }, [firebaseConfig, isConfigValid])

  const logout = async () => {
    if (firebaseApp) {
      await signOut(getAuth(firebaseApp))
    }
  }

  return {
    user,
    idToken,
    loading,
    firebaseApp,
    isConfigValid,
    logout,
  }
}


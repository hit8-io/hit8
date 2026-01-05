import { useState, useEffect, useMemo } from 'react'
import { initializeApp, getApps, FirebaseApp } from 'firebase/app'
import { getAuth, User as FirebaseUser, signOut, onAuthStateChanged } from 'firebase/auth'
import { logError } from '../utils/errorHandling'
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

    const app = getApps().length === 0 ? initializeApp(firebaseConfig) : getApps()[0]
    setFirebaseApp(app)

    const auth = getAuth(app)
    const unsubscribe = onAuthStateChanged(auth, async (firebaseUser: FirebaseUser | null) => {
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
          setUser({
            id: firebaseUser.uid,
            email: firebaseUser.email,
            name: firebaseUser.displayName,
            picture: firebaseUser.photoURL,
          })
        } else {
          setUser(null)
          setIdToken(null)
        }
      } catch (error) {
        logError('useAuth: Error in auth state change', error)
        setUser(null)
        setIdToken(null)
      } finally {
        setLoading(false)
      }
    })

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


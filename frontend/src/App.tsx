import { useState, useEffect } from 'react'
import { initializeApp, getApps, FirebaseApp } from 'firebase/app'
import { getAuth, signInWithPopup, GoogleAuthProvider, User, signOut, onAuthStateChanged, createUserWithEmailAndPassword, signInWithEmailAndPassword } from 'firebase/auth'
import ChatInterface from './components/ChatInterface'
import { Button } from './components/ui/button'
import { Input } from './components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './components/ui/card'

// Identity Platform user type
interface IdentityUser {
  id: string
  email: string
  name: string
  picture: string
}

function App() {
  const [user, setUser] = useState<IdentityUser | null>(null)
  const [idToken, setIdToken] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [firebaseApp, setFirebaseApp] = useState<FirebaseApp | null>(null)
  const [authMode, setAuthMode] = useState<'select' | 'email'>('select')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [isSignUp, setIsSignUp] = useState(false)
  const [authError, setAuthError] = useState<string | null>(null)
  const [authLoading, setAuthLoading] = useState(false)

  // Firebase config - using API key and domain from secrets
  const firebaseConfig = {
    apiKey: import.meta.env.VITE_GOOGLE_IDENTITY_PLATFORM_KEY,
    authDomain: import.meta.env.VITE_GOOGLE_IDENTITY_PLATFORM_DOMAIN,
    projectId: import.meta.env.VITE_GCP_PROJECT,
  }

  useEffect(() => {
    // Check Firebase config immediately
    if (!firebaseConfig.apiKey || !firebaseConfig.authDomain || !firebaseConfig.projectId) {
      console.error('Firebase configuration is missing. Please set VITE_GOOGLE_IDENTITY_PLATFORM_KEY, VITE_GOOGLE_IDENTITY_PLATFORM_DOMAIN, and VITE_GCP_PROJECT')
      setLoading(false)
      return
    }

    // Set a timeout to prevent infinite loading
    const timeoutId = setTimeout(() => {
      console.warn('Firebase initialization taking longer than expected')
      setLoading(false)
    }, 5000) // 5 second timeout

    // Initialize Firebase if not already initialized
    let app: FirebaseApp
    try {
      if (getApps().length === 0) {
        app = initializeApp(firebaseConfig)
        setFirebaseApp(app)
      } else {
        app = getApps()[0]
        setFirebaseApp(app)
      }

      const auth = getAuth(app)
      
      // Log current URL for debugging
      console.log('Current URL:', window.location.href)
      
      // Listen for auth state changes
      const unsubscribe = onAuthStateChanged(auth, async (firebaseUser: User | null) => {
        clearTimeout(timeoutId) // Clear timeout once we get a response
        
        console.log('Auth state changed:', firebaseUser ? `User: ${firebaseUser.email}` : 'No user')
        
        if (firebaseUser) {
          try {
            // Get the ID token (don't force refresh for faster response)
            console.log('Getting ID token for user:', firebaseUser.email)
            const token = await firebaseUser.getIdToken(false)
            setIdToken(token)
            
            // Extract user info
            const userInfo: IdentityUser = {
              id: firebaseUser.uid,
              email: firebaseUser.email || '',
              name: firebaseUser.displayName || '',
              picture: firebaseUser.photoURL || '',
            }
            setUser(userInfo)
            console.log('✅ User logged in successfully:', userInfo.email)
          } catch (error) {
            console.error('❌ Error getting ID token:', error)
            setUser(null)
            setIdToken(null)
          }
        } else {
          // No user - set loading to false immediately
          console.log('No user authenticated')
          setUser(null)
          setIdToken(null)
        }
        setLoading(false)
      })

      return () => {
        clearTimeout(timeoutId)
        unsubscribe()
      }
    } catch (error) {
      clearTimeout(timeoutId)
      console.error('Error initializing Firebase:', error)
      setLoading(false)
    }
  }, [])

  const handleLogin = async () => {
    if (!firebaseApp) {
      console.error('Firebase not initialized')
      return
    }

    const auth = getAuth(firebaseApp)
    
    // Configure Google Auth Provider for popup mode
    const provider = new GoogleAuthProvider()
    provider.addScope('email')
    provider.addScope('profile')
    
    // Set custom parameters - prompt select_account ensures account picker
    provider.setCustomParameters({
      prompt: 'select_account'
    })

    try {
      console.log('Initiating sign in with popup...')
      console.log('Auth domain:', auth.config.authDomain)
      
      // Use signInWithPopup - Firebase will open a popup window
      // Note: Some browsers may convert popups to tabs based on user settings
      // This is normal behavior and the authentication will still work
      const result = await signInWithPopup(auth, provider)
      console.log('✅ Signed in successfully:', result.user.email)
      console.log('User:', result.user.displayName)
      // onAuthStateChanged will handle updating state
    } catch (error: unknown) {
      const err = error as { code?: string; message?: string; customData?: { email?: string } }
      console.error('Error initiating sign in:', err)
      console.error('Error code:', err.code)
      console.error('Error message:', err.message)
      
      // Handle specific popup errors
      if (err.code === 'auth/popup-blocked') {
        alert('Popup blocked by browser. Please allow popups for this site and try again.')
      } else if (err.code === 'auth/popup-closed-by-user') {
        console.log('User closed the popup/tab')
        // Don't show error for user closing popup
      } else if (err.code === 'auth/cancelled-popup-request') {
        console.log('Only one popup request is allowed at a time')
        // This usually resolves itself, just log it
      } else if (err.code === 'auth/account-exists-with-different-credential') {
        alert('An account already exists with the same email address but different sign-in credentials.')
      } else {
        alert(`Sign in error: ${err.message || 'Unknown error'}`)
      }
    }
  }

  const handleLogout = async () => {
    if (!firebaseApp) {
      return
    }

    const auth = getAuth(firebaseApp)
    try {
      await signOut(auth)
      setAuthMode('select')
      setEmail('')
      setPassword('')
      setAuthError(null)
      // User state is automatically handled by onAuthStateChanged
    } catch (error) {
      console.error('Error signing out:', error)
    }
  }

  const handleEmailAuth = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!firebaseApp) {
      console.error('Firebase not initialized')
      return
    }

    setAuthError(null)
    setAuthLoading(true)

    const auth = getAuth(firebaseApp)

    try {
      if (isSignUp) {
        // Sign up with email and password
        const userCredential = await createUserWithEmailAndPassword(auth, email, password)
        console.log('✅ Signed up successfully:', userCredential.user.email)
        // onAuthStateChanged will handle updating state
      } else {
        // Sign in with email and password
        const userCredential = await signInWithEmailAndPassword(auth, email, password)
        console.log('✅ Signed in successfully:', userCredential.user.email)
        // onAuthStateChanged will handle updating state
      }
    } catch (error: unknown) {
      const err = error as { code?: string; message?: string }
      console.error('Email auth error:', err)
      
      let errorMessage = 'An error occurred during authentication'
      if (err.code === 'auth/email-already-in-use') {
        errorMessage = 'This email is already registered. Please sign in instead.'
      } else if (err.code === 'auth/invalid-email') {
        errorMessage = 'Invalid email address.'
      } else if (err.code === 'auth/weak-password') {
        errorMessage = 'Password should be at least 6 characters.'
      } else if (err.code === 'auth/user-not-found') {
        errorMessage = 'No account found with this email. Please sign up first.'
      } else if (err.code === 'auth/wrong-password') {
        errorMessage = 'Incorrect password.'
      } else if (err.code === 'auth/invalid-credential') {
        errorMessage = 'Invalid email or password.'
      } else if (err.code === 'auth/internal-error') {
        // Check if it's a 403 Forbidden (user not approved)
        if (err.message?.includes('403') || err.message?.includes('Forbidden')) {
          errorMessage = 'Sign up is not available. Please contact an administrator.'
        } else {
          errorMessage = 'An internal error occurred. Please try again later.'
        }
      } else if (err.message) {
        errorMessage = err.message
      }
      
      setAuthError(errorMessage)
    } finally {
      setAuthLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </div>
    )
  }

  if (!user || !idToken) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle className="text-2xl">Hit8 Chat</CardTitle>
            <CardDescription>
              {authMode === 'select' 
                ? 'Choose a sign-in method to continue'
                : isSignUp 
                  ? 'Create a new account'
                  : 'Sign in to your account'}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {authMode === 'select' ? (
              <>
                <Button 
                  onClick={handleLogin} 
                  className="w-full"
                  size="lg"
                >
                  Sign in with Google
                </Button>
                <div className="relative">
                  <div className="absolute inset-0 flex items-center">
                    <span className="w-full border-t" />
                  </div>
                  <div className="relative flex justify-center text-xs uppercase">
                    <span className="bg-background px-2 text-muted-foreground">
                      Or continue with
                    </span>
                  </div>
                </div>
                <Button 
                  onClick={() => setAuthMode('email')} 
                  variant="outline"
                  className="w-full"
                  size="lg"
                >
                  Sign in with Email
                </Button>
              </>
            ) : (
              <form onSubmit={handleEmailAuth} className="space-y-4">
                <div className="space-y-2">
                  <label htmlFor="email" className="text-sm font-medium">
                    Email
                  </label>
                  <Input
                    id="email"
                    type="email"
                    placeholder="you@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    disabled={authLoading}
                  />
                </div>
                <div className="space-y-2">
                  <label htmlFor="password" className="text-sm font-medium">
                    Password
                  </label>
                  <Input
                    id="password"
                    type="password"
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    disabled={authLoading}
                    minLength={6}
                  />
                </div>
                {authError && (
                  <div className="text-sm text-destructive bg-destructive/10 p-3 rounded-md">
                    {authError}
                  </div>
                )}
                <Button 
                  type="submit" 
                  className="w-full"
                  size="lg"
                  disabled={authLoading}
                >
                  {authLoading 
                    ? 'Please wait...' 
                    : isSignUp 
                      ? 'Sign Up' 
                      : 'Sign In'}
                </Button>
                <div className="text-center text-sm space-y-2">
                  <button
                    type="button"
                    onClick={() => {
                      setIsSignUp(!isSignUp)
                      setAuthError(null)
                    }}
                    className="text-primary hover:underline"
                    disabled={authLoading}
                  >
                    {isSignUp 
                      ? 'Already have an account? Sign in' 
                      : "Don't have an account? Sign up"}
                  </button>
                  <div>
                    <button
                      type="button"
                      onClick={() => {
                        setAuthMode('select')
                        setEmail('')
                        setPassword('')
                        setAuthError(null)
                        setIsSignUp(false)
                      }}
                      className="text-muted-foreground hover:underline text-xs"
                      disabled={authLoading}
                    >
                      ← Back to sign-in options
                    </button>
                  </div>
                </div>
              </form>
            )}
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background">
      <ChatInterface 
        token={idToken || ''} 
        user={user} 
        onLogout={handleLogout} 
      />
    </div>
  )
}

export default App


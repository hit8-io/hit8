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
    const app = getApps().length === 0 ? initializeApp(firebaseConfig) : getApps()[0]
    setFirebaseApp(app)

    const auth = getAuth(app)
    const unsubscribe = onAuthStateChanged(auth, async (firebaseUser: User | null) => {
      if (firebaseUser) {
        const token = await firebaseUser.getIdToken(false)
        setIdToken(token)
        setUser({
          id: firebaseUser.uid,
          email: firebaseUser.email || '',
          name: firebaseUser.displayName || '',
          picture: firebaseUser.photoURL || '',
        })
      } else {
        setUser(null)
        setIdToken(null)
      }
      setLoading(false)
    })

    return unsubscribe
  }, [])

  const handleLogin = async () => {
    const auth = getAuth(firebaseApp!)
    const provider = new GoogleAuthProvider()
    provider.setCustomParameters({ prompt: 'select_account' })
    await signInWithPopup(auth, provider)
  }

  const handleLogout = async () => {
    await signOut(getAuth(firebaseApp!))
    setAuthMode('select')
    setEmail('')
    setPassword('')
    setAuthError(null)
  }

  const handleEmailAuth = async (e: React.FormEvent) => {
    e.preventDefault()
    setAuthError(null)
    setAuthLoading(true)

    const auth = getAuth(firebaseApp!)
    try {
      if (isSignUp) {
        await createUserWithEmailAndPassword(auth, email, password)
      } else {
        await signInWithEmailAndPassword(auth, email, password)
      }
    } catch (error: unknown) {
      const err = error as { code?: string; message?: string }
      if (err.code === 'auth/internal-error' && (err.message?.includes('403') || err.message?.includes('Forbidden'))) {
        setAuthError('Sign up is not available. Please contact an administrator.')
      } else {
        setAuthError(err.message || 'An error occurred during authentication')
      }
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


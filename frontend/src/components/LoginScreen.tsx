import { useState } from 'react'
import { FirebaseApp } from 'firebase/app'
import { getAuth, signInWithPopup, GoogleAuthProvider, createUserWithEmailAndPassword, signInWithEmailAndPassword } from 'firebase/auth'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card'

interface LoginScreenProps {
  firebaseApp: FirebaseApp
}

export default function LoginScreen({ firebaseApp }: LoginScreenProps) {
  const [authMode, setAuthMode] = useState<'select' | 'email'>('select')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [isSignUp, setIsSignUp] = useState(false)
  const [authError, setAuthError] = useState<string | null>(null)
  const [authLoading, setAuthLoading] = useState(false)

  const handleLogin = async () => {
    setAuthError(null)
    setAuthLoading(true)
    try {
      const auth = getAuth(firebaseApp)
      const provider = new GoogleAuthProvider()
      provider.setCustomParameters({ prompt: 'select_account' })
      await signInWithPopup(auth, provider)
    } catch (error: unknown) {
      const err = error as { code?: string; message?: string }
      if (err.code === 'auth/popup-closed-by-user') {
        // User closed the popup - don't show error
        setAuthError(null)
      } else if (err.message) {
        setAuthError(err.message)
      } else {
        setAuthError('Failed to sign in with Google. Please try again.')
      }
    } finally {
      setAuthLoading(false)
    }
  }

  const handleEmailAuth = async (e: React.FormEvent) => {
    e.preventDefault()
    setAuthError(null)
    setAuthLoading(true)

    const auth = getAuth(firebaseApp)
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
      } else if (err.message) {
        setAuthError(err.message)
      } else {
        setAuthError('An error occurred during authentication')
      }
    } finally {
      setAuthLoading(false)
    }
  }

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
                <svg className="w-5 h-5 mr-2" viewBox="0 0 24 24" aria-hidden="true">
                  <path
                    d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                    fill="#4285F4"
                  />
                  <path
                    d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                    fill="#34A853"
                  />
                  <path
                    d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                    fill="#FBBC05"
                  />
                  <path
                    d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                    fill="#EA4335"
                  />
                </svg>
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


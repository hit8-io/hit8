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
    const auth = getAuth(firebaseApp)
    const provider = new GoogleAuthProvider()
    provider.setCustomParameters({ prompt: 'select_account' })
    await signInWithPopup(auth, provider)
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


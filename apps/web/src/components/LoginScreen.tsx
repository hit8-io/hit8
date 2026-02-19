import { useState } from 'react'
import { FirebaseApp } from 'firebase/app'
import {
  getAuth,
  signInWithPopup,
  GoogleAuthProvider,
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  updateProfile,
  sendEmailVerification,
  sendPasswordResetEmail,
  signOut
} from 'firebase/auth'
import { Button, Input } from '@hit8/ui'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@hit8/ui'
import { GoogleIcon } from './icons/GoogleIcon'

interface LoginScreenProps {
  readonly firebaseApp: FirebaseApp
}

export default function LoginScreen({ firebaseApp }: LoginScreenProps) {
  // Added 'reset' to authMode to handle the Forgot Password view
  const [authMode, setAuthMode] = useState<'select' | 'email' | 'reset'>('select')

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  // New state for password confirmation
  const [confirmPassword, setConfirmPassword] = useState('')

  const [isSignUp, setIsSignUp] = useState(false)
  const [authError, setAuthError] = useState<string | null>(null)
  // New state for success messages (e.g., "Reset link sent")
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const [authLoading, setAuthLoading] = useState(false)

  // Helper function to check if error is a rejection
  const isRejectionError = (err: { code?: string; message?: string }): boolean => {
    if (!err) return false

    const message = err.message?.toLowerCase() || ''
    return (
      err.code === 'auth/operation-not-allowed' ||
      (err.code === 'auth/internal-error' && (
        err.message?.includes('403') ||
        err.message?.includes('Forbidden') ||
        err.message?.includes('permission-denied') ||
        err.message?.includes('Unauthorized email domain')
      )) ||
      message.includes('unauthorized email domain') ||
      message.includes('permission-denied')
    )
  }

  // Helper function to get user-friendly error message
  const getAuthErrorMessage = (err: { code?: string; message?: string }): string => {
    if (isRejectionError(err)) {
      return 'Sign up is not available for your email domain.'
    }

    if (
      err.code === 'auth/invalid-credential' ||
      err.code === 'auth/user-not-found' ||
      err.code === 'auth/wrong-password'
    ) {
      return 'Invalid email or password. Please check your credentials and try again.'
    }

    if (err.code === 'auth/password-does-not-meet-requirements') {
      // Extract password requirement from error message
      // Error format: "Firebase: Missing password requirements: [Password must contain a non-alphanumeric character]"
      if (err.message) {
        const bracketStart = err.message.indexOf('[')
        const bracketEnd = err.message.indexOf(']')
        if (bracketStart >= 0 && bracketEnd > bracketStart) {
          const requirement = err.message.substring(bracketStart + 1, bracketEnd)
          // Remove "Password must" prefix and convert to lowercase for cleaner message
          const cleanRequirement = requirement.replace(/^Password must /i, '').toLowerCase()
          return `Password must ${cleanRequirement}.`
        }
      }
      return 'Password does not meet the requirements. Please check the password policy and try again.'
    }

    if (err.code === 'auth/weak-password') {
      return 'Password is too weak. Please choose a stronger password.'
    }

    if (err.code === 'auth/too-many-requests') {
      return 'Too many failed attempts. Please try again later.'
    }

    if (err.code === 'auth/user-disabled') {
      return 'This account has been disabled.'
    }

    if (err.code === 'auth/email-already-in-use') {
      return 'An account with this email already exists. Please sign in instead.'
    }

    if (err.code === 'auth/network-request-failed') {
      return 'Network error. Please check your connection and try again.'
    }

    if (err.code === 'auth/requires-recent-login') {
      return 'This operation requires recent authentication. Please sign in again.'
    }

    return err.message || 'An error occurred during authentication.'
  }

  const handleLogin = async () => {
    setAuthError(null)
    setSuccessMessage(null)
    setAuthLoading(true)
    try {
      const auth = getAuth(firebaseApp)
      const provider = new GoogleAuthProvider()
      provider.setCustomParameters({ prompt: 'select_account' })
      await signInWithPopup(auth, provider)
    } catch (error: unknown) {
      const err = error as { code?: string; message?: string }
      if (err.code === 'auth/popup-closed-by-user') {
        setAuthError(null)
      } else if (
        err.code === 'auth/missing-or-invalid-nonce' ||
        err.message?.includes('missing initial state') ||
        err.message?.includes('Unable to process request')
      ) {
        // Handle redirect state errors - try clearing sessionStorage and suggest retry
        try {
          if (typeof window !== 'undefined' && window.sessionStorage) {
            const keys = Object.keys(sessionStorage)
            keys.forEach((key) => {
              if (key.startsWith('firebase:authUser:') || key.startsWith('firebase:redirectUser:')) {
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
        }
        setAuthError(
          'Authentication state was cleared. Please try signing in again.'
        )
      } else {
        setAuthError(getAuthErrorMessage(err))
      }
    } finally {
      setAuthLoading(false)
    }
  }

  const handleEmailAuth = async (e: React.FormEvent) => {
    e.preventDefault()
    setAuthError(null)
    setSuccessMessage(null)

    // 1. Frontend Check: Validate passwords match during sign up
    if (isSignUp && password !== confirmPassword) {
      setAuthError("Passwords do not match.")
      return
    }

    setAuthLoading(true)
    const auth = getAuth(firebaseApp)

    try {
      if (isSignUp) {
        const userCredential = await createUserWithEmailAndPassword(auth, email, password)
        const displayName = email.split('@')[0] || 'User'
        const photoURL = `https://ui-avatars.com/api/?name=${encodeURIComponent(displayName)}&background=random`

        await updateProfile(userCredential.user, {
          displayName,
          photoURL,
        })

        // 2. Email Verification: Send link immediately after creation
        await sendEmailVerification(userCredential.user)
        // Sign out the user immediately - they need to verify email before logging in
        await signOut(auth)
        setSuccessMessage("Account created! A verification email has been sent to your inbox. Please verify your email before signing in.")
        setIsSignUp(false) // Switch back to sign-in mode
      } else {
        const userCredential = await signInWithEmailAndPassword(auth, email, password)

        // Check if email is verified - require verification for login
        if (!userCredential.user.emailVerified) {
          // Send a new verification email before signing out
          try {
            await sendEmailVerification(userCredential.user)
            await signOut(auth)
            setAuthError('Please verify your email address before signing in. A new verification email has been sent to your inbox.')
          } catch {
            // If sending verification fails, still sign out and show error
            await signOut(auth)
            setAuthError('Please verify your email address before signing in. Check your inbox for the verification link.')
          }
          return
        }
      }
    } catch (error: unknown) {
      const err = error as { code?: string; message?: string }
      setAuthError(getAuthErrorMessage(err))
    } finally {
      setAuthLoading(false)
    }
  }

  // 3. Password Reset Handler
  const handlePasswordReset = async (e: React.FormEvent) => {
    e.preventDefault()
    setAuthError(null)
    setSuccessMessage(null)

    if (!email) {
      setAuthError("Please enter your email address.")
      return
    }

    setAuthLoading(true)
    const auth = getAuth(firebaseApp)
    try {
      await sendPasswordResetEmail(auth, email)
      setSuccessMessage('If an account exists with this email, a password reset link has been sent.')
    } catch (error: unknown) {
      const err = error as { code?: string; message?: string }
      // Check for rejection errors (e.g., email not found)
      if (err.code === 'auth/user-not-found') {
        // Use generic message to prevent user enumeration
        setAuthError('If an account exists with this email, a password reset link has been sent.')
      } else if (err.code === 'auth/invalid-email') {
        setAuthError('Invalid email address. Please check and try again.')
      } else if (err.code === 'auth/too-many-requests') {
        setAuthError('Too many requests. Please try again later.')
      } else {
        setAuthError(err.message || "Failed to send reset email.")
      }
    } finally {
      setAuthLoading(false)
    }
  }

  // Helper to render the correct card title/description based on mode
  const getCardHeader = () => {
    if (authMode === 'reset') {
      return { title: 'Reset Password', desc: 'Enter your email to receive a reset link' }
    }
    if (authMode === 'select') {
      return { title: 'Welcome to Hit8', desc: 'Choose a sign-in method to continue' }
    }
    return {
      title: 'Welcome to Hit8',
      desc: isSignUp ? 'Create a new account' : 'Sign in to your account'
    }
  }

  // Helper to render the appropriate form content based on auth mode
  const renderAuthContent = () => {
    if (authMode === 'select') {
      return (
        <>
          <Button
            onClick={() => {
              void handleLogin()
            }}
            className="w-full"
            size="lg"
            disabled={authLoading}
            aria-label="Sign in with Google"
          >
            <GoogleIcon className="w-5 h-5 mr-2" />
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
      )
    }

    if (authMode === 'reset') {
      return (
        <form onSubmit={(e) => { void handlePasswordReset(e) }} className="space-y-4">
          <div className="space-y-2">
            <label htmlFor="reset-email" className="text-sm font-medium">Email</label>
            <Input
              id="reset-email"
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              disabled={authLoading}
            />
          </div>

          {authError && (
            <div className="text-sm text-destructive bg-destructive/10 p-3 rounded-md">
              {authError}
            </div>
          )}

          <Button type="submit" className="w-full" size="lg" disabled={authLoading}>
            {authLoading ? 'Sending...' : 'Send Reset Link'}
          </Button>

          <div className="text-center">
            <button
              type="button"
              onClick={() => {
                setAuthMode('email')
                setAuthError(null)
                setSuccessMessage(null)
              }}
              className="text-muted-foreground hover:underline text-xs"
            >
              ← Back to Sign In
            </button>
          </div>
        </form>
      )
    }

    let buttonText = 'Sign In'
    if (authLoading) {
      buttonText = 'Please wait...'
    } else if (isSignUp) {
      buttonText = 'Sign Up'
    }

    return (
      <form onSubmit={(e) => { void handleEmailAuth(e) }} className="space-y-4">
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
          {!isSignUp && (
            <div className="text-right">
              <button
                type="button"
                onClick={() => {
                  setAuthMode('reset')
                  setAuthError(null)
                  setSuccessMessage(null)
                }}
                className="text-xs text-primary hover:underline"
              >
                Forgot password?
              </button>
            </div>
          )}
        </div>

        {isSignUp && (
          <div className="space-y-2">
            <label htmlFor="confirmPassword" className="text-sm font-medium">
              Confirm Password
            </label>
            <Input
              id="confirmPassword"
              type="password"
              placeholder="••••••••"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              disabled={authLoading}
              minLength={6}
            />
          </div>
        )}

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
          {buttonText}
        </Button>

        <div className="text-center text-sm space-y-2">
          <button
            type="button"
            onClick={() => {
              setIsSignUp(!isSignUp)
              setConfirmPassword('')
              setAuthError(null)
              setSuccessMessage(null)
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
                setConfirmPassword('')
                setAuthError(null)
                setSuccessMessage(null)
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
    )
  }

  const { title, desc } = getCardHeader()

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-2xl">{title}</CardTitle>
          <CardDescription>{desc}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">

          {/* Success Message Display */}
          {successMessage && (
            <div className="text-sm text-green-600 bg-green-50 p-3 rounded-md border border-green-200">
              {successMessage}
            </div>
          )}

          {renderAuthContent()}
        </CardContent>
      </Card>
    </div>
  )
}

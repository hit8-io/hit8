import { useState, useEffect, useCallback } from 'react'
import { initializeApp, getApps, FirebaseApp } from 'firebase/app'
import { getAuth, User, signOut, onAuthStateChanged } from 'firebase/auth'
import ChatInterface from './components/ChatInterface'
import LoginScreen from './components/LoginScreen'
import GraphView from './components/GraphView'
import StatusWindow from './components/StatusWindow'
import StatusBar from './components/StatusBar'
import { ErrorBoundary } from './components/ErrorBoundary'
import { Card, CardDescription, CardHeader, CardTitle } from './components/ui/card'
import type { ExecutionState } from './types/execution'

interface IdentityUser {
  id: string
  email: string
  name: string
  picture: string
}

const API_URL = import.meta.env.VITE_API_URL

function App() {
  const [user, setUser] = useState<IdentityUser | null>(null)
  const [idToken, setIdToken] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [firebaseApp, setFirebaseApp] = useState<FirebaseApp | null>(null)
  const [threadId, setThreadId] = useState<string | null>(null)
  const [isChatActive, setIsChatActive] = useState(false)
  const [executionState, setExecutionState] = useState<ExecutionState | null>(null)

  const firebaseConfig = {
    apiKey: import.meta.env.VITE_GOOGLE_IDENTITY_PLATFORM_KEY,
    authDomain: import.meta.env.VITE_GOOGLE_IDENTITY_PLATFORM_DOMAIN,
    projectId: import.meta.env.VITE_GCP_PROJECT,
  }
  const isConfigValid = !!(firebaseConfig.apiKey && firebaseConfig.authDomain && firebaseConfig.projectId)

  useEffect(() => {
    if (!isConfigValid) {
      setLoading(false)
      return
    }

    const app = getApps().length === 0 ? initializeApp(firebaseConfig) : getApps()[0]
    setFirebaseApp(app)

    const auth = getAuth(app)
    const unsubscribe = onAuthStateChanged(auth, async (firebaseUser: User | null) => {
      try {
        if (firebaseUser) {
          if (!firebaseUser.email) {
            console.error('User email is required but not provided')
            setUser(null)
            setIdToken(null)
            setLoading(false)
            return
          }
          if (!firebaseUser.displayName) {
            console.error('User display name is required but not provided')
            setUser(null)
            setIdToken(null)
            setLoading(false)
            return
          }
          if (!firebaseUser.photoURL) {
            console.error('User photo URL is required but not provided')
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
        console.error('Error in auth state change:', error)
        setUser(null)
        setIdToken(null)
      } finally {
        setLoading(false)
      }
    })

    return unsubscribe
  }, [])

  const handleLogout = async () => {
    await signOut(getAuth(firebaseApp!))
  }

  const handleChatStateChange = (active: boolean, threadId?: string | null) => {
    setIsChatActive(active)
    if (threadId) {
      setThreadId(threadId)
    }
  }

  const handleExecutionStateUpdate = useCallback((state: ExecutionState | null) => {
    setExecutionState(state)
  }, [])

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </div>
    )
  }

  if (!isConfigValid) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle className="text-2xl text-destructive">Configuration Error</CardTitle>
            <CardDescription>
              Firebase configuration is missing. Please set VITE_GOOGLE_IDENTITY_PLATFORM_KEY, VITE_GOOGLE_IDENTITY_PLATFORM_DOMAIN, and VITE_GCP_PROJECT
            </CardDescription>
          </CardHeader>
        </Card>
      </div>
    )
  }

  if (!user || !idToken) {
    if (!firebaseApp) {
      return null
    }
    return (
      <LoginScreen 
        firebaseApp={firebaseApp}
      />
    )
  }

  if (!API_URL) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle className="text-2xl text-destructive">Configuration Error</CardTitle>
            <CardDescription>
              API URL is not configured. Please set VITE_API_URL environment variable.
            </CardDescription>
          </CardHeader>
        </Card>
      </div>
    )
  }

  return (
    <ErrorBoundary>
      <div className="h-screen bg-background flex flex-col overflow-hidden">
        {/* Grid Layout */}
        <div className="flex-1 min-h-0 grid grid-cols-12 grid-rows-[auto_1fr] gap-4 p-4 overflow-hidden">
          {/* Chat Interface - Left Column */}
          <div className="col-span-12 lg:col-span-7 row-span-2 flex flex-col min-h-0 overflow-hidden">
            <ChatInterface 
              token={idToken} 
              user={user} 
              onLogout={handleLogout}
              onChatStateChange={handleChatStateChange}
              onExecutionStateUpdate={handleExecutionStateUpdate}
            />
          </div>

          {/* Graph View - Top Right */}
          <div className="col-span-12 lg:col-span-5 row-span-1 flex flex-col min-h-0 overflow-hidden">
            <GraphView
              apiUrl={API_URL}
              token={idToken}
              threadId={threadId}
              isChatActive={isChatActive}
              executionState={executionState}
              onExecutionStateChange={handleExecutionStateUpdate}
            />
          </div>

          {/* Status Window - Bottom Right */}
          <div className="col-span-12 lg:col-span-5 row-span-1 flex flex-col min-h-0 overflow-hidden">
            <StatusWindow
              executionState={executionState}
              isLoading={isChatActive}
            />
          </div>
        </div>

        {/* Status Bar - Bottom Full Width */}
        <StatusBar apiUrl={API_URL} token={idToken} userName={user.name} />
      </div>
    </ErrorBoundary>
  )
}

export default App

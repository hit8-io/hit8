import { useState, useCallback } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom'
import ChatInterface from './components/ChatInterface'
import LoginScreen from './components/LoginScreen'
import GraphView from './components/GraphView'
import StatusWindow from './components/StatusWindow'
import ObservabilityWindow from './components/ObservabilityWindow'
import StatusBar from './components/StatusBar'
import ReportInterface from './components/ReportInterface'
import { Sidebar } from './components/Sidebar'
import { ErrorBoundary } from './components/ErrorBoundary'
import { Card, CardDescription, CardHeader, CardTitle } from './components/ui/card'
import { useLocalStorage } from './hooks/useLocalStorage'
import { useAuth } from './hooks/useAuth'
import { useUserConfig } from './hooks/useUserConfig'
import type { ExecutionState } from './types/execution'

const API_URL = import.meta.env.VITE_API_URL

// Helper to generate ID immediately, avoiding redirect flash
const NewChatRedirect = () => {
  const newId = crypto.randomUUID()
  return <Navigate to={`/chat/${newId}`} replace />
}

// ChatPage component that reads threadId from URL and renders the main app
function ChatPage() {
  const { threadId } = useParams<{ threadId: string }>()
  
  return <AppContent threadId={threadId!} />
}

// Main app content (extracted from original App function)
function AppContent({ threadId }: { threadId: string }) {
  const { user, idToken, loading, firebaseApp, isConfigValid, logout } = useAuth()
  const [isChatActive, setIsChatActive] = useState(false)
  const [executionState, setExecutionState] = useState<ExecutionState | null>(null)
  const [isChatExpanded, setIsChatExpanded] = useLocalStorage<boolean>('chatExpanded', false)
  const [activeTab, setActiveTab] = useState<'chat' | 'reports'>('chat')
  
  const { selection } = useUserConfig(idToken)
  const org = selection?.org
  const project = selection?.project

  const handleChatStateChange = (active: boolean, _threadId?: string | null) => {
    setIsChatActive(active)
  }

  const handleExecutionStateUpdate = useCallback((state: ExecutionState | null) => {
    // Always create a new object reference to ensure React detects the change
    // This is important for triggering useEffect in GraphView
    if (state === null) {
      setExecutionState(null)
    } else {
      setExecutionState({
        ...state,
        history: state.history ? [...state.history] : undefined,
        next: state.next ? [...state.next] : [],
        streamEvents: state.streamEvents ? [...state.streamEvents] : undefined,
      })
    }
  }, [])

  const toggleChatExpanded = useCallback(() => {
    setIsChatExpanded(!isChatExpanded)
  }, [isChatExpanded, setIsChatExpanded])

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
        {/* Sidebar */}
        <Sidebar 
          user={user} 
          onLogout={logout}
          activeTab={activeTab}
          onTabChange={setActiveTab}
        />

        {/* Main Content - Adjusted for sidebar (always minimal width) */}
        <div className="flex-1 min-h-0 ml-16 flex flex-col overflow-hidden">
          {/* Grid Layout */}
          <div className="flex-1 min-h-0 p-4 overflow-hidden transition-all duration-300 ease-in-out">
            <div className="h-full grid grid-cols-12 gap-4">
              {/* Interface - Left Column */}
              <div className={`${isChatExpanded ? 'col-span-12' : 'col-span-12 lg:col-span-7'} h-full flex flex-col min-h-0 overflow-hidden transition-all duration-300 ease-in-out`}>
                {activeTab === 'chat' ? (
                  <ChatInterface 
                    token={idToken}
                    threadId={threadId}
                    org={org}
                    project={project}
                    onChatStateChange={handleChatStateChange}
                    onExecutionStateUpdate={handleExecutionStateUpdate}
                    isExpanded={isChatExpanded}
                    onToggleExpand={toggleChatExpanded}
                  />
                ) : (
                  <ReportInterface 
                    token={idToken} 
                    org={org}
                    project={project}
                    onExecutionStateUpdate={handleExecutionStateUpdate}
                  />
                )}
              </div>

              {/* Graph/Status/Observability - Right Column */}
              {!isChatExpanded && (
                <div className="col-span-12 lg:col-span-5 flex flex-col min-h-0 space-y-4 overflow-hidden transition-all duration-300 ease-in-out">
                  <div className="flex-1 min-h-0">
                    <GraphView
                      apiUrl={API_URL}
                      token={idToken}
                      executionState={executionState}
                      flow={activeTab === 'chat' ? 'chat' : 'report'}
                    />
                  </div>
                  <div className="flex-1 min-h-0">
                    <StatusWindow
                      executionState={executionState}
                      isLoading={isChatActive}
                    />
                  </div>
                  <div className="flex-1 min-h-0">
                    <ObservabilityWindow
                      apiUrl={API_URL}
                      token={idToken}
                      executionState={executionState}
                      isLoading={isChatActive}
                    />
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Status Bar - Bottom Full Width */}
          {user && <StatusBar apiUrl={API_URL} token={idToken} userName={user.name} />}
        </div>
      </div>
    </ErrorBoundary>
  )
}

// Root App component with routing
function App() {
  return (
    <BrowserRouter
      future={{
        v7_startTransition: true,
        v7_relativeSplatPath: true,
      }}
    >
      <Routes>
        <Route path="/chat/:threadId" element={<ChatPage />} />
        <Route path="/" element={<NewChatRedirect />} />
        <Route path="*" element={<NewChatRedirect />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App

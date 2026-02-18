import { useState, useCallback } from 'react'
import * as React from 'react'
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
import { getApiUrl } from './utils/api'

const API_URL = getApiUrl()

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

// ReportPage component that reads threadId from URL and renders the main app
function ReportPage() {
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
  
  const { selection, getAvailableFlows } = useUserConfig(idToken)
  const org = selection?.org
  const project = selection?.project
  
  // Get available flows for current org/project selection
  // Use state + useEffect to ensure reactivity when selection changes
  const [availableFlows, setAvailableFlows] = useState<string[]>([])
  
  // Update flows when selection changes from hook
  React.useEffect(() => {
    if (!selection?.org || !selection?.project) {
      setAvailableFlows([])
      return
    }
    const flows = getAvailableFlows(selection.org, selection.project)
    setAvailableFlows(flows)
  }, [selection, getAvailableFlows])
  
  // Also poll localStorage to catch changes from UserMenu (which uses separate hook instance)
  // This ensures App.tsx reacts when UserMenu updates selection
  React.useEffect(() => {
    const updateFromStorage = () => {
      const storedOrg = localStorage.getItem('activeOrg')
      const storedProject = localStorage.getItem('activeProject')
      
      if (storedOrg && storedProject && getAvailableFlows) {
        const flows = getAvailableFlows(storedOrg, storedProject)
        setAvailableFlows(flows)
      } else {
        setAvailableFlows([])
      }
    }
    
    // Check initially
    updateFromStorage()
    
    // Poll for changes (since same-tab localStorage changes don't trigger storage events)
    const interval = setInterval(updateFromStorage, 100)
    
    // Also listen for storage events (from other tabs)
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === 'activeOrg' || e.key === 'activeProject') {
        updateFromStorage()
      }
    }
    
    window.addEventListener('storage', handleStorageChange)
    
    return () => {
      clearInterval(interval)
      window.removeEventListener('storage', handleStorageChange)
    }
  }, [getAvailableFlows])
  
  // Ensure active tab is valid for current flows
  // If current tab is not available, switch to an available one
  React.useEffect(() => {
    if (availableFlows.length === 0) {
      return // No flows available yet
    }
    
    if (activeTab === 'reports' && !availableFlows.includes('report')) {
      // Report flow not available, switch to chat if available
      if (availableFlows.includes('chat')) {
        setActiveTab('chat')
      }
    } else if (activeTab === 'chat' && !availableFlows.includes('chat')) {
      // Chat flow not available, switch to report if available
      if (availableFlows.includes('report')) {
        setActiveTab('reports')
      }
    }
  }, [activeTab, availableFlows])

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
          availableFlows={availableFlows}
        />

        {/* Main Content - Adjusted for sidebar (always minimal width) */}
        <div className="flex-1 min-h-0 ml-16 flex flex-col overflow-hidden">
          {/* Grid Layout */}
          <div className="flex-1 min-h-0 p-4 overflow-hidden transition-all duration-300 ease-in-out">
            <div className="h-full grid grid-cols-12 gap-4">
              {/* Interface - Left Column */}
              <div className={`${isChatExpanded || activeTab === 'reports' ? 'col-span-12' : 'col-span-12 lg:col-span-7'} h-full flex flex-col min-h-0 overflow-hidden transition-all duration-300 ease-in-out`}>
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

              {/* Graph/Status/Observability - Right Column (only for chat) */}
              {!isChatExpanded && activeTab === 'chat' && (
                <div className="col-span-12 lg:col-span-5 flex flex-col min-h-0 space-y-4 overflow-hidden transition-all duration-300 ease-in-out">
                  <div className="flex-1 min-h-0">
                    <GraphView
                      apiUrl={API_URL}
                      token={idToken}
                      executionState={executionState}
                      flow="chat"
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
                      executionState={executionState}
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
        <Route path="/report/:threadId" element={<ReportPage />} />
        <Route path="/" element={<NewChatRedirect />} />
        <Route path="*" element={<NewChatRedirect />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App

import { Component, ErrorInfo, ReactNode } from 'react'
import { Card, CardDescription, CardHeader, CardTitle, Button } from '@hit8/ui'
import { logError } from '../utils/errorHandling'
import { captureException } from '../utils/sentry'

interface Props {
  readonly children: ReactNode
  readonly fallback?: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    logError('ErrorBoundary: Caught an error', { error, errorInfo })
    
    // Report to Sentry with component stack context
    captureException(error, {
      errorBoundary: {
        componentStack: errorInfo.componentStack,
        errorBoundary: true,
      },
    })
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null })
  }

  render(): ReactNode {
    const defaultFallback: ReactNode = (
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle className="text-2xl text-destructive">Something went wrong</CardTitle>
            <CardDescription>
              {this.state.error?.message || 'An unexpected error occurred'}
            </CardDescription>
          </CardHeader>
          <div className="p-4 pt-0">
            <Button onClick={this.handleReset} className="w-full">
              Try again
            </Button>
          </div>
        </Card>
      </div>
    )

    const renderedContent: ReactNode = this.state.hasError
      ? (this.props.fallback ?? defaultFallback)
      : this.props.children

    return renderedContent
  }
}


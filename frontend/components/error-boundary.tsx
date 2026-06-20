"use client"

import { Component, type ReactNode } from "react"
import { Button } from "@/components/ui/button"
import { AlertTriangle, RefreshCw } from "lucide-react"

interface ErrorBoundaryProps {
  children: ReactNode
  fallback?: ReactNode
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("[ErrorBoundary]", error.message, errorInfo.componentStack)
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback

      return (
        <div className="flex flex-col items-center justify-center min-h-[300px] p-8 text-center">
          <div className="rounded-full bg-red-500/10 p-4 mb-4">
            <AlertTriangle className="h-8 w-8 text-red-400" />
          </div>
          <h3 className="text-lg font-semibold text-foreground mb-2">
            组件加载失败
          </h3>
          <p className="text-sm text-muted-foreground mb-4 max-w-md">
            {this.state.error?.message ?? "发生未知错误"}
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={this.handleReset}
          >
            <RefreshCw className="h-4 w-4 mr-2" />
            重试
          </Button>
        </div>
      )
    }

    return this.props.children
  }
}

export function PageErrorFallback({ message }: { message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] p-8 text-center">
      <div className="rounded-full bg-amber-500/10 p-4 mb-4">
        <AlertTriangle className="h-10 w-10 text-amber-400" />
      </div>
      <h2 className="text-xl font-semibold text-foreground mb-2">
        页面加载失败
      </h2>
      <p className="text-sm text-muted-foreground mb-6">
        {message ?? "无法加载数据，请检查后端服务是否正常运行"}
      </p>
      <Button
        variant="default"
        onClick={() => window.location.reload()}
      >
        <RefreshCw className="h-4 w-4 mr-2" />
        刷新页面
      </Button>
    </div>
  )
}

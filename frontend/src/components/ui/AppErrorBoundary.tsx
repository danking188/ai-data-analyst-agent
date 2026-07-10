import { Component, type ErrorInfo, type ReactNode } from "react";
import { CircleAlert } from "lucide-react";

interface State {
  error: Error | null;
}

export class AppErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(_error: Error, _info: ErrorInfo) {
    // Production logging is intentionally delegated to the configured telemetry adapter.
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <main className="fatal-error">
        <CircleAlert aria-hidden="true" size={34} />
        <h1>页面暂时无法显示</h1>
        <p>界面发生了未预期错误。数据与运行任务不会因此被修改。</p>
        <button className="button button--primary" onClick={() => window.location.reload()}>
          重新载入
        </button>
      </main>
    );
  }
}

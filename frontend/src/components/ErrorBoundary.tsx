import { Component, type ReactNode } from "react";

/** If any screen crashes while drawing, show a message and a reload button
 *  instead of a blank page. A reload is safe: the saved token rejoins the game. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: unknown) {
    console.error(error);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main className="page center">
        <div className="error-panel" role="alert">
          <p>Something went wrong on this screen. Your score is safe.</p>
          <button className="btn" onClick={() => location.reload()}>Reload</button>
        </div>
      </main>
    );
  }
}

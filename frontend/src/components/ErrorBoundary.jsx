import { Component } from 'react'

export default class ErrorBoundary extends Component {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  render() {
    if (this.state.failed)
      return (
        <div
          role="alert"
          className="rounded-xl border border-red-300 bg-white p-6 dark:border-red-800 dark:bg-slate-800"
        >
          <h2 className="text-xl font-semibold">This screen could not load</h2>
          <p className="my-3">
            Check your connection and reload the app. Saved progress stays on this device.
            An unsubmitted session may be lost.
          </p>
          <button
            type="button"
            className="rounded-lg bg-slate-900 px-4 py-2 text-white dark:bg-sky-700"
            onClick={() => window.location.reload()}
          >
            Reload app
          </button>
        </div>
      )
    return this.props.children
  }
}

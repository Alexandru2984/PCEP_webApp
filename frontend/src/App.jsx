import QuizContainer from './components/QuizContainer'
import ThemeToggle from './components/ThemeToggle'
import RuntimeStatus from './components/RuntimeStatus'
import ErrorBoundary from './components/ErrorBoundary'

export default function App() {
  return (
    <div className="min-h-screen bg-slate-50 px-4 py-5 text-slate-900 transition-colors sm:py-8 dark:bg-slate-950 dark:text-slate-100">
      <a
        href="#quiz-main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-white focus:p-3 focus:text-slate-900"
      >
        Skip to quiz
      </a>
      <header className="mx-auto mb-6 flex max-w-3xl items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-slate-900 dark:text-slate-50">
            PCEP Quiz
          </h1>
          <p className="mt-1 text-slate-600 dark:text-slate-400">
            Python Certified Entry-Level Programmer — practice questions with instant
            feedback and detailed explanations.
          </p>
        </div>
        <ThemeToggle />
      </header>

      <main id="quiz-main" tabIndex={-1} className="mx-auto min-w-0 max-w-3xl">
        <RuntimeStatus />
        <ErrorBoundary>
          <QuizContainer />
        </ErrorBoundary>
      </main>

      <footer className="mx-auto mt-8 max-w-3xl text-center text-sm text-slate-600 dark:text-slate-400">
        <details className="mb-4 rounded-lg border border-slate-200 p-3 text-left dark:border-slate-700">
          <summary className="flex cursor-pointer items-center font-medium">
            Keyboard shortcuts ▾
          </summary>
          <ul className="mt-2 space-y-2">
            <li>
              Practice: 1–4 or A–D to answer; Enter or → for the next question after
              feedback.
            </li>
            <li>Exam: 1–4 or A–D to select; ← and → to navigate; F to flag.</li>
            <li>Flashcards: Space or Enter to reveal, then choose a self-rating.</li>
            <li>
              Tab moves between controls; Enter or Space activates buttons. Study
              shortcuts pause while typing or using modifier keys.
            </li>
          </ul>
        </details>
        Practice for the PCEP™ certification · built with Django &amp; React
      </footer>
    </div>
  )
}

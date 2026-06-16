import QuizContainer from './components/QuizContainer'
import ThemeToggle from './components/ThemeToggle'

export default function App() {
  return (
    <div className="min-h-screen bg-slate-50 px-4 py-8 text-slate-900 transition-colors dark:bg-slate-950 dark:text-slate-100">
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

      <main className="mx-auto max-w-3xl">
        <QuizContainer />
      </main>

      <footer className="mx-auto mt-8 max-w-3xl text-center text-sm text-slate-400 dark:text-slate-600">
        Practice for the PCEP™ certification · built with Django &amp; React
      </footer>
    </div>
  )
}

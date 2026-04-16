import QuizContainer from './components/QuizContainer'

export default function App() {
  return (
    <div className="min-h-screen bg-slate-50 py-8 px-4">
      <header className="max-w-3xl mx-auto mb-6">
        <h1 className="text-3xl font-bold text-slate-900">PCEP Quiz</h1>
        <p className="text-slate-600 mt-1">
          Python Certified Entry-Level Programmer — practice questions with instant feedback and detailed explanations.
        </p>
      </header>

      <main className="max-w-3xl mx-auto">
        <QuizContainer />
      </main>

      <footer className="max-w-3xl mx-auto mt-8 text-center text-sm text-slate-500">
        <a
          href="/admin/"
          className="hover:text-slate-700 underline underline-offset-2"
        >
          Admin panel
        </a>
      </footer>
    </div>
  )
}

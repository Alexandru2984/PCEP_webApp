import { useState, useEffect, useCallback } from 'react'
import CodeBlock from './CodeBlock'
import { submitAnswer } from '../api'

// A flip-card study mode: read the snippet, reveal the answer, then self-mark
// "Got it" or "Review later". The reveal POSTs a throwaway guess so the correct
// choice + concept come from the server (answer keys never ship to the client).
// Marks feed the same finish() flow, so the report, drill and mistakes store all
// work for free — "Review later" lands a card in "Practice your mistakes".
export default function FlashcardView({ questions, onFinish, onQuit }) {
  const [index, setIndex] = useState(0)
  const [revealed, setRevealed] = useState(null)
  const [revealing, setRevealing] = useState(false)
  const [items, setItems] = useState([])
  const question = questions[index]

  const reveal = useCallback(async () => {
    if (revealed || revealing) return
    setRevealing(true)
    try {
      const data = await submitAnswer(question.id, question.choices[0].id)
      setRevealed({
        correct_choice_id: data.correct_choice_id,
        correct_explanation: data.correct_explanation,
      })
    } catch {
      // Network hiccup: still flip so the session can continue.
      setRevealed({ correct_choice_id: null, correct_explanation: '' })
    } finally {
      setRevealing(false)
    }
  }, [question, revealed, revealing])

  const mark = (gotIt) => {
    if (!revealed) return
    const item = {
      question,
      pickedChoiceId: gotIt ? revealed.correct_choice_id : null,
      feedback: {
        is_correct: gotIt,
        correct_choice_id: revealed.correct_choice_id,
        correct_explanation: revealed.correct_explanation,
        explanation: '',
      },
    }
    const next = [...items, item]
    if (index + 1 >= questions.length) {
      onFinish(next)
      return
    }
    setItems(next)
    setIndex((i) => i + 1)
    setRevealed(null)
  }

  // Space / Enter flips the card (when not typing in the code editor).
  useEffect(() => {
    const onKey = (e) => {
      const t = e.target
      if (t?.tagName === 'TEXTAREA' || t?.tagName === 'INPUT' || t?.isContentEditable)
        return
      if (!revealed && (e.key === ' ' || e.key === 'Enter')) {
        e.preventDefault()
        reveal()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [revealed, reveal])

  const progress = Math.round((index / questions.length) * 100)

  return (
    <div>
      <div className="mb-4 h-1.5 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
        <div
          className="h-full rounded-full bg-slate-900 transition-all dark:bg-sky-500"
          style={{ width: `${progress}%` }}
        />
      </div>

      <div className="mb-3 flex items-center justify-between gap-3 text-sm">
        <span className="text-slate-500 dark:text-slate-400">
          Flashcard{' '}
          <span className="font-semibold text-slate-700 dark:text-slate-200">
            {index + 1}
          </span>{' '}
          of {questions.length}
        </span>
        <button
          type="button"
          onClick={onQuit}
          className="text-slate-500 underline underline-offset-2 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
        >
          Quit
        </button>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-800">
        <p className="font-semibold text-slate-900 dark:text-slate-100">
          {question.text}
        </p>
        {question.code_snippet && (
          <CodeBlock code={question.code_snippet} className="mt-3" />
        )}

        <ul className="mt-4 space-y-1.5">
          {question.choices.map((choice, i) => {
            const isAnswer = revealed && choice.id === revealed.correct_choice_id
            return (
              <li
                key={choice.id}
                className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-sm ${
                  isAnswer
                    ? 'border-green-500 bg-green-50 text-green-900 dark:border-green-600 dark:bg-green-950/40 dark:text-green-200'
                    : 'border-slate-200 text-slate-700 dark:border-slate-700 dark:text-slate-300'
                }`}
              >
                <span className="font-mono text-slate-500 dark:text-slate-400">
                  {String.fromCharCode(65 + i)}.
                </span>
                <span className="flex-1">{choice.text}</span>
                {isAnswer && (
                  <span className="text-xs font-semibold text-green-700 dark:text-green-400">
                    answer
                  </span>
                )}
              </li>
            )
          })}
        </ul>

        {revealed && revealed.correct_explanation && (
          <div className="mt-3 rounded-lg border border-green-300 bg-green-50 p-3 text-sm whitespace-pre-wrap text-green-900 dark:border-green-800 dark:bg-green-950/40 dark:text-green-200">
            <span className="font-semibold">Why: </span>
            {revealed.correct_explanation}
          </div>
        )}

        {!revealed ? (
          <button
            type="button"
            onClick={reveal}
            disabled={revealing}
            className="mt-5 w-full rounded-lg bg-slate-900 px-6 py-3 font-medium text-white transition-colors hover:bg-slate-700 disabled:opacity-60 dark:bg-sky-600 dark:hover:bg-sky-500"
          >
            {revealing ? 'Revealing…' : 'Reveal answer'}
          </button>
        ) : (
          <div className="mt-5 grid grid-cols-2 gap-3">
            <button
              type="button"
              onClick={() => mark(false)}
              className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 font-medium text-amber-900 transition-colors hover:bg-amber-100 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200 dark:hover:bg-amber-950/60"
            >
              Review later
            </button>
            <button
              type="button"
              onClick={() => mark(true)}
              className="rounded-lg bg-emerald-700 px-4 py-3 font-medium text-white transition-colors hover:bg-emerald-600"
            >
              Got it
            </button>
          </div>
        )}
      </div>

      {!revealed && (
        <p className="mt-3 text-center text-xs text-slate-500 dark:text-slate-400">
          Tip: press <kbd className="font-mono">Space</kbd> to flip the card
        </p>
      )}
    </div>
  )
}

import { describe, expect, it } from 'vitest'
import { validateFeedback } from './questionData'

const question = {
  id: 7,
  choices: [
    { id: 71, text: 'Wrong' },
    { id: 72, text: 'Correct' },
  ],
}

const feedback = {
  is_correct: false,
  correct_choice_id: 72,
  explanation: 'Why the first choice is wrong.',
  correct_explanation: 'Why the second choice is right.',
}

describe('feedback validation', () => {
  it('binds a grading result to its question and selected choice', () => {
    expect(
      validateFeedback({ ...feedback, question_id: 7, choice_id: 71 }, question, 71)
    ).toEqual(feedback)
  })

  it.each([
    [{ ...feedback, is_correct: true }, 71],
    [{ ...feedback, is_correct: false }, 72],
    [{ ...feedback, question_id: 8, choice_id: 71 }, 71],
    [{ ...feedback, question_id: 7, choice_id: 72 }, 71],
    [{ ...feedback, question_id: 7 }, 71],
    [{ ...feedback, choice_id: 71 }, 71],
    [{ ...feedback, explanation: undefined }, 71],
  ])('rejects contradictory feedback %#', (response, pickedChoiceId) => {
    expect(() => validateFeedback(response, question, pickedChoiceId)).toThrow(
      /invalid feedback/i
    )
  })

  it('rejects response fields outside the documented feedback contract', () => {
    expect(() =>
      validateFeedback({ ...feedback, answer_key: [72] }, question, 71)
    ).toThrow(/invalid feedback/i)
  })
})

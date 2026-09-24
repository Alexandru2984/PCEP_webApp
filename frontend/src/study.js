import { DIFFICULTIES, MODULES, publicQuestion, validId } from './questionData'

export const STUDY_LIMIT = 1000
export const DAY_MS = 24 * 60 * 60 * 1000
const MAX_ATTEMPTS = 10_000
const MAX_INTERVAL_DAYS = 60
const object = (value) => value && typeof value === 'object' && !Array.isArray(value)
const integer = (value, min, max) =>
  Number.isSafeInteger(value) && value >= min && value <= max

export function normalizeStudyRecord(record) {
  const allowed = new Set([
    'questionId',
    'module',
    'difficulty',
    'attempts',
    'correct',
    'streak',
    'intervalDays',
    'lastAttempted',
    'nextReview',
  ])
  if (
    !object(record) ||
    Object.keys(record).some((key) => !allowed.has(key)) ||
    !validId(record.questionId) ||
    !MODULES.includes(record.module) ||
    !DIFFICULTIES.includes(record.difficulty) ||
    !integer(record.attempts, 1, MAX_ATTEMPTS) ||
    !integer(record.correct, 0, record.attempts) ||
    !integer(record.streak, 0, record.attempts) ||
    !integer(record.intervalDays, 0, MAX_INTERVAL_DAYS) ||
    typeof record.lastAttempted !== 'string' ||
    record.lastAttempted.length > 40 ||
    typeof record.nextReview !== 'string' ||
    record.nextReview.length > 40
  )
    return null

  const lastAttempted = Date.parse(record.lastAttempted)
  const nextReview = Date.parse(record.nextReview)
  if (
    !Number.isFinite(lastAttempted) ||
    !Number.isFinite(nextReview) ||
    Math.abs(nextReview - (lastAttempted + record.intervalDays * DAY_MS)) > 1000 ||
    (record.streak === 0) !== (record.intervalDays === 0)
  )
    return null

  return {
    questionId: record.questionId,
    module: record.module,
    difficulty: record.difficulty,
    attempts: record.attempts,
    correct: record.correct,
    streak: record.streak,
    intervalDays: record.intervalDays,
    lastAttempted: new Date(lastAttempted).toISOString(),
    nextReview: new Date(nextReview).toISOString(),
  }
}

export function normalizeStudyRecords(value) {
  if (!Array.isArray(value)) return []
  const byId = new Map()
  for (const raw of value.slice(0, STUDY_LIMIT)) {
    const record = normalizeStudyRecord(raw)
    if (!record) continue
    const previous = byId.get(record.questionId)
    if (
      !previous ||
      Date.parse(record.lastAttempted) > Date.parse(previous.lastAttempted)
    )
      byId.set(record.questionId, record)
  }
  return [...byId.values()].sort(
    (a, b) => Date.parse(b.lastAttempted) - Date.parse(a.lastAttempted)
  )
}

function nextInterval(previous) {
  const streak = previous.streak + 1
  if (streak === 1) return 1
  if (streak === 2) return 3
  return Math.min(MAX_INTERVAL_DAYS, Math.max(7, Math.round(previous.intervalDays * 2)))
}

export function updateStudyRecords(records, items, now = Date.now()) {
  if (!Number.isFinite(now)) return normalizeStudyRecords(records)
  const timestamp = new Date(now).toISOString()
  const byId = new Map(
    normalizeStudyRecords(records).map((record) => [record.questionId, record])
  )

  for (const item of Array.isArray(items) ? items : []) {
    const question = publicQuestion(item?.question)
    if (!question || typeof item?.feedback?.is_correct !== 'boolean') continue
    const previous = byId.get(question.id) ?? {
      attempts: 0,
      correct: 0,
      streak: 0,
      intervalDays: 0,
    }
    const isCorrect = item.feedback.is_correct
    const attempts = Math.min(MAX_ATTEMPTS, previous.attempts + 1)
    const correct = Math.min(attempts, previous.correct + (isCorrect ? 1 : 0))
    const streak = isCorrect ? Math.min(attempts, previous.streak + 1) : 0
    const intervalDays = isCorrect ? nextInterval(previous) : 0
    byId.set(question.id, {
      questionId: question.id,
      module: question.module,
      difficulty: question.difficulty,
      attempts,
      correct,
      streak,
      intervalDays,
      lastAttempted: timestamp,
      nextReview: new Date(now + intervalDays * DAY_MS).toISOString(),
    })
  }

  return [...byId.values()]
    .sort((a, b) => Date.parse(b.lastAttempted) - Date.parse(a.lastAttempted))
    .slice(0, STUDY_LIMIT)
}

export function masteryPercent(record) {
  const normalized = normalizeStudyRecord(record)
  if (!normalized) return 0
  const accuracy = normalized.correct / normalized.attempts
  const repetitionEvidence = Math.min(normalized.attempts, 5) / 5
  const intervalEvidence = Math.min(normalized.intervalDays, 30) / 30
  return Math.round(accuracy * 60 + repetitionEvidence * 20 + intervalEvidence * 20)
}

export function studySummary(records, now = Date.now()) {
  const normalized = normalizeStudyRecords(records)
  const due = normalized.filter((record) => Date.parse(record.nextReview) <= now)
  const mastery = normalized.map(masteryPercent)
  return {
    tracked: normalized.length,
    due: due.length,
    strong: normalized.filter(
      (record) => masteryPercent(record) >= 80 && Date.parse(record.nextReview) > now
    ).length,
    averageMastery: mastery.length
      ? Math.round(mastery.reduce((sum, value) => sum + value, 0) / mastery.length)
      : 0,
    nextReview:
      normalized
        .map((record) => Date.parse(record.nextReview))
        .filter((time) => time > now)
        .sort((a, b) => a - b)[0] ?? null,
  }
}

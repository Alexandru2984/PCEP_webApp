import { DIFFICULTIES, MODULES, publicQuestion } from './questionData'
import {
  STUDY_LIMIT,
  adaptivePracticePlan,
  normalizeStudyRecord,
  normalizeStudyRecords,
  studySummary,
  updateStudyRecords,
} from './study'

const VERSION = 1
const BACKUP_VERSION = 2
const LIMIT = 100
const PROGRESS_KEY = 'pcep.progress'
const ACTIVE_EXAM_KEY = 'pcep.activeExam'
const BACKUP_MAX_BYTES = 8 * 1024 * 1024
const ACTIVE_EXAM_MAX_AGE_MS = 24 * 60 * 60 * 1000
const ACTIVE_EXAM_MAX_DURATION_MS = 3 * 60 * 60 * 1000
const MODES = ['practice', 'exam', 'flashcards']
const integer = (v, min, max) => Number.isSafeInteger(v) && v >= min && v <= max
const object = (v) => v && typeof v === 'object' && !Array.isArray(v)
let cachedRaw
let cachedProgress

function read(key, fallback) {
  try {
    const raw = localStorage.getItem(key)
    return raw == null ? fallback : JSON.parse(raw)
  } catch {
    return fallback
  }
}
function write(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
    return true
  } catch {
    window.dispatchEvent(new CustomEvent('pcep-storage-warning'))
    return false
  }
}

function breakdown(value, keys, score, total) {
  if (value == null) return undefined
  if (!object(value) || Object.keys(value).some((k) => !keys.includes(k))) return null
  const out = {}
  for (const [key, row] of Object.entries(value)) {
    if (!object(row) || !integer(row.total, 1, 100) || !integer(row.score, 0, row.total))
      return null
    out[key] = { score: row.score, total: row.total }
  }
  if (
    Object.values(out).reduce((s, r) => s + r.total, 0) !== total ||
    Object.values(out).reduce((s, r) => s + r.score, 0) !== score
  )
    return null
  return out
}
export function validAttempt(a) {
  if (
    !object(a) ||
    typeof a.date !== 'string' ||
    a.date.length > 40 ||
    !Number.isFinite(Date.parse(a.date)) ||
    !MODES.includes(a.mode) ||
    !['', ...MODULES].includes(a.module ?? '') ||
    !['', ...DIFFICULTIES].includes(a.difficulty ?? '') ||
    !integer(a.total, 1, 100) ||
    !integer(a.score, 0, a.total) ||
    !integer(a.elapsedMs ?? 0, 0, 7 * 86400 * 1000) ||
    !integer(a.bestStreak ?? 0, 0, a.total)
  )
    return null
  const byModule = breakdown(a.byModule, MODULES, a.score, a.total)
  const byDifficulty = breakdown(a.byDifficulty, DIFFICULTIES, a.score, a.total)
  if (byModule === null || byDifficulty === null) return null
  return {
    ...(typeof a.id === 'string' && a.id.length <= 80 ? { id: a.id } : {}),
    date: new Date(a.date).toISOString(),
    mode: a.mode,
    module: a.module ?? '',
    difficulty: a.difficulty ?? '',
    score: a.score,
    total: a.total,
    pct: Math.round((a.score / a.total) * 100),
    elapsedMs: a.elapsedMs ?? 0,
    bestStreak: a.bestStreak ?? 0,
    ...(byModule ? { byModule } : {}),
    ...(byDifficulty ? { byDifficulty } : {}),
  }
}
function records(value, normalize) {
  return Array.isArray(value) ? value.slice(0, LIMIT).map(normalize).filter(Boolean) : []
}
function questions(value) {
  const seen = new Set()
  return records(value, publicQuestion).filter((q) => {
    if (seen.has(q.id)) return false
    seen.add(q.id)
    return true
  })
}
function loadProgress() {
  let raw
  try {
    raw = localStorage.getItem(PROGRESS_KEY)
  } catch {
    raw = null
  }
  if (raw && raw === cachedRaw) return cachedProgress
  let saved
  try {
    saved = raw ? JSON.parse(raw) : null
  } catch {
    saved = null
  }
  const data =
    saved?.version === VERSION && object(saved.data)
      ? saved.data
      : {
          history: read('pcep.history', []),
          mistakes: read('pcep.mistakes', []),
          bookmarks: read('pcep.bookmarks', []),
        }
  const result = {
    history: records(data.history, validAttempt),
    mistakes: questions(data.mistakes),
    bookmarks: questions(data.bookmarks),
    study: normalizeStudyRecords(data.study),
  }
  if (raw) {
    cachedRaw = raw
    cachedProgress = result
  }
  return result
}
function saveProgress(data) {
  const existing = read(PROGRESS_KEY, null)
  if (existing?.version > VERSION) {
    window.dispatchEvent(new CustomEvent('pcep-storage-warning'))
    return false
  }
  if (!write(PROGRESS_KEY, { version: VERSION, data })) return false
  cachedRaw = undefined
  cachedProgress = undefined
  // Remove legacy keys only after the complete replacement has been written.
  try {
    for (const key of ['pcep.history', 'pcep.mistakes', 'pcep.bookmarks'])
      localStorage.removeItem(key)
  } catch {
    /* unavailable */
  }
  return true
}

function normalizeSettings(s) {
  if (!object(s)) return null
  if (
    !MODES.includes(s.mode ?? 'practice') ||
    !['', ...MODULES].includes(s.module ?? '') ||
    !['', ...DIFFICULTIES].includes(s.difficulty ?? '') ||
    !integer(s.count, 1, 100)
  )
    return null
  return {
    mode: s.mode ?? 'practice',
    module: s.module ?? '',
    difficulty: s.difficulty ?? '',
    count: s.count,
  }
}
export function loadSettings() {
  const saved = read('pcep.settings', null)
  return normalizeSettings(saved?.version === VERSION ? saved.data : saved)
}
export const saveSettings = (settings) =>
  write('pcep.settings', { version: VERSION, data: settings })
export const loadTheme = () => {
  const theme = read('pcep.theme', null)
  return ['light', 'dark'].includes(theme) ? theme : null
}
export const saveTheme = (theme) => write('pcep.theme', theme)
export const loadHistory = () => loadProgress().history
export const loadMistakes = () => loadProgress().mistakes
export const loadBookmarks = () => loadProgress().bookmarks
export const loadStudyProgress = () => loadProgress().study
export const loadDueReviews = (now = Date.now()) =>
  loadStudyProgress()
    .filter((record) => Date.parse(record.nextReview) <= now)
    .sort((a, b) => Date.parse(a.nextReview) - Date.parse(b.nextReview))
export const loadStudySummary = (now = Date.now()) =>
  studySummary(loadStudyProgress(), now)
export const loadAdaptivePlan = (now = Date.now(), limit = 20) =>
  adaptivePracticePlan(loadStudyProgress(), loadMistakes(), now, limit)

function normalizeActiveExam(value, now = Date.now()) {
  const allowed = new Set([
    'config',
    'questions',
    'startedAt',
    'deadline',
    'index',
    'answers',
    'flagged',
  ])
  if (!object(value) || Object.keys(value).some((key) => !allowed.has(key))) return null
  const config = normalizeSettings(value.config)
  if (config?.mode !== 'exam') return null
  if (
    !Array.isArray(value.questions) ||
    value.questions.length < 1 ||
    value.questions.length > LIMIT
  )
    return null
  const normalizedQuestions = value.questions.map(publicQuestion)
  if (
    normalizedQuestions.some((question) => !question) ||
    new Set(normalizedQuestions.map((question) => question.id)).size !==
      normalizedQuestions.length
  )
    return null
  if (
    !integer(value.startedAt, 1, Number.MAX_SAFE_INTEGER) ||
    !integer(value.deadline, 1, Number.MAX_SAFE_INTEGER) ||
    value.deadline <= value.startedAt ||
    value.deadline - value.startedAt > ACTIVE_EXAM_MAX_DURATION_MS ||
    value.startedAt > now + 5 * 60 * 1000 ||
    now - value.deadline > ACTIVE_EXAM_MAX_AGE_MS ||
    !integer(value.index, 0, normalizedQuestions.length - 1) ||
    !object(value.answers) ||
    !Array.isArray(value.flagged)
  )
    return null

  const byId = new Map(
    normalizedQuestions.map((question) => [String(question.id), question])
  )
  const answerEntries = Object.entries(value.answers)
  if (answerEntries.length > normalizedQuestions.length) return null
  const answers = {}
  for (const [questionId, choiceId] of answerEntries) {
    const question = byId.get(questionId)
    if (!question || !question.choices.some((choice) => choice.id === choiceId))
      return null
    answers[questionId] = choiceId
  }
  if (
    value.flagged.length > normalizedQuestions.length ||
    new Set(value.flagged).size !== value.flagged.length ||
    value.flagged.some((id) => !byId.has(String(id)))
  )
    return null

  return {
    config,
    questions: normalizedQuestions,
    startedAt: value.startedAt,
    deadline: value.deadline,
    index: value.index,
    answers,
    flagged: [...value.flagged],
  }
}

export function loadActiveExam() {
  const saved = read(ACTIVE_EXAM_KEY, null)
  const normalized = saved?.version === VERSION ? normalizeActiveExam(saved.data) : null
  if (!normalized) {
    try {
      localStorage.removeItem(ACTIVE_EXAM_KEY)
    } catch {
      /* unavailable */
    }
  }
  return normalized
}
export function saveActiveExam(exam) {
  const normalized = normalizeActiveExam(exam)
  return normalized
    ? write(ACTIVE_EXAM_KEY, { version: VERSION, data: normalized })
    : false
}
export function clearActiveExam() {
  try {
    localStorage.removeItem(ACTIVE_EXAM_KEY)
    return true
  } catch {
    window.dispatchEvent(new CustomEvent('pcep-storage-warning'))
    return false
  }
}

export function appendAttempt(attempt) {
  const normalized = validAttempt({ ...attempt, id: attempt.id ?? crypto.randomUUID() })
  const progress = loadProgress()
  if (!normalized) return progress.history
  const history = [normalized, ...progress.history].slice(0, LIMIT)
  saveProgress({ ...progress, history })
  return history
}
export const clearHistory = () => saveProgress({ ...loadProgress(), history: [] })
export const clearMistakes = () => saveProgress({ ...loadProgress(), mistakes: [] })
export const clearBookmarks = () => saveProgress({ ...loadProgress(), bookmarks: [] })
export const clearStudyProgress = () => saveProgress({ ...loadProgress(), study: [] })

export function updateMistakes(items) {
  const progress = loadProgress()
  // Insertion order is oldest first; do not reverse untouched records on each save.
  const byId = new Map([...progress.mistakes].reverse().map((q) => [q.id, q]))
  for (const item of items) {
    const question = publicQuestion(item?.question)
    if (!question) continue
    byId.delete(question.id)
    if (item.feedback?.is_correct !== true) byId.set(question.id, question)
  }
  const mistakes = [...byId.values()].reverse().slice(0, LIMIT)
  saveProgress({ ...progress, mistakes })
  return mistakes
}
export function updateStudyProgress(items, now = Date.now()) {
  const progress = loadProgress()
  const study = updateStudyRecords(progress.study, items, now)
  saveProgress({ ...progress, study })
  return study
}
export function toggleBookmark(question) {
  const q = publicQuestion(question)
  if (!q) return loadBookmarks()
  const progress = loadProgress()
  const existing = progress.bookmarks.some((item) => item.id === q.id)
  const bookmarks = existing
    ? progress.bookmarks.filter((item) => item.id !== q.id)
    : [q, ...progress.bookmarks].slice(0, LIMIT)
  if (!saveProgress({ ...progress, bookmarks }))
    throw new Error(
      'Could not save the bookmark. Browser storage is unavailable or full.'
    )
  return bookmarks
}

export function exportProgress() {
  return JSON.stringify(
    {
      type: 'pcep-progress',
      version: BACKUP_VERSION,
      exportedAt: new Date().toISOString(),
      ...loadProgress(),
    },
    null,
    2
  )
}
export function parseProgressBackup(raw) {
  if (typeof raw !== 'string' || new Blob([raw]).size > BACKUP_MAX_BYTES)
    throw new Error('Backup must be a JSON file smaller than 8 MB.')
  let data
  try {
    data = JSON.parse(raw)
  } catch {
    throw new Error('This file is not valid JSON.')
  }
  if (
    !object(data) ||
    data.type !== 'pcep-progress' ||
    ![1, BACKUP_VERSION].includes(data.version)
  )
    throw new Error('Unsupported progress backup format or version.')
  const out = {}
  for (const [key, normalize] of [
    ['history', validAttempt],
    ['mistakes', publicQuestion],
    ['bookmarks', publicQuestion],
  ]) {
    if (!Array.isArray(data[key]) || data[key].length > LIMIT)
      throw new Error(`Backup ${key} must contain at most 100 records.`)
    const normalized = data[key].map(normalize)
    if (normalized.some((record) => !record))
      throw new Error(`Backup contains invalid ${key} records.`)
    out[key] = normalized
  }
  if (data.version === BACKUP_VERSION) {
    if (!Array.isArray(data.study) || data.study.length > STUDY_LIMIT)
      throw new Error(`Backup study must contain at most ${STUDY_LIMIT} records.`)
    const normalized = data.study.map(normalizeStudyRecord)
    if (
      normalized.some((record) => !record) ||
      new Set(normalized.map((record) => record.questionId)).size !== normalized.length
    )
      throw new Error('Backup contains invalid or duplicate study records.')
    out.study = normalized
  } else out.study = []
  // Reject answer metadata outright rather than importing a portable answer bank.
  const forbidden = new Set([
    'is_correct',
    'correct_choice_id',
    'correct_explanation',
    'explanation',
  ])
  if (
    Object.keys(data).some(
      (key) =>
        ![
          'type',
          'version',
          'exportedAt',
          'history',
          'mistakes',
          'bookmarks',
          ...(data.version === BACKUP_VERSION ? ['study'] : []),
        ].includes(key)
    )
  )
    throw new Error('Backup contains unsupported fields.')
  const inspect = (value, depth = 0) => {
    if (depth > 8) throw new Error('Backup contains excessively nested data.')
    if (!object(value) && !Array.isArray(value)) return
    for (const [key, child] of Object.entries(value)) {
      if (forbidden.has(key) || ['__proto__', 'constructor', 'prototype'].includes(key))
        throw new Error('Backup contains unsupported answer metadata or object keys.')
      inspect(child, depth + 1)
    }
  }
  inspect(data)
  return out
}
export function importProgress(backup) {
  // Revalidate even when the caller bypasses the file preview UI.
  const incoming = parseProgressBackup(
    JSON.stringify({
      type: 'pcep-progress',
      version: BACKUP_VERSION,
      ...backup,
      study: backup.study ?? [],
    })
  )
  const progress = loadProgress()
  const attemptKey = (a) =>
    a.id ??
    [a.date, a.mode, a.module, a.difficulty, a.score, a.total, a.elapsedMs].join('|')
  const history = [
    ...new Map(
      [...progress.history, ...incoming.history].map((a) => [attemptKey(a), a])
    ).values(),
  ]
    .sort((a, b) => Date.parse(b.date) - Date.parse(a.date))
    .slice(0, LIMIT)
  const mergeQuestions = (key) =>
    [
      ...new Map([...incoming[key], ...progress[key]].map((q) => [q.id, q])).values(),
    ].slice(0, LIMIT)
  const merged = {
    history,
    mistakes: mergeQuestions('mistakes'),
    bookmarks: mergeQuestions('bookmarks'),
    study: [
      ...new Map(
        [...progress.study, ...incoming.study]
          .sort((a, b) => {
            const time = Date.parse(a.lastAttempted) - Date.parse(b.lastAttempted)
            return time || a.attempts - b.attempts
          })
          .map((record) => [record.questionId, record])
      ).values(),
    ]
      .sort((a, b) => Date.parse(b.lastAttempted) - Date.parse(a.lastAttempted))
      .slice(0, STUDY_LIMIT),
  }
  if (!saveProgress(merged))
    throw new Error(
      'Import could not be saved. Existing progress was kept. Free browser storage and retry.'
    )
  return merged
}

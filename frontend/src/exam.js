export const EXAM_SECONDS_PER_QUESTION = 80

export const PCEP_30_02_PRESET = Object.freeze({
  value: 'pcep-30-02',
  count: 30,
  durationSeconds: 40 * 60,
  distribution: Object.freeze({
    module1: 7,
    module2: 8,
    module3: 7,
    module4: 8,
  }),
})

export function examDurationLabel(questionCount) {
  const total = Math.max(0, questionCount) * EXAM_SECONDS_PER_QUESTION
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const seconds = total % 60
  const parts = []
  if (hours) parts.push(`${hours}h`)
  if (minutes) parts.push(`${minutes}m`)
  if (seconds || parts.length === 0) parts.push(`${seconds}s`)
  return parts.join(' ')
}

export function validPcep30_02Set(data, questions) {
  if (
    data?.preset !== PCEP_30_02_PRESET.value ||
    data?.count !== PCEP_30_02_PRESET.count ||
    !Array.isArray(questions) ||
    questions.length !== PCEP_30_02_PRESET.count
  )
    return false
  const distribution = Object.fromEntries(
    Object.keys(PCEP_30_02_PRESET.distribution).map((module) => [module, 0])
  )
  for (const question of questions) {
    if (!(question.module in distribution)) return false
    distribution[question.module] += 1
  }
  return Object.entries(PCEP_30_02_PRESET.distribution).every(
    ([module, expected]) => distribution[module] === expected
  )
}

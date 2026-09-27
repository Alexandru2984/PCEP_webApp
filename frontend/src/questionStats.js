import { DIFFICULTIES, MODULES } from './questionData'
import { OBJECTIVE_VALUES } from './syllabus'

const MAX_QUESTION_COUNT = 1_000_000
const object = (value) => value && typeof value === 'object' && !Array.isArray(value)
const count = (value) =>
  Number.isSafeInteger(value) && value >= 0 && value <= MAX_QUESTION_COUNT
const sameKeys = (value, keys) =>
  object(value) &&
  Object.keys(value).length === keys.length &&
  keys.every((key) => Object.hasOwn(value, key))

function countMap(value, keys) {
  if (!sameKeys(value, keys) || keys.some((key) => !count(value[key]))) return null
  return Object.fromEntries(keys.map((key) => [key, value[key]]))
}

function countMatrix(value, rowKeys) {
  if (!sameKeys(value, rowKeys)) return null
  const normalized = {}
  for (const key of rowKeys) {
    const row = countMap(value[key], DIFFICULTIES)
    if (!row) return null
    normalized[key] = row
  }
  return normalized
}

const sum = (values) => values.reduce((total, value) => total + value, 0)

export function normalizeQuestionStats(value) {
  if (!object(value) || !count(value.total)) return null
  const byModule = countMap(value.by_module, MODULES)
  const byDifficulty = countMap(value.by_difficulty, DIFFICULTIES)
  const byObjective = countMap(value.by_objective, OBJECTIVE_VALUES)
  const matrix = countMatrix(value.matrix, MODULES)
  const objectiveMatrix = countMatrix(value.objective_matrix, OBJECTIVE_VALUES)
  if (
    !byModule ||
    !byDifficulty ||
    !byObjective ||
    !matrix ||
    !objectiveMatrix ||
    !Number.isSafeInteger(value.pass_threshold) ||
    value.pass_threshold < 1 ||
    value.pass_threshold > 100 ||
    !Array.isArray(value.modules) ||
    value.modules.length !== MODULES.length
  )
    return null

  const moduleRows = new Map()
  for (const row of value.modules) {
    if (
      !object(row) ||
      !MODULES.includes(row.value) ||
      moduleRows.has(row.value) ||
      typeof row.label !== 'string' ||
      !row.label.trim() ||
      row.label.length > 100 ||
      !count(row.total) ||
      DIFFICULTIES.some((difficulty) => !count(row[difficulty]))
    )
      return null
    moduleRows.set(row.value, {
      value: row.value,
      label: row.label,
      total: row.total,
      ...Object.fromEntries(
        DIFFICULTIES.map((difficulty) => [difficulty, row[difficulty]])
      ),
    })
  }

  if (
    sum(Object.values(byModule)) !== value.total ||
    sum(Object.values(byDifficulty)) !== value.total ||
    sum(Object.values(byObjective)) !== value.total ||
    MODULES.some(
      (module) =>
        sum(Object.values(matrix[module])) !== byModule[module] ||
        moduleRows.get(module)?.total !== byModule[module] ||
        DIFFICULTIES.some(
          (difficulty) =>
            moduleRows.get(module)?.[difficulty] !== matrix[module][difficulty]
        )
    ) ||
    OBJECTIVE_VALUES.some(
      (objective) =>
        sum(Object.values(objectiveMatrix[objective])) !== byObjective[objective]
    ) ||
    DIFFICULTIES.some(
      (difficulty) =>
        sum(MODULES.map((module) => matrix[module][difficulty])) !==
          byDifficulty[difficulty] ||
        sum(
          OBJECTIVE_VALUES.map((objective) => objectiveMatrix[objective][difficulty])
        ) !== byDifficulty[difficulty]
    )
  )
    return null

  return {
    total: value.total,
    by_module: byModule,
    by_difficulty: byDifficulty,
    by_objective: byObjective,
    objective_matrix: objectiveMatrix,
    matrix,
    modules: value.modules.map((row) => moduleRows.get(row.value)),
    pass_threshold: value.pass_threshold,
  }
}

export function getScopeTotal(
  stats,
  selectedModule,
  selectedDifficulty,
  selectedObjective = ''
) {
  if (!stats) return 0
  if (selectedObjective && selectedDifficulty) {
    return stats.objective_matrix?.[selectedObjective]?.[selectedDifficulty] ?? 0
  }
  if (selectedObjective) return stats.by_objective?.[selectedObjective] ?? 0
  if (selectedModule && selectedDifficulty) {
    return stats.matrix?.[selectedModule]?.[selectedDifficulty] ?? 0
  }
  if (selectedModule) return stats.by_module?.[selectedModule] ?? 0
  if (selectedDifficulty) return stats.by_difficulty?.[selectedDifficulty] ?? 0
  return stats.total ?? 0
}

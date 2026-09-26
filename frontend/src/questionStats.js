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

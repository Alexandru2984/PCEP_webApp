export const OBJECTIVES = [
  { value: '1.1', module: 'module1', label: '1.1 · Fundamental terms' },
  { value: '1.2', module: 'module1', label: '1.2 · Python logic & structure' },
  { value: '1.3', module: 'module1', label: '1.3 · Literals & variables' },
  { value: '1.4', module: 'module1', label: '1.4 · Operators & data types' },
  { value: '1.5', module: 'module1', label: '1.5 · Console I/O' },
  { value: '2.1', module: 'module2', label: '2.1 · Decisions & branching' },
  { value: '2.2', module: 'module2', label: '2.2 · Iteration & loops' },
  { value: '3.1', module: 'module3', label: '3.1 · Lists' },
  { value: '3.2', module: 'module3', label: '3.2 · Tuples' },
  { value: '3.3', module: 'module3', label: '3.3 · Dictionaries' },
  { value: '3.4', module: 'module3', label: '3.4 · Strings' },
  { value: '4.1', module: 'module4', label: '4.1 · Functions & returns' },
  { value: '4.2', module: 'module4', label: '4.2 · Arguments & scope' },
  { value: '4.3', module: 'module4', label: '4.3 · Exception hierarchy' },
  { value: '4.4', module: 'module4', label: '4.4 · Exception handling' },
]

export const OBJECTIVE_VALUES = OBJECTIVES.map(({ value }) => value)
export const OBJECTIVE_LABELS = Object.fromEntries(
  OBJECTIVES.map(({ value, label }) => [value, label])
)
export const OBJECTIVE_MODULE = Object.fromEntries(
  OBJECTIVES.map(({ value, module }) => [value, module])
)

export const validObjective = (value, module) =>
  OBJECTIVE_VALUES.includes(value) && (!module || OBJECTIVE_MODULE[value] === module)

export const objectivesForModule = (module) =>
  module ? OBJECTIVES.filter((objective) => objective.module === module) : OBJECTIVES

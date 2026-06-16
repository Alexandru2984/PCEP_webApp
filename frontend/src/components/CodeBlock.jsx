// Tiny zero-dependency Python syntax highlighter. The code background is always
// dark (in both themes), so tokens use a fixed bright-on-dark palette. A single
// combined regex tokenizes in one pass, so keywords inside strings/comments are
// not mis-highlighted.

const KEYWORDS = new Set([
  'False',
  'None',
  'True',
  'and',
  'as',
  'assert',
  'async',
  'await',
  'break',
  'class',
  'continue',
  'def',
  'del',
  'elif',
  'else',
  'except',
  'finally',
  'for',
  'from',
  'global',
  'if',
  'import',
  'in',
  'is',
  'lambda',
  'nonlocal',
  'not',
  'or',
  'pass',
  'raise',
  'return',
  'try',
  'while',
  'with',
  'yield',
])

const BUILTINS = new Set([
  'print',
  'len',
  'range',
  'int',
  'str',
  'float',
  'list',
  'dict',
  'set',
  'tuple',
  'bool',
  'type',
  'input',
  'abs',
  'sum',
  'min',
  'max',
  'sorted',
  'reversed',
  'enumerate',
  'zip',
  'map',
  'filter',
  'open',
  'isinstance',
  'id',
  'round',
  'format',
  'repr',
  'ord',
  'chr',
  'bin',
  'hex',
  'object',
])

const TOKEN =
  /(#[^\n]*)|("""[\s\S]*?"""|'''[\s\S]*?'''|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|(\b\d[\d_]*\.?\d*\b)|(\b[A-Za-z_]\w*\b)/g

function highlight(code) {
  const nodes = []
  let last = 0
  let key = 0
  let m
  TOKEN.lastIndex = 0
  while ((m = TOKEN.exec(code)) !== null) {
    if (m.index > last) nodes.push(code.slice(last, m.index))
    const [text, comment, string, number, ident] = m
    let cls = null
    if (comment) cls = 'text-slate-500 italic'
    else if (string) cls = 'text-emerald-300'
    else if (number) cls = 'text-amber-300'
    else if (KEYWORDS.has(ident)) cls = 'text-sky-400'
    else if (BUILTINS.has(ident)) cls = 'text-violet-300'

    nodes.push(
      cls ? (
        <span key={key++} className={cls}>
          {text}
        </span>
      ) : (
        text
      )
    )
    last = m.index + text.length
  }
  if (last < code.length) nodes.push(code.slice(last))
  return nodes
}

export default function CodeBlock({ code, className = '' }) {
  return (
    <pre
      className={`overflow-x-auto rounded-lg bg-slate-900 p-4 text-sm leading-relaxed text-slate-100 ring-1 ring-slate-800 ${className}`}
    >
      <code>{highlight(code)}</code>
    </pre>
  )
}

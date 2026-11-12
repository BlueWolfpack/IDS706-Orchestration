/** Lightweight CSV header sniff for the setup form (browser-side only). */

export function sniffCsvHeaders(text: string): string[] {
  const firstLine = text.split(/\r?\n/).find((l) => l.trim().length > 0) ?? ''
  if (!firstLine) return []

  const seps = [',', ';', '\t', '|'] as const
  let best: string[] = []
  for (const sep of seps) {
    const cols = splitCsvLine(firstLine, sep)
      .map((c) => c.trim().replace(/^"|"$/g, ''))
      .filter(Boolean)
    if (cols.length > best.length) best = cols
  }
  return best
}

function splitCsvLine(line: string, sep: string): string[] {
  const out: string[] = []
  let cur = ''
  let inQuotes = false
  for (let i = 0; i < line.length; i++) {
    const ch = line[i]
    if (ch === '"') {
      if (inQuotes && line[i + 1] === '"') {
        cur += '"'
        i++
      } else {
        inQuotes = !inQuotes
      }
      continue
    }
    if (ch === sep && !inQuotes) {
      out.push(cur)
      cur = ''
      continue
    }
    cur += ch
  }
  out.push(cur)
  return out
}

/** Prefer common Kaggle target names when present. */
export function guessTargetColumn(columns: string[]): string {
  const preferred = [
    'churned',
    'churn',
    'target',
    'label',
    'class',
    'survived',
    'Survived',
    'outcome',
    'y',
  ]
  const lower = Object.fromEntries(columns.map((c) => [c.toLowerCase(), c]))
  for (const p of preferred) {
    if (lower[p.toLowerCase()]) return lower[p.toLowerCase()]
  }
  // Last column is a common Kaggle convention.
  return columns[columns.length - 1] ?? ''
}

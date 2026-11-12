import { useState, type ReactNode } from 'react'

type Lang = 'python' | 'bash' | 'plain'

/** Strip shared leading indent so paste into a def body isn't double-indented. */
function dedent(code: string): string {
  const lines = code.replace(/\r\n/g, '\n').split('\n')
  let min = Infinity
  for (const line of lines) {
    if (!line.trim()) continue
    const n = line.match(/^ */)?.[0].length ?? 0
    if (n < min) min = n
  }
  if (!Number.isFinite(min) || min === 0) return code.replace(/\s+$/, '')
  return lines
    .map((l) => (l.length >= min ? l.slice(min) : l))
    .join('\n')
    .replace(/\s+$/, '')
}

/** Tiny highlighter — no Prism/Shiki dep. Good enough for guide paste blocks. */
function highlightPython(code: string): ReactNode[] {
  const out: ReactNode[] = []
  // comment | string | keyword-ish token | other
  const re =
    /(#[^\n]*)|('''[\s\S]*?'''|"""[\s\S]*?"""|'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*")|(\b(?:False|True|None|and|as|assert|async|await|break|class|continue|def|del|elif|else|except|finally|for|from|global|if|import|in|is|lambda|nonlocal|not|or|pass|raise|return|try|while|with|yield)\b)|(\b\d+(?:\.\d+)?\b)/g
  let last = 0
  let m: RegExpExecArray | null
  let i = 0
  while ((m = re.exec(code))) {
    if (m.index > last) out.push(code.slice(last, m.index))
    const [full, comment, str, kw, num] = m
    if (comment) out.push(<span key={i++} className="text-mist">{comment}</span>)
    else if (str) out.push(<span key={i++} className="text-teal">{str}</span>)
    else if (kw) out.push(<span key={i++} className="font-semibold text-amber">{kw}</span>)
    else if (num) out.push(<span key={i++} className="text-teal/80">{num}</span>)
    else out.push(full)
    last = m.index + full.length
  }
  if (last < code.length) out.push(code.slice(last))
  return out
}

function highlightBash(code: string): ReactNode[] {
  const out: ReactNode[] = []
  const re = /(#[^\n]*)|('(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*")/g
  let last = 0
  let m: RegExpExecArray | null
  let i = 0
  while ((m = re.exec(code))) {
    if (m.index > last) out.push(code.slice(last, m.index))
    const [full, comment, str] = m
    if (comment) out.push(<span key={i++} className="text-mist">{comment}</span>)
    else if (str) out.push(<span key={i++} className="text-teal">{str}</span>)
    else out.push(full)
    last = m.index + full.length
  }
  if (last < code.length) out.push(code.slice(last))
  return out
}

function renderCode(code: string, lang: Lang): ReactNode {
  if (lang === 'python') return highlightPython(code)
  if (lang === 'bash') return highlightBash(code)
  return code
}

export function CopyBlock({ code, lang = 'plain' }: { code: string; lang?: Lang }) {
  const [copied, setCopied] = useState(false)
  const text = lang === 'python' ? dedent(code) : code
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      /* clipboard unavailable */
    }
  }
  return (
    <div className="relative">
      {lang !== 'plain' ? (
        <span className="absolute left-2 top-2 z-10 font-mono text-[10px] uppercase tracking-wider text-mist/80">
          {lang}
        </span>
      ) : null}
      <pre
        className={`overflow-x-auto rounded border border-line bg-ink-2 p-3 pr-20 font-mono text-xs leading-relaxed text-paper ${
          lang !== 'plain' ? 'pt-7' : ''
        }`}
      >
        <code>{renderCode(text, lang)}</code>
      </pre>
      <button
        type="button"
        onClick={copy}
        className="absolute right-2 top-2 rounded border border-line bg-panel px-2 py-0.5 text-xs text-mist hover:border-teal hover:text-teal"
      >
        {copied ? 'Copied' : 'Copy'}
      </button>
    </div>
  )
}

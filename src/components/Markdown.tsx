import { useState, type ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import { useT } from '../i18n'
import remarkGfm from 'remark-gfm'
import { isMeaningfulInlineCode } from '../utils/inlineCode'

interface MarkdownProps {
  content: string
}

function inlineCodeText(children: ReactNode): string {
  if (typeof children === 'string') return children
  if (Array.isArray(children)) return children.map(inlineCodeText).join('')
  if (children == null || typeof children === 'boolean') return ''
  if (typeof children === 'object' && 'props' in (children as object)) {
    const el = children as { props?: { children?: ReactNode; className?: string } }
    return inlineCodeText(el.props?.children)
  }
  return String(children)
}

function languageFromChildren(children: ReactNode): string | null {
  const walk = (node: ReactNode): string | null => {
    if (node == null || typeof node === 'boolean') return null
    if (Array.isArray(node)) {
      for (const n of node) {
        const hit = walk(n)
        if (hit) return hit
      }
      return null
    }
    if (typeof node === 'object' && 'props' in node) {
      const el = node as { props?: { className?: string; children?: ReactNode } }
      const cls = el.props?.className || ''
      const m = /language-([^\s]+)/.exec(cls)
      if (m) return m[1]
      return walk(el.props?.children)
    }
    return null
  }
  return walk(children)
}

function CodeBlock({ children }: { children: ReactNode }) {
  const t = useT()
  const [copied, setCopied] = useState(false)
  const raw = inlineCodeText(children).replace(/\n$/, '')
  const lang = languageFromChildren(children)

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(raw)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      // ignore
    }
  }

  return (
    <div className="group relative mb-3 last:mb-0">
      <div className="pointer-events-none absolute right-1.5 top-1.5 z-[1] flex items-center gap-1.5">
        {lang ? (
          <span className="rounded px-1.5 py-0.5 font-mono text-[10px] leading-none text-[var(--text-dim)] opacity-80">
            {lang}
          </span>
        ) : null}
        <button
          type="button"
          title={copied ? t('common.copied') : t('common.copy')}
          aria-label={copied ? t('common.copied') : t('common.copy')}
          onClick={(e) => {
            e.preventDefault()
            e.stopPropagation()
            void onCopy()
          }}
          className={[
            'pointer-events-auto inline-flex h-7 w-7 items-center justify-center rounded-md border border-[var(--border-subtle)] bg-[var(--bg-elevated)] text-[var(--text-muted)] shadow-sm transition-colors',
            'opacity-100 sm:opacity-0 sm:group-hover:opacity-100 sm:focus-within:opacity-100',
            'hover:border-[var(--border)] hover:text-[var(--text-h)]',
            copied ? 'opacity-100 text-emerald-400' : '',
          ].join(' ')}
        >
          {copied ? (
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-3.5 w-3.5">
              <path d="M20 6L9 17l-5-5" />
            </svg>
          ) : (
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-3.5 w-3.5">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
              <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
            </svg>
          )}
        </button>
      </div>
      <pre className="overflow-x-auto rounded-lg border border-[var(--border-subtle)] bg-[var(--bg)] p-3 font-mono text-[13px] leading-relaxed">
        {children}
      </pre>
    </div>
  )
}

export function Markdown({ content }: MarkdownProps) {
  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
          strong: ({ children }) => (
            <strong className="font-medium">{children}</strong>
          ),
          em: ({ children }) => <em className="italic">{children}</em>,
          code: ({ className, children }) => {
            const text = inlineCodeText(children)
            const isBlock =
              /language-/.test(className || '') || text.includes('\n')
            if (isBlock) {
              return <code className={className}>{children}</code>
            }
            // Plain words / short literals: no chip — model over-uses backticks.
            if (!isMeaningfulInlineCode(text)) {
              return <>{children}</>
            }
            return (
              <code className="rounded-[3px] bg-[var(--code-inline-bg)] px-1 py-px font-mono text-[0.92em] text-[var(--text)]">
                {children}
              </code>
            )
          },
          pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
          ul: ({ children }) => (
            <ul className="mb-3 list-disc space-y-1 pl-5 last:mb-0 marker:text-[var(--text)]">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="mb-3 list-decimal space-y-1 pl-5 last:mb-0 marker:text-[var(--text)]">{children}</ol>
          ),
          li: ({ children }) => <li className="leading-[1.7]">{children}</li>,
          h1: ({ children }) => (
            <h1 className="mb-2.5 mt-5 text-[1.5em] font-bold leading-snug text-[var(--text-h)] first:mt-0 [&_*]:font-bold">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="mb-2 mt-4 text-[1.32em] font-[650] leading-snug text-[var(--text-h)] first:mt-0 [&_*]:font-[650]">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="mb-2 mt-3.5 text-[1.15em] font-semibold leading-snug text-[var(--text-h)] first:mt-0 [&_*]:font-semibold">
              {children}
            </h3>
          ),
          blockquote: ({ children }) => (
            <blockquote className="mb-3 border-l-2 border-[var(--accent-solid)] pl-3 text-[var(--text-muted)] last:mb-0">
              {children}
            </blockquote>
          ),
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="text-[var(--accent)] underline decoration-[var(--accent)]/40 underline-offset-2 hover:decoration-[var(--accent)]"
            >
              {children}
            </a>
          ),
          table: ({ children }) => (
            <div className="mb-3 overflow-x-auto last:mb-0">
              <table className="w-full border-collapse text-[0.92em]">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border border-[var(--border)] bg-[var(--surface)] px-2.5 py-1.5 text-left font-medium text-[var(--text-h)]">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border border-[var(--border)] px-2.5 py-1.5">{children}</td>
          ),
          hr: () => <hr className="my-4 border-[var(--border-subtle)]" />,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}

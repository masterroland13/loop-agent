import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface MarkdownProps {
  content: string
}

export function Markdown({ content }: MarkdownProps) {
  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
          strong: ({ children }) => (
            <strong className="font-semibold text-[var(--text-h)]">{children}</strong>
          ),
          em: ({ children }) => <em className="italic">{children}</em>,
          code: ({ className, children }) => {
            const isBlock = /language-/.test(className || '')
            if (isBlock) {
              return <code className={className}>{children}</code>
            }
            return (
              <code className="rounded-[4px] bg-[var(--surface-active)] px-1.5 py-0.5 font-mono text-[0.85em] text-[var(--text-h)]">
                {children}
              </code>
            )
          },
          pre: ({ children }) => (
            <pre className="mb-3 overflow-x-auto rounded-lg border border-[var(--border-subtle)] bg-[var(--bg)] p-3 font-mono text-[13px] leading-relaxed last:mb-0">
              {children}
            </pre>
          ),
          ul: ({ children }) => (
            <ul className="mb-3 list-disc space-y-1 pl-5 last:mb-0 marker:text-[var(--text-dim)]">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="mb-3 list-decimal space-y-1 pl-5 last:mb-0 marker:text-[var(--text-dim)]">{children}</ol>
          ),
          li: ({ children }) => <li className="leading-[1.7]">{children}</li>,
          h1: ({ children }) => (
            <h1 className="mb-2.5 mt-5 text-[1.5em] font-bold leading-snug text-[var(--text-h)] first:mt-0">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="mb-2 mt-4 text-[1.32em] font-[650] leading-snug text-[var(--text-h)] first:mt-0">{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 className="mb-2 mt-3.5 text-[1.15em] font-semibold leading-snug text-[var(--text-h)] first:mt-0">{children}</h3>
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

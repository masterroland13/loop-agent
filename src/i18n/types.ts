/** UI locale — shell chrome only; Agent reply language follows the user message. */
export type Locale = 'zh' | 'en'

export type MessageTree = {
  [key: string]: string | MessageTree
}

/** Dot-path lookup; missing keys fall back to zh then the key itself. */
export function lookup(tree: MessageTree, path: string): string | undefined {
  const parts = path.split('.')
  let node: string | MessageTree | undefined = tree
  for (const p of parts) {
    if (node == null || typeof node === 'string') return undefined
    node = node[p]
  }
  return typeof node === 'string' ? node : undefined
}

export function formatMessage(
  template: string,
  vars?: Record<string, string | number>,
): string {
  if (!vars) return template
  return template.replace(/\{(\w+)\}/g, (_, name: string) =>
    vars[name] != null ? String(vars[name]) : `{${name}}`,
  )
}

export function normalizeLocale(value: unknown): Locale {
  return value === 'en' ? 'en' : 'zh'
}

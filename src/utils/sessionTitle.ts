/** Sidebar title from the first instruction. One short subject, not a mid-word clip. */
export function sessionTitleFromInstruction(content: string, fallback: string): string {
  const flat = content.replace(/\s+/g, ' ').trim()
  if (!flat) return fallback
  const sentence = flat.split(/[。！？!?；;\n]/)[0]?.trim() || flat
  if (sentence.length <= 24) return sentence
  return `${sentence.slice(0, 24).trimEnd()}…`
}

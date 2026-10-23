export type ChatAttachment = {
  id?: string
  name: string
  kind: 'file'
  status: 'pending' | 'ready' | 'error'
  error?: string
  size?: number
  contentType?: string
  url?: string
  /** Local object URL for image chip preview (revoke on remove). */
  previewUrl?: string
  /** Local key for React lists before id exists */
  localKey: string
}

const IMAGE_NAME_RE = /\.(png|jpe?g|gif|webp|bmp)$/i

export function isImageAttachment(att: {
  contentType?: string | null
  name?: string
  filename?: string
}): boolean {
  const ctype = (att.contentType || '').toLowerCase()
  if (ctype.startsWith('image/') && !ctype.includes('svg')) return true
  const name = att.name || att.filename || ''
  return IMAGE_NAME_RE.test(name)
}

export function draftContentForSend(userText: string): string {
  return userText.trim()
}

/** Send when textarea nonempty OR at least one ready attachment; block while any pending. */
export function canSendDraft(userText: string, attachments: ChatAttachment[]): boolean {
  const pending = attachments.some((a) => a.status === 'pending')
  if (pending) return false
  const ready = attachments.some((a) => a.status === 'ready' && a.id)
  if (ready) return true
  return Boolean(userText.trim())
}

export function readyAttachmentIds(attachments: ChatAttachment[]): string[] {
  return attachments.filter((a) => a.status === 'ready' && a.id).map((a) => a.id as string)
}

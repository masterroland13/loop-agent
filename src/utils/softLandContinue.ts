/** Build the user message for 「继续」after a soft-land wrap-up (mirrors backend). */

function extractMarkdownSection(text: string, heading: string): string {
  if (!text) return ''
  const marker = heading.startsWith('## ') ? heading : `## ${heading}`
  const start = text.indexOf(marker)
  if (start < 0) return ''
  let bodyStart = start + marker.length
  if (text[bodyStart] === '\n') bodyStart += 1
  const rest = text.slice(bodyStart)
  const nextH = rest.indexOf('\n## ')
  const body = nextH < 0 ? rest : rest.slice(0, nextH)
  return body.trim()
}

export function buildSoftLandContinueMessage(opts: {
  turnGoal?: string | null
  softLandReply?: string | null
}): string {
  const reply = opts.softLandReply || ''
  const unfinished = extractMarkdownSection(reply, '## 未完成 / 阻塞')
  const nextSteps = extractMarkdownSection(reply, '## 建议下一步')
  const lines = [
    '请从上一轮软着陆处继续推进，不要重复已经完成的工作；直接调用工具接着干。',
  ]
  const goal = (opts.turnGoal || '').trim()
  if (goal) {
    lines.push(`本轮目标：${goal}`)
  }
  lines.push('')
  lines.push('对照上轮收口：')
  lines.push('### 未完成 / 阻塞')
  lines.push(unfinished || '（上轮未写明；请根据工具轨迹与对话自行判断缺口。）')
  lines.push('')
  lines.push('### 建议下一步')
  lines.push(nextSteps || '（上轮未写明；优先消除阻塞，再对照目标推进。）')
  lines.push('')
  lines.push(
    '要求：优先处理未完成项；证据不足时据实说明；仍受本会话「最大工具轮次」限制，触顶可再次软着陆。',
  )
  return lines.join('\n')
}

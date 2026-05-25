import fs from 'node:fs'
import { createRequire } from 'node:module'
import path from 'node:path'

import type {
  HarnessRenderState,
  HarnessStreamFrame,
  WechatHarnessCase,
} from './wechat-harness-types'

type RawFixture = {
  name: string
  description?: string
  content: string
  presentation?: Record<string, unknown>
  covers?: string[]
  manual_focus?: string[]
  expected?: {
    renderBlockTypes?: string[]
    visibleBlockTypes?: string[]
    mcqCount?: number
  }
}

type AiMessageStateModule = {
  deriveAiMessageRenderState(input: {
    content: string
    presentation?: Record<string, unknown>
    parseBlocks: boolean
  }): HarnessRenderState
}

type RenderSchemaModule = {
  createRenderModel(input: Partial<HarnessRenderState>): HarnessRenderState
}

declare const __non_webpack_require__: NodeJS.Require | undefined

function resolveWebRoot(): string {
  const explicit = String(process.env.DEEPTUTOR_WEB_ROOT || '').trim()
  if (explicit) return explicit

  const cwd = process.cwd()
  const standaloneSuffix = `${path.sep}.next${path.sep}standalone`
  if (cwd.endsWith(standaloneSuffix)) {
    return path.resolve(cwd, '..', '..')
  }
  return cwd
}

const webRoot = resolveWebRoot()
const repoRoot = path.resolve(webRoot, '..')
const wxRequire =
  typeof __non_webpack_require__ === 'function'
    ? __non_webpack_require__
    : createRequire(import.meta.url)
const aiMessageState = wxRequire(
  path.join(repoRoot, 'wx_miniprogram/utils/ai-message-state.js')
) as AiMessageStateModule
const renderSchema = wxRequire(
  path.join(repoRoot, 'wx_miniprogram/utils/render-schema.js')
) as RenderSchemaModule

function readJson<T>(relativePath: string): T {
  const absolutePath = path.join(repoRoot, relativePath)
  return JSON.parse(fs.readFileSync(absolutePath, 'utf8')) as T
}

function deriveState(input: {
  content: string
  presentation?: Record<string, unknown>
  parseBlocks?: boolean
  streamPhase?: HarnessRenderState['streamPhase']
}): HarnessRenderState {
  const state = aiMessageState.deriveAiMessageRenderState({
    content: input.content,
    presentation: input.presentation,
    parseBlocks: input.parseBlocks ?? true,
  })
  return renderSchema.createRenderModel({
    ...state,
    streamPhase: input.streamPhase ?? 'complete',
  })
}

function firstVisibleLine(content: string): string {
  return (
    content
      .split(/\n+/)
      .map(line => line.trim())
      .find(Boolean) || content.slice(0, 36)
  )
}

function firstHalf(content: string): string {
  if (content.length <= 80) return content
  return content.slice(0, Math.max(40, Math.floor(content.length / 2))).trimEnd()
}

function buildStreamFrames(fixture: RawFixture): HarnessStreamFrame[] {
  const frames: HarnessStreamFrame[] = []
  const firstLine = firstVisibleLine(fixture.content)
  frames.push({
    id: 'chunk-1',
    label: 'Chunk 1',
    state: deriveState({
      content: firstLine,
      parseBlocks: true,
      streamPhase: 'streaming',
    }),
  })
  frames.push({
    id: 'chunk-mid',
    label: 'Chunk mid',
    state: deriveState({
      content: firstHalf(fixture.content),
      parseBlocks: true,
      streamPhase: 'streaming',
    }),
  })
  frames.push({
    id: 'chunk-final',
    label: 'Final payload',
    state: deriveState({
      content: fixture.content,
      presentation: fixture.presentation,
      parseBlocks: true,
      streamPhase: 'complete',
    }),
  })
  return frames
}

function summarizeState(state: HarnessRenderState) {
  return {
    renderBlockTypes: (state.blocks || [])
      .map(block => String(block.type || 'unknown'))
      .filter(type => type !== 'blank'),
    visibleBlockTypes: (state.visibleBlocks || [])
      .map(block => String(block.type || 'unknown'))
      .filter(type => type !== 'blank'),
    mcqCount: state.mcqCards ? state.mcqCards.length : 0,
    renderableContent: state.renderableContent,
    originalContent: state.originalContent,
  }
}

function compareFinalAndHistory(
  finalState: HarnessRenderState,
  historyState: HarnessRenderState
): string[] {
  const warnings: string[] = []
  const finalSummary = summarizeState(finalState)
  const historySummary = summarizeState(historyState)
  if (
    JSON.stringify(finalSummary.renderBlockTypes) !==
    JSON.stringify(historySummary.renderBlockTypes)
  ) {
    warnings.push('render block types differ between final stream and history hydrate')
  }
  if (
    JSON.stringify(finalSummary.visibleBlockTypes) !==
    JSON.stringify(historySummary.visibleBlockTypes)
  ) {
    warnings.push('visible block types differ between final stream and history hydrate')
  }
  if (finalSummary.mcqCount !== historySummary.mcqCount) {
    warnings.push('mcq count differs between final stream and history hydrate')
  }
  if (finalSummary.renderableContent !== historySummary.renderableContent) {
    warnings.push('renderable content differs between final stream and history hydrate')
  }
  if (finalSummary.originalContent !== historySummary.originalContent) {
    warnings.push('original folded content differs between final stream and history hydrate')
  }
  return warnings
}

function buildFixtureCase(
  fixture: RawFixture,
  index: number,
  sourcePath: string,
  prefix: string
): WechatHarnessCase {
  const finalState = deriveState({
    content: fixture.content,
    presentation: fixture.presentation,
    parseBlocks: true,
    streamPhase: 'complete',
  })
  const historyState = deriveState({
    content: fixture.content,
    presentation: fixture.presentation,
    parseBlocks: true,
    streamPhase: 'complete',
  })
  const parityWarnings = compareFinalAndHistory(finalState, historyState)
  const stateSummary = summarizeState(finalState)
  return {
    id: `${prefix}-${fixture.name || index}`,
    name: fixture.name || `${prefix}-${index}`,
    title: fixture.name.replace(/_/g, ' ').replace(/\b[a-z]/g, char => char.toUpperCase()),
    surface: fixture.presentation ? 'chat' : 'chat',
    sourcePath,
    description:
      fixture.description ||
      'Replay a canonical mini-program rendering fixture through the Web shadow harness.',
    content: fixture.content,
    tags: fixture.covers || [fixture.presentation ? 'structured' : 'markdown'],
    manualFocus: fixture.manual_focus || [],
    expectations: {
      blockTypes: fixture.expected?.renderBlockTypes || stateSummary.renderBlockTypes,
      visibleBlockTypes: fixture.expected?.visibleBlockTypes || stateSummary.visibleBlockTypes,
      mcqCount: fixture.expected?.mcqCount ?? stateSummary.mcqCount,
      historyParity: parityWarnings.length === 0,
    },
    streamFrames: buildStreamFrames(fixture),
    finalState,
    historyState,
    parityWarnings,
  }
}

function buildOperationalCase(fixture: RawFixture, index: number): WechatHarnessCase {
  return buildFixtureCase(fixture, index, 'web/lib/wechat-harness-data.ts', 'operational')
}

// Keys whose values are server-only grading authority. They must never reach
// the SSR HTML or hydrated DOM because the harness ships fixture data as
// React props, which Next.js serializes verbatim into client payload.
// Camel and snake variants both listed because render-schema.js normalizes
// to camelCase but raw fixtures keep snake.
const SENSITIVE_AUTHORITY_KEYS: ReadonlySet<string> = new Set([
  'correct_answer',
  'correctAnswer',
  'scoring_points',
  'scoringPoints',
  'grading_key',
  'gradingKey',
  'grading_authority',
  'gradingAuthority',
  'explanation',
  'reference_answer',
  'referenceAnswer',
  'answer_key',
  'answerKey',
  'grader_secret',
  'graderSecret',
  // followup_context is the wx_miniprogram envelope that wraps
  // correct_answer/scoring_points; questionId is already lifted to the
  // top-level mcqCard, so dropping the whole context is safe for UI.
  'followup_context',
  'followupContext',
])

const LEAK_TEXT_PATTERNS: ReadonlyArray<RegExp> = [
  /正确答案[：:]\s*[^\n]*/g,
  /参考答案[：:]\s*[^\n]*/g,
  /答案是[：:]?\s*[^\n。]*/g,
  /correct_answer\s*[:=]\s*[^\s,}]+/gi,
  /scoring_points\s*[:=]\s*[^\n}]+/gi,
  /grading_key\s*[:=]\s*[^\s,}]+/gi,
  /评分点[：:]\s*[^\n]*/g,
  /采分点[：:]\s*[^\n]*/g,
]

const SCRUB_PLACEHOLDER = '[已折叠：评分后可见]'

function scrubLeakStrings(input: string): string {
  let out = input
  for (const pattern of LEAK_TEXT_PATTERNS) {
    out = out.replace(pattern, SCRUB_PLACEHOLDER)
  }
  return out
}

function redactForClient(value: unknown): unknown {
  if (value === null || value === undefined) return value
  if (typeof value === 'string') return scrubLeakStrings(value)
  if (typeof value !== 'object') return value
  if (Array.isArray(value)) return value.map(redactForClient)
  const source = value as Record<string, unknown>
  const out: Record<string, unknown> = {}
  for (const key of Object.keys(source)) {
    if (SENSITIVE_AUTHORITY_KEYS.has(key)) continue
    out[key] = redactForClient(source[key])
  }
  return out
}

export function sanitizeHarnessCaseForClient(input: WechatHarnessCase): WechatHarnessCase {
  return redactForClient(input) as WechatHarnessCase
}

export function loadWechatHarnessCases(): WechatHarnessCase[] {
  const structuredPath = 'tests/fixtures/wechat_structured_renderer_cases.json'
  const markdownPath = 'tests/fixtures/wechat_markdown_golden_cases.json'
  const structuredCases = readJson<RawFixture[]>(structuredPath).map((fixture, index) =>
    buildFixtureCase(fixture, index, structuredPath, 'structured')
  )
  const markdownCases = readJson<RawFixture[]>(markdownPath).map((fixture, index) =>
    buildFixtureCase(fixture, index, markdownPath, 'markdown')
  )
  const operationalCases = [
    buildOperationalCase(
      {
        name: 'billing_quota_exceeded_surface',
        description: 'Billing 429 and retry copy must stay readable in the mini-program shell.',
        content:
          '今日额度已用完。你可以先查看历史批改记录，或升级到通关版继续使用。\n\n错误码：billing_quota_exceeded',
        covers: ['billing', 'error-state', 'retry-copy'],
        manual_focus: ['错误态不遮挡底部输入栏', '升级引导与重试按钮同时可见'],
      },
      0
    ),
    buildOperationalCase(
      {
        name: 'auth_expired_retry_surface',
        description: 'Expired mobile auth should fail closed with one clear recovery path.',
        content:
          '登录状态已过期，请重新登录后继续。系统不会丢弃当前问题，重新登录后可以回到本轮对话。',
        covers: ['auth', 'resume', 'recovery-copy'],
        manual_focus: ['重新登录文案明确', '不会把 token 错误渲染给用户'],
      },
      1
    ),
  ]
  const allCases = [...structuredCases, ...markdownCases, ...operationalCases]
  return allCases.map(sanitizeHarnessCaseForClient)
}

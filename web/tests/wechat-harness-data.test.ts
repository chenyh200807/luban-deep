import test from 'node:test'
import assert from 'node:assert/strict'

import { loadWechatHarnessCases } from '../lib/wechat-harness-data.ts'

test('wechat harness loads canonical mini-program fixtures through wx render authority', () => {
  const cases = loadWechatHarnessCases()
  assert.ok(cases.length >= 10)

  const structured = cases.find(item => item.id.includes('structured_table'))
  assert.ok(structured)
  assert.ok(structured.finalState.hasStructuredContent)
  assert.equal(structured.expectations.historyParity, true)
  assert.equal(structured.parityWarnings.length, 0)
  assert.ok(structured.finalState.mcqCards && structured.finalState.mcqCards.length > 0)
})

test('wechat harness includes first-visible stream frames and history hydrate states', () => {
  const cases = loadWechatHarnessCases()
  for (const fixture of cases) {
    assert.ok(fixture.streamFrames.length >= 3, fixture.id)
    assert.equal(fixture.streamFrames[0].state.streamPhase, 'streaming')
    assert.equal(fixture.streamFrames.at(-1)?.state.streamPhase, 'complete')
    assert.equal(fixture.historyState.streamPhase, 'complete')
  }
})

test('wechat harness client payload never carries grading authority', () => {
  const cases = loadWechatHarnessCases()
  const serialized = JSON.stringify(cases)
  const forbiddenMarkers = [
    'correct_answer',
    'correctAnswer',
    'scoring_points',
    'scoringPoints',
    'grading_key',
    'gradingKey',
    'grading_authority',
    'gradingAuthority',
    'reference_answer',
    'referenceAnswer',
    'answer_key',
    'answerKey',
    'followup_context',
    'followupContext',
    'LEAK_',
    '正确答案：',
    '参考答案：',
    '答案是',
    '评分点：',
    '采分点：',
  ]
  for (const marker of forbiddenMarkers) {
    assert.equal(serialized.includes(marker), false, `client payload must not include ${marker}`)
  }
})

test('wechat harness preserves render contract while redacting authority', () => {
  const cases = loadWechatHarnessCases()
  const structured = cases.find(item => item.id.includes('structured_table'))
  assert.ok(structured)
  // Render contract must still be intact for the harness UI:
  assert.ok(structured.finalState.mcqCards && structured.finalState.mcqCards.length > 0)
  assert.ok(structured.finalState.blocks && structured.finalState.blocks.length > 0)
  assert.ok(structured.finalState.visibleBlocks.length > 0)
  assert.ok(structured.expectations.visibleBlockTypes.includes('mcq'))
  // mcqCard must still expose questionId + options so the harness can wire
  // the option buttons; only the grading authority envelope is stripped.
  const card = (structured.finalState.mcqCards || [])[0] as Record<string, unknown>
  assert.ok(card)
  assert.ok(typeof card.questionId === 'string' && (card.questionId as string).length > 0)
  assert.ok(Array.isArray(card.options))
  assert.equal((card.options as unknown[]).length >= 2, true)
  // The wrapped grading authority envelope must be gone.
  assert.equal('followupContext' in card, false)
  assert.equal('followup_context' in card, false)
})

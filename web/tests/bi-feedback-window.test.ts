import test from 'node:test'
import assert from 'node:assert/strict'

import {
  FEEDBACK_WINDOW_DAYS,
  feedbackWindowHint,
} from '../app/(workspace)/bi/_v2/feedback/feedback-window.ts'

test('FEEDBACK_WINDOW_DAYS is the canonical positive integer days value', () => {
  assert.equal(typeof FEEDBACK_WINDOW_DAYS, 'number')
  assert.ok(Number.isInteger(FEEDBACK_WINDOW_DAYS))
  assert.ok(FEEDBACK_WINDOW_DAYS > 0)
})

test('FEEDBACK_WINDOW_DAYS matches the value passed to getBiFeedback (30 days)', () => {
  // If this assertion ever needs to change, the panel's call to
  // `getBiFeedback({ days: FEEDBACK_WINDOW_DAYS, limit: 100 })` must
  // change together; that is the whole point of centralising the constant.
  assert.equal(FEEDBACK_WINDOW_DAYS, 30)
})

test('feedbackWindowHint renders as `近 {N}d` for the configured window', () => {
  assert.equal(feedbackWindowHint(), '近 30d')
})

test('feedbackWindowHint stays in sync with FEEDBACK_WINDOW_DAYS by construction', () => {
  // Sanity: the hint must contain the days number literally, so any drift
  // between the two would be visible as a string mismatch.
  assert.ok(feedbackWindowHint().includes(String(FEEDBACK_WINDOW_DAYS)))
})

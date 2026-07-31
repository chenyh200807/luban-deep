import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  resolveLearningPreferencePlaybackState,
  resolveLearningPreferencePresentationState,
} from '../lib/learning-preference-state.ts'

const __dirname = dirname(fileURLToPath(import.meta.url))
const webRoot = resolve(__dirname, '..')

async function readWeb(path: string): Promise<string> {
  return readFile(resolve(webRoot, path), 'utf8')
}

test('learning preference distinguishes filtered internal playback from missing telemetry', async () => {
  const panel = await readWeb(
    'app/(workspace)/bi/_v2/learning-pref/BiV2LearningPrefPanel.tsx',
  )
  const api = await readWeb('lib/bi-api.ts')

  assert.ok(api.includes('excludedNonBusinessPlayback'))
  assert.ok(panel.includes('excludedNonBusinessPlayback'))
  assert.ok(panel.includes('resolveLearningPreferencePresentationState({'))
  assert.ok(panel.includes('resolveLearningPreferencePlaybackState({'))
  assert.ok(panel.includes('data-testid="bi-learning-pref-excluded-playback"'))
  assert.ok(panel.includes('data-testid="bi-learning-pref-scope-unknown"'))
  assert.ok(panel.includes('data-testid="bi-learning-pref-playback-scope-unknown"'))
  assert.ok(panel.includes('含内部/测试账号'))
  assert.ok(panel.includes('内部/测试账号播放器事件'))
  assert.equal(panel.includes('埋点未回流'), false)
})

test('playback state stays unknown on a legacy response even when other business data exists', () => {
  assert.equal(
    resolveLearningPreferencePlaybackState({
      playbackAvailable: false,
      scopeDiagnosticAvailable: false,
      excludedPlaybackAvailable: false,
    }),
    'scope_unknown',
  )
  assert.equal(
    resolveLearningPreferencePlaybackState({
      playbackAvailable: false,
      scopeDiagnosticAvailable: true,
      excludedPlaybackAvailable: true,
    }),
    'excluded_playback',
  )
  assert.equal(
    resolveLearningPreferencePlaybackState({
      playbackAvailable: false,
      scopeDiagnosticAvailable: true,
      excludedPlaybackAvailable: false,
    }),
    'known_empty',
  )
  assert.equal(
    resolveLearningPreferencePlaybackState({
      playbackAvailable: true,
      scopeDiagnosticAvailable: false,
      excludedPlaybackAvailable: false,
    }),
    'data',
  )
})

test('learning preference presentation keeps excluded, empty, and unknown states distinct', () => {
  assert.equal(
    resolveLearningPreferencePresentationState({
      hasBusinessData: false,
      scopeDiagnosticAvailable: true,
      excludedPlaybackAvailable: true,
    }),
    'excluded_playback',
  )
  assert.equal(
    resolveLearningPreferencePresentationState({
      hasBusinessData: false,
      scopeDiagnosticAvailable: true,
      excludedPlaybackAvailable: false,
    }),
    'known_empty',
  )
  assert.equal(
    resolveLearningPreferencePresentationState({
      hasBusinessData: false,
      scopeDiagnosticAvailable: false,
      excludedPlaybackAvailable: false,
    }),
    'scope_unknown',
  )
  assert.equal(
    resolveLearningPreferencePresentationState({
      hasBusinessData: true,
      scopeDiagnosticAvailable: false,
      excludedPlaybackAvailable: false,
    }),
    'data',
  )
})

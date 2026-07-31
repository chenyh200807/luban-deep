export type LearningPreferencePresentationState =
  | 'data'
  | 'excluded_playback'
  | 'known_empty'
  | 'scope_unknown'

export type LearningPreferencePlaybackState =
  | 'data'
  | 'excluded_playback'
  | 'known_empty'
  | 'scope_unknown'

export function resolveLearningPreferencePresentationState(input: {
  hasBusinessData: boolean
  scopeDiagnosticAvailable: boolean
  excludedPlaybackAvailable: boolean
}): LearningPreferencePresentationState {
  if (input.hasBusinessData) return 'data'
  if (input.excludedPlaybackAvailable) return 'excluded_playback'
  if (!input.scopeDiagnosticAvailable) return 'scope_unknown'
  return 'known_empty'
}

export function resolveLearningPreferencePlaybackState(input: {
  playbackAvailable: boolean
  scopeDiagnosticAvailable: boolean
  excludedPlaybackAvailable: boolean
}): LearningPreferencePlaybackState {
  if (input.playbackAvailable) return 'data'
  if (input.excludedPlaybackAvailable) return 'excluded_playback'
  if (!input.scopeDiagnosticAvailable) return 'scope_unknown'
  return 'known_empty'
}

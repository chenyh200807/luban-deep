type WechatHarnessGateInput = {
  nodeEnv?: string
  enableWechatHarness?: string
  publicEnableWechatHarness?: string
}

function isTruthyFlag(value?: string): boolean {
  return String(value || '').trim().toLowerCase() === 'true'
}

export function isWechatHarnessEnabled({
  nodeEnv,
  enableWechatHarness,
  publicEnableWechatHarness: _publicEnableWechatHarness,
}: WechatHarnessGateInput): boolean {
  if (nodeEnv !== 'production') return true
  return isTruthyFlag(enableWechatHarness)
}

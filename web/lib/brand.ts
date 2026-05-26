type BrandEnv = Record<string, string | undefined>

export const DEFAULT_BRAND_NAME = '鲁班智考'

export function resolveBrandCopy(env: BrandEnv = process.env) {
  const brandName = String(env.NEXT_PUBLIC_APP_BRAND_NAME || '').trim() || DEFAULT_BRAND_NAME
  return {
    brandName,
    biTitle: `${brandName} BI 工作台`,
  }
}

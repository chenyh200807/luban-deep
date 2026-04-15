const TRUTHY = new Set(["1", "true", "yes", "on"]);

function envFlag(value: string | undefined): boolean {
  return TRUTHY.has(String(value || "").trim().toLowerCase());
}

export const WEB_AUTH_ENABLED = envFlag(process.env.NEXT_PUBLIC_WEB_AUTH_ENABLED);
export const WEB_LEGACY_SURFACES_ENABLED = envFlag(
  process.env.NEXT_PUBLIC_ENABLE_LEGACY_WEB_SURFACES,
);

export function requiresWebAuth(): boolean {
  return WEB_AUTH_ENABLED;
}

export function allowsLegacyWebSurfaces(): boolean {
  return WEB_LEGACY_SURFACES_ENABLED;
}

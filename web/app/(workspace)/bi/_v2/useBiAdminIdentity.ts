"use client";

import { useSyncExternalStore } from "react";
import {
  BI_ADMIN_SESSION_CHANGED_EVENT,
  getStoredBiAdminSession,
  type BiAdminSession,
} from "@/lib/api";

export type BiAdminIdentity = {
  authenticated: boolean;
  actorId: string;
  displayName: string;
  hasBiAccess: boolean;
  isAdmin: boolean;
  biRole: string;
  biRoleLabel: string;
  canManagePermissions: boolean;
  accessibleTabs: string[];
  matrix: Record<string, string[]>;
  session: BiAdminSession | null;
};

const UNAUTHENTICATED: BiAdminIdentity = {
  authenticated: false,
  actorId: "unauthenticated",
  displayName: "未登录",
  hasBiAccess: false,
  isAdmin: false,
  biRole: "",
  biRoleLabel: "",
  canManagePermissions: false,
  accessibleTabs: [],
  matrix: {},
  session: null,
};

function buildIdentity(session: BiAdminSession | null): BiAdminIdentity {
  if (!session) return UNAUTHENTICATED;
  return {
    authenticated: true,
    actorId: session.userId,
    displayName: session.displayName || session.userId,
    hasBiAccess: Boolean(session.biRole && session.accessibleTabs?.length),
    isAdmin: session.isAdmin,
    biRole: session.biRole || "",
    biRoleLabel: session.biRoleLabel || session.biRole || "",
    canManagePermissions: Boolean(session.canManagePermissions),
    accessibleTabs: Array.isArray(session.accessibleTabs) ? session.accessibleTabs : [],
    matrix: session.biMatrix ?? {},
    session,
  };
}

function subscribe(callback: () => void) {
  if (typeof window === "undefined") return () => {};
  window.addEventListener("storage", callback);
  window.addEventListener(BI_ADMIN_SESSION_CHANGED_EVENT, callback);
  return () => {
    window.removeEventListener("storage", callback);
    window.removeEventListener(BI_ADMIN_SESSION_CHANGED_EVENT, callback);
  };
}

let cachedIdentity: BiAdminIdentity | null = null;
let cachedSessionKey: string | null = null;

function getClientSnapshot(): BiAdminIdentity {
  if (typeof window === "undefined") return UNAUTHENTICATED;
  const session = getStoredBiAdminSession();
  const key = session
    ? `${session.userId}:${session.expiresAt}:${session.biRole}:${(session.accessibleTabs ?? []).join(",")}`
    : "";
  if (key === cachedSessionKey && cachedIdentity) {
    return cachedIdentity;
  }
  cachedSessionKey = key;
  cachedIdentity = buildIdentity(session);
  return cachedIdentity;
}

function getServerSnapshot(): BiAdminIdentity {
  return UNAUTHENTICATED;
}

export function useBiAdminIdentity(): BiAdminIdentity {
  return useSyncExternalStore(subscribe, getClientSnapshot, getServerSnapshot);
}

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
  isAdmin: boolean;
  session: BiAdminSession | null;
};

const UNAUTHENTICATED: BiAdminIdentity = {
  authenticated: false,
  actorId: "unauthenticated",
  displayName: "未登录",
  isAdmin: false,
  session: null,
};

function buildIdentity(session: BiAdminSession | null): BiAdminIdentity {
  if (!session) return UNAUTHENTICATED;
  return {
    authenticated: true,
    actorId: session.userId,
    displayName: session.displayName || session.userId,
    isAdmin: session.isAdmin,
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
  const key = session ? `${session.userId}:${session.expiresAt}` : "";
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

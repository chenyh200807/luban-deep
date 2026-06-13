#!/usr/bin/env node
"use strict";

function parseArgs(argv) {
  const out = {
    port: 9420,
    targetPage: "/packageDeeptutor/pages/report/report",
    baseUrl: process.env.WECHAT_QA_BASE_URL || "http://127.0.0.1:8001",
    authBaseUrl: process.env.WECHAT_QA_AUTH_BASE_URL || "",
    waitMs: Number(process.env.WECHAT_QA_PAGE_WAIT_MS || 800),
  };
  for (let i = 2; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--port") {
      out.port = Number(argv[++i]);
    } else if (arg === "--target-page") {
      out.targetPage = String(argv[++i] || "");
    } else if (arg === "--base-url") {
      out.baseUrl = String(argv[++i] || "");
    } else if (arg === "--auth-base-url") {
      out.authBaseUrl = String(argv[++i] || "");
    } else if (arg === "--wait-ms") {
      out.waitMs = Number(argv[++i] || 800);
    }
  }
  return out;
}

function normalizePagePath(pagePath) {
  const raw = String(pagePath || "").trim();
  return raw && !raw.startsWith("/") ? "/" + raw : raw;
}

function loadAutomator() {
  const candidates = [
    "miniprogram-automator",
    "/opt/homebrew/lib/node_modules/miniprogram-automator",
    "/usr/local/lib/node_modules/miniprogram-automator",
  ];
  const errors = [];
  for (const name of candidates) {
    try {
      return require(name);
    } catch (error) {
      errors.push(String(error && error.message ? error.message : error));
    }
  }
  const err = new Error("miniprogram-automator is not installed or not resolvable");
  err.details = errors.slice(0, 3);
  throw err;
}

function emit(payload, exitCode) {
  process.stdout.write(JSON.stringify(payload) + "\n");
  process.exit(exitCode);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function connectWithRetry(automator, wsEndpoint) {
  let lastError;
  for (let attempt = 1; attempt <= 6; attempt += 1) {
    try {
      return await automator.connect({ wsEndpoint });
    } catch (error) {
      lastError = error;
      await sleep(500);
    }
  }
  throw lastError;
}

async function currentPageSnapshot(miniProgram) {
  const current = await miniProgram.currentPage();
  const currentPage = current && current.path ? current.path : "";
  const pageData = current && typeof current.data === "function" ? await current.data() : {};
  return { current, currentPage, pageData: pageData || {} };
}

async function forceQaBaseUrl(miniProgram, baseUrl) {
  const normalized = String(baseUrl || "").trim();
  if (!normalized) return "";
  return await miniProgram.evaluate(function (nextBaseUrl) {
    const app = getApp();
    if (!app.globalData) app.globalData = {};
    app.globalData.apiUrl = nextBaseUrl;
    app.globalData.gatewayUrl = nextBaseUrl;
    app.globalData.apiCandidates = [nextBaseUrl];
    app.globalData.gatewayCandidates = [nextBaseUrl];
    return {
      apiUrl: app.globalData.apiUrl,
      gatewayUrl: app.globalData.gatewayUrl,
      apiCandidates: app.globalData.apiCandidates,
    };
  }, normalized);
}

async function loginViaHttpIfAvailable(authBaseUrl) {
  const username = String(process.env.WECHAT_QA_USERNAME || "").trim();
  const password = String(process.env.WECHAT_QA_PASSWORD || "");
  const base = String(authBaseUrl || "").trim().replace(/\/$/, "");
  if (!username || !password || !base) {
    return { attempted: false, credential_source: "none" };
  }
  const resp = await fetch(base + "/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  let body = {};
  try {
    body = await resp.json();
  } catch (_err) {}
  const inner = body && (body.data || body);
  const user = (inner && inner.user) || {};
  const token = inner && (inner.token || inner._token || user._token);
  const userId =
    (inner && (inner.user_id || inner.userId || inner.id || inner.uid)) ||
    user.user_id ||
    user.userId ||
    user.id ||
    user.uid ||
    "";
  return {
    attempted: true,
    credential_source: "env_http",
    http_status: resp.status,
    token_present: !!token,
    token,
    expires_at: inner && (inner.expires_at || inner.expiresAt || inner.exp),
    user_id: userId,
  };
}

async function seedAuthStorage(miniProgram, authPayload) {
  if (!authPayload || !authPayload.token) {
    return { token_present: false };
  }
  return await miniProgram.evaluate(function (payload) {
    var nowSeconds = Math.floor(Date.now() / 1000);
    var expiresAt = Number(payload.expires_at || 0);
    if (!Number.isFinite(expiresAt) || expiresAt < nowSeconds + 172800) {
      expiresAt = nowSeconds + 604800;
    }
    wx.setStorageSync("auth_token", payload.token);
    wx.setStorageSync("auth_token_exp", expiresAt);
    if (payload.user_id) {
      wx.setStorageSync("auth_user_id", payload.user_id);
    }
    return {
      token_present: !!wx.getStorageSync("auth_token"),
      user_id_present: !!wx.getStorageSync("auth_user_id"),
    };
  }, {
    token: authPayload.token,
    expires_at: authPayload.expires_at || 0,
    user_id: authPayload.user_id || "",
  });
}

async function readLearningReportViaRuntime(miniProgram, baseUrl) {
  const normalized = String(baseUrl || "").trim().replace(/\/$/, "");
  if (!normalized) return { attempted: false, reason: "missing_base_url" };
  return await miniProgram.evaluate(function (url) {
    return new Promise(function (resolve) {
      var token = wx.getStorageSync("auth_token");
      wx.request({
        url: url,
        method: "GET",
        header: {
          Authorization: token ? "Bearer " + token : "",
          "Content-Type": "application/json",
        },
        timeout: 20000,
        success: function (res) {
          var body = res && res.data && typeof res.data === "object" ? res.data : {};
          var loop = body.grading_to_brain_loop && typeof body.grading_to_brain_loop === "object"
            ? body.grading_to_brain_loop
            : {};
          resolve({
            attempted: true,
            status_code: res && res.statusCode,
            body_keys: Object.keys(body).sort().slice(0, 80),
            has_grading_to_brain_loop: Object.prototype.hasOwnProperty.call(body, "grading_to_brain_loop"),
            loop_status: String(loop.status || ""),
            loop_next_required_action: String(loop.next_required_action || loop.nextRequiredAction || ""),
            loop_evidence_ref_count: Array.isArray(loop.evidence_refs) ? loop.evidence_refs.length : 0,
            loop_stage_count: Array.isArray(loop.stages) ? loop.stages.length : 0,
          });
        },
        fail: function (err) {
          resolve({
            attempted: true,
            status_code: 0,
            error: String(err && err.errMsg ? err.errMsg : err),
          });
        },
      });
    });
  }, normalized + "/api/v1/mobile/learning-report?event_limit=100&schema_version=2");
}

async function waitForCurrentPage(miniProgram, targetPage, timeoutMs) {
  const startedAt = Date.now();
  let lastSnapshot = await currentPageSnapshot(miniProgram);
  while (Date.now() - startedAt < timeoutMs) {
    if (normalizePagePath(lastSnapshot.currentPage) === targetPage) {
      return lastSnapshot;
    }
    await sleep(500);
    lastSnapshot = await currentPageSnapshot(miniProgram);
  }
  return lastSnapshot;
}

async function loginWithPasswordIfAvailable(miniProgram, targetPage) {
  const username = String(process.env.WECHAT_QA_USERNAME || "").trim();
  const password = String(process.env.WECHAT_QA_PASSWORD || "");
  if (!username || !password) {
    return { attempted: false, credential_source: "none" };
  }

  const manualPagePath =
    "/packageDeeptutor/pages/login/manual?loginMode=password&returnTo=" +
    encodeURIComponent(targetPage) +
    "&username=" +
    encodeURIComponent(username);
  const page = await miniProgram.reLaunch(manualPagePath);
  await page.waitFor(800);
  await page.setData({
    loginMode: "password",
    username,
    password,
    returnTo: targetPage,
  });
  await page.callMethod("handlePasswordLogin");
  const snapshot = await waitForCurrentPage(miniProgram, targetPage, 8000);
  const errorMsg = String(snapshot.pageData.errorMsg || "").trim();
  return {
    attempted: true,
    credential_source: "env",
    reached_target: normalizePagePath(snapshot.currentPage) === targetPage,
    login_error_present: !!errorMsg,
    login_error_message: errorMsg || undefined,
  };
}

(async function main() {
  const args = parseArgs(process.argv);
  const targetPage = args.targetPage || "/packageDeeptutor/pages/report/report";
  const qaBaseUrl = String(args.baseUrl || "").trim();
  const wsEndpoint = "ws://127.0.0.1:" + Number(args.port || 9420);
  let miniProgram;
  try {
    const automator = loadAutomator();
    miniProgram = await connectWithRetry(automator, wsEndpoint);
    const qaBase = await forceQaBaseUrl(miniProgram, qaBaseUrl);
    const httpAuth = await loginViaHttpIfAvailable(args.authBaseUrl || qaBaseUrl);
    const seededAuth = await seedAuthStorage(miniProgram, httpAuth);
    const page = await miniProgram.reLaunch(targetPage);
    if (!page) {
      throw new Error("DevTools automator did not return a Page for " + targetPage);
    }
    await page.waitFor(Math.max(0, Number(args.waitMs || 800)));
    let snapshot = await currentPageSnapshot(miniProgram);
    const runtimeReportProbe = await readLearningReportViaRuntime(miniProgram, qaBaseUrl);
    let auth = {
      attempted: httpAuth.attempted,
      credential_source: httpAuth.credential_source,
      http_status: httpAuth.http_status,
      token_present: !!httpAuth.token_present,
      seeded_token_present: !!seededAuth.token_present,
      seeded_user_id_present: !!seededAuth.user_id_present,
    };
    if (normalizePagePath(snapshot.currentPage) === "/packageDeeptutor/pages/login/login") {
      auth = await loginWithPasswordIfAvailable(miniProgram, targetPage);
      snapshot = await currentPageSnapshot(miniProgram);
    }
    const currentPage = snapshot.currentPage;
    const pageData = snapshot.pageData;
    const reachedTarget = normalizePagePath(currentPage) === targetPage;
    const p0aProbe = {
      has_note_assets_key: Object.prototype.hasOwnProperty.call(pageData || {}, "noteAssets"),
      has_today_tasks_key: Object.prototype.hasOwnProperty.call(pageData || {}, "todayTasks"),
      note_assets_count: Array.isArray((pageData || {}).noteAssets) ? pageData.noteAssets.length : -1,
      today_tasks_count: Array.isArray((pageData || {}).todayTasks) ? pageData.todayTasks.length : -1,
      has_save_attempt_method: Boolean(snapshot.current && typeof snapshot.current.callMethod === "function"),
    };
    const gradingToBrainLoop =
      pageData && pageData.gradingToBrainLoop && typeof pageData.gradingToBrainLoop === "object"
        ? pageData.gradingToBrainLoop
        : {};
    const flatGradingLoop = {
      status: String((pageData || {}).gradingLoopStatus || ""),
      nextRequiredAction: String((pageData || {}).gradingLoopNextRequiredAction || ""),
      evidenceRefs: Array.isArray((pageData || {}).gradingLoopEvidenceRefs)
        ? (pageData || {}).gradingLoopEvidenceRefs
        : [],
      stages: Array.isArray((pageData || {}).gradingLoopStages) ? (pageData || {}).gradingLoopStages : [],
      currentAction:
        (pageData || {}).gradingLoopCurrentAction && typeof (pageData || {}).gradingLoopCurrentAction === "object"
          ? (pageData || {}).gradingLoopCurrentAction
          : {},
      latestOutcome:
        (pageData || {}).gradingLoopLatestOutcome && typeof (pageData || {}).gradingLoopLatestOutcome === "object"
          ? (pageData || {}).gradingLoopLatestOutcome
          : {},
      authority:
        (pageData || {}).gradingLoopAuthority && typeof (pageData || {}).gradingLoopAuthority === "object"
          ? (pageData || {}).gradingLoopAuthority
          : {},
      sourceStatus:
        (pageData || {}).gradingLoopSourceStatus && typeof (pageData || {}).gradingLoopSourceStatus === "object"
          ? (pageData || {}).gradingLoopSourceStatus
          : {},
    };
    const loopEvidenceRefs = Array.isArray(gradingToBrainLoop.evidenceRefs)
      ? gradingToBrainLoop.evidenceRefs
      : flatGradingLoop.evidenceRefs;
    const loopStages = Array.isArray(gradingToBrainLoop.stages)
      ? gradingToBrainLoop.stages
      : flatGradingLoop.stages;
    const loopCurrentAction =
      gradingToBrainLoop.currentAction && typeof gradingToBrainLoop.currentAction === "object"
        ? gradingToBrainLoop.currentAction
        : flatGradingLoop.currentAction;
    const loopLatestOutcome =
      gradingToBrainLoop.latestOutcome && typeof gradingToBrainLoop.latestOutcome === "object"
        ? gradingToBrainLoop.latestOutcome
        : flatGradingLoop.latestOutcome;
    const gradingToBrainProbe = {
      has_grading_to_brain_loop:
        Object.prototype.hasOwnProperty.call(pageData || {}, "gradingToBrainLoop") ||
        Object.prototype.hasOwnProperty.call(pageData || {}, "gradingLoopStatus"),
      status: String(gradingToBrainLoop.status || flatGradingLoop.status || ""),
      next_required_action: String(gradingToBrainLoop.nextRequiredAction || flatGradingLoop.nextRequiredAction || ""),
      evidence_ref_count: loopEvidenceRefs.length,
      stage_count: loopStages.length,
      current_action_title:
        loopCurrentAction && typeof loopCurrentAction === "object" ? String(loopCurrentAction.title || "") : "",
      latest_outcome_status:
        loopLatestOutcome && typeof loopLatestOutcome === "object" ? String(loopLatestOutcome.status || "") : "",
      authority:
        gradingToBrainLoop.authority && typeof gradingToBrainLoop.authority === "object"
          ? gradingToBrainLoop.authority
          : flatGradingLoop.authority,
      source_status:
        gradingToBrainLoop.sourceStatus && typeof gradingToBrainLoop.sourceStatus === "object"
          ? gradingToBrainLoop.sourceStatus
          : flatGradingLoop.sourceStatus,
    };
    emit(
      {
        ok: reachedTarget,
        ws_endpoint: wsEndpoint,
        devtools_project_root: "yousenwebview",
        target_subpackage: "packageDeeptutor",
        target_page: targetPage,
        entry_flow: "direct_subpackage_page",
        qa_base_url: qaBaseUrl,
        auth_base_url: String(args.authBaseUrl || qaBaseUrl || "").trim(),
        wait_ms: Math.max(0, Number(args.waitMs || 800)),
        qa_base_applied: qaBase,
        auth_attempted: auth.attempted,
        auth_state: auth.seeded_token_present || auth.reached_target ? "qa_token" : auth.attempted ? "auth_blocked" : "unknown",
        auth_mode: auth.seeded_token_present ? "manual_token" : auth.attempted ? "local_dev_wechat" : "none",
        credential_source: auth.credential_source,
        auth_http_status: auth.http_status,
        auth_token_present: !!auth.token_present,
        seeded_token_present: !!auth.seeded_token_present,
        seeded_user_id_present: !!auth.seeded_user_id_present,
        login_error_present: !!auth.login_error_present,
        login_error_message: auth.login_error_message,
        current_page: currentPage,
        p0a_probe: p0aProbe,
        grading_to_brain_probe: gradingToBrainProbe,
        runtime_report_probe: runtimeReportProbe,
        page_data_keys: Object.keys(pageData || {}).sort().slice(0, 80),
      },
      reachedTarget ? 0 : 1,
    );
  } catch (error) {
    emit(
      {
        ok: false,
        ws_endpoint: wsEndpoint,
        devtools_project_root: "yousenwebview",
        target_subpackage: "packageDeeptutor",
        target_page: targetPage,
        entry_flow: "direct_subpackage_page",
        qa_base_url: String(args.baseUrl || "").trim(),
        auth_base_url: String(args.authBaseUrl || args.baseUrl || "").trim(),
        wait_ms: Math.max(0, Number(args.waitMs || 800)),
        error: String(error && error.message ? error.message : error),
        details: error && error.details ? error.details : undefined,
      },
      1,
    );
  } finally {
    if (miniProgram && typeof miniProgram.disconnect === "function") {
      miniProgram.disconnect();
    }
  }
})();

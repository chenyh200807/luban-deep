#!/usr/bin/env node
"use strict";

function parseArgs(argv) {
  const out = { port: 9420, targetPage: "/packageDeeptutor/pages/report/report" };
  for (let i = 2; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--port") {
      out.port = Number(argv[++i]);
    } else if (arg === "--target-page") {
      out.targetPage = String(argv[++i] || "");
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
  process.stdout.write(JSON.stringify(payload, null, 2) + "\n");
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
  const wsEndpoint = "ws://127.0.0.1:" + Number(args.port || 9420);
  let miniProgram;
  try {
    const automator = loadAutomator();
    miniProgram = await connectWithRetry(automator, wsEndpoint);
    const page = await miniProgram.reLaunch(targetPage);
    if (!page) {
      throw new Error("DevTools automator did not return a Page for " + targetPage);
    }
    await page.waitFor(800);
    let snapshot = await currentPageSnapshot(miniProgram);
    let auth = { attempted: false, credential_source: "none" };
    if (normalizePagePath(snapshot.currentPage) === "/packageDeeptutor/pages/login/login") {
      auth = await loginWithPasswordIfAvailable(miniProgram, targetPage);
      snapshot = await currentPageSnapshot(miniProgram);
    }
    const currentPage = snapshot.currentPage;
    const pageData = snapshot.pageData;
    const reachedTarget = normalizePagePath(currentPage) === targetPage;
    emit(
      {
        ok: reachedTarget,
        ws_endpoint: wsEndpoint,
        devtools_project_root: "yousenwebview",
        target_subpackage: "packageDeeptutor",
        target_page: targetPage,
        entry_flow: "direct_subpackage_page",
        auth_attempted: auth.attempted,
        credential_source: auth.credential_source,
        login_error_present: !!auth.login_error_present,
        login_error_message: auth.login_error_message,
        current_page: currentPage,
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

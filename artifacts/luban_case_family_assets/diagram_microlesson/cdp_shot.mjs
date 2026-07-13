// 一次性 CDP 手机截图器(零依赖, Node24 原生 fetch+WebSocket)。
// 用法: node cdp_shot.mjs <input.html> <out.png> [width|widthxheight] [evalJS]
// 启 headless Chrome → 设移动视口 → 导航 → (可选注入 JS) → full-page 截图 → 杀 Chrome。
import { spawn } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const [, , input, out, widthArg, evalJS] = process.argv;
if (!input || !out) { console.error("usage: node cdp_shot.mjs <input.html> <out.png> [width] [evalJS]"); process.exit(2); }
const [widthText, heightText] = String(widthArg || "390").split("x");
const width = Number(widthText) || 390;
const viewportHeight = Number(heightText) || 844;
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const userDir = mkdtempSync(join(tmpdir(), "cdp-shot-"));
const PORT = 9300 + Math.floor(Math.random() * 600);

const chrome = spawn(CHROME, [
  "--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${userDir}`,
  "--no-first-run", "--no-default-browser-check", "--disable-extensions", "--hide-scrollbars",
  "--force-device-scale-factor=2",
], { stdio: "ignore" });

const cleanup = () => { try { chrome.kill("SIGKILL"); } catch {} try { rmSync(userDir, { recursive: true, force: true }); } catch {} };
process.on("exit", cleanup);

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function wsEndpoint() {
  // 必须连 page 目标(非 browser 目标), 否则 Page.* 域命令不可用
  for (let i = 0; i < 50; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/json`);
      const list = await r.json();
      const page = list.find((t) => t.type === "page" && t.webSocketDebuggerUrl);
      if (page) return page.webSocketDebuggerUrl;
    } catch {}
    await sleep(100);
  }
  throw new Error("chrome page target not ready");
}

function cdp(ws) {
  let id = 0; const pending = new Map(); const events = [];
  ws.addEventListener("message", (e) => {
    const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
    else if (m.method) events.push(m);
  });
  const send = (method, params = {}) => new Promise((res, rej) => {
    const i = ++id;
    pending.set(i, (m) => { if (m.error) rej(new Error(`${method}: ${JSON.stringify(m.error)}`)); else res(m); });
    ws.send(JSON.stringify({ id: i, method, params }));
  });
  return { send };
}

(async () => {
  const wsUrl = await wsEndpoint();
  const ws = new WebSocket(wsUrl);
  await new Promise((r) => ws.addEventListener("open", r, { once: true }));
  const { send } = cdp(ws);
  await send("Page.enable");
  await send("Runtime.enable");
  await send("Emulation.setDeviceMetricsOverride", { width, height: viewportHeight, deviceScaleFactor: 2, mobile: true });
  const url = "file://" + resolve(input);
  await send("Page.navigate", { url });
  // 轮询 readyState(比 loadEventFired 稳, 见 zero-dep-cdp 记忆)
  for (let i = 0; i < 60; i++) {
    const r = await send("Runtime.evaluate", { expression: "document.readyState", returnByValue: true });
    if (r.result?.result?.value === "complete") break;
    await sleep(100);
  }
  await sleep(350); // 让内联 JS 初始化
  // DC handoff pages expose seek through a range input rather than a window API.
  // Keep the documented `seek(seconds)` screenshot shorthand deterministic.
  const seekHelper = await send("Runtime.evaluate", {
    expression: `globalThis.seek=(seconds)=>{const input=document.querySelector('input[type="range"]');if(!input)throw new Error('seek helper: range input not found');input.value=String(seconds);input.dispatchEvent(new Event('input',{bubbles:true}));}`,
    returnByValue: true,
  });
  if (seekHelper.result?.exceptionDetails) throw new Error(`seek helper failed: ${seekHelper.result.exceptionDetails.text || "runtime exception"}`);
  if (evalJS) {
    const evaluated = await send("Runtime.evaluate", { expression: evalJS, returnByValue: true });
    if (evaluated.result?.exceptionDetails) throw new Error(`evalJS failed: ${evaluated.result.exceptionDetails.text || "runtime exception"}`);
    await sleep(250);
  }
  const metrics = await send("Page.getLayoutMetrics");
  const res = metrics.result || {};
  const cs = res.cssContentSize || res.contentSize;
  // 退而求其次: 用 scrollHeight 量内容高度
  let height;
  if (cs && cs.height) {
    height = Math.ceil(cs.height);
  } else {
    const sh = await send("Runtime.evaluate", { expression: "document.body.scrollHeight", returnByValue: true });
    height = Math.ceil(sh.result?.result?.value || 2400);
  }
  const shot = await send("Page.captureScreenshot", {
    format: "png", captureBeyondViewport: true,
    clip: { x: 0, y: 0, width, height, scale: 1 },
  });
  writeFileSync(out, Buffer.from(shot.result.data, "base64"));
  ws.close();
  console.log(`shot: ${out}  (${width}px × ${Math.ceil(cs.height)}px css)`);
  cleanup();
  process.exit(0);
})().catch((e) => { console.error(e); cleanup(); process.exit(1); });

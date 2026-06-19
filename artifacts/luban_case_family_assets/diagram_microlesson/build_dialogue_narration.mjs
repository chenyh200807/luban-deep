// 双人对话(NotebookLM 式)离线配音 — do-once 存档复用。
// 与单人 build_card_narration.mjs 的区别:逐 turn 切换音色(A/B 两个 say voice),
// timing 段带 speaker + anchor,运行时 render_dialogue.py 按段高亮对话气泡。
//
// 防漂移闸:每个 claim=true 的 turn 必须带 anchor,且 anchor 能在 derived_from 卡里解析到真实字段。
//   解析不到 → 报错退出(不让"听感有趣"掩盖"事实漂移")。
// --print: 只跑防漂移闸 + 打印对话稿,不配音(先确认稿子/grounding)。
// 安全:全程 execFileSync 数组传参,不经 shell。
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { basename, dirname, join } from "node:path";

const input = process.argv[2];
const PRINT = process.argv.includes("--print");
if (!input) {
  console.error("usage: node build_dialogue_narration.mjs <card.dialogue.json> [--print]");
  process.exit(2);
}
const dlg = JSON.parse(readFileSync(input, "utf-8"));
const dir = dirname(input);

// ---- 防漂移闸:claim=true 的 turn 的 anchor 必须在源卡里解析到真实字段 ----
const stripHtml = (s) => String(s || "").replace(/<[^>]+>/g, "").trim();
function resolveAnchor(card, path) {
  // 支持 a.b.c / arr[0].x / arr[id_string].x(数组里按 id 字段匹配)
  let cur = card;
  for (const raw of path.split(".")) {
    const m = raw.match(/^([^[]+)(?:\[([^\]]+)\])?$/);
    if (!m) return undefined;
    const [, key, idx] = m;
    cur = cur?.[key];
    if (idx !== undefined) {
      if (cur === undefined) return undefined;
      if (/^\d+$/.test(idx)) cur = cur[Number(idx)];
      else cur = Array.isArray(cur) ? cur.find((e) => e && e.id === idx) : undefined;
    }
    if (cur === undefined || cur === null) return undefined;
  }
  return cur;
}
function checkFaithfulness(dlg) {
  const cardPath = join(dir, dlg.derived_from || "");
  if (!dlg.derived_from || !existsSync(cardPath)) {
    console.error(`✗ derived_from 卡不存在: ${dlg.derived_from}`);
    process.exit(1);
  }
  const card = JSON.parse(readFileSync(cardPath, "utf-8"));
  const problems = [];
  dlg.turns.forEach((t, i) => {
    if (!t.claim) return;
    if (!t.anchor) return problems.push(`turn#${i}(${t.speaker}) claim=true 但缺 anchor`);
    const v = resolveAnchor(card, t.anchor);
    if (v === undefined) problems.push(`turn#${i} anchor 解析不到: ${t.anchor}`);
  });
  if (problems.length) {
    console.error("✗ 防漂移闸失败:\n  " + problems.join("\n  "));
    process.exit(1);
  }
  const claims = dlg.turns.filter((t) => t.claim).length;
  console.log(`✓ 防漂移闸通过:${claims} 条事实 turn 全部 anchor 到 ${basename(cardPath)} 真实字段`);
}
checkFaithfulness(dlg);

// 朗读规范化(只改朗读形态,字幕仍显原文)
const speechNorm = (t) =>
  String(t || "")
    .replace(/\//g, "、")
    .replace(/[（(]/g, ",")
    .replace(/[）)]/g, ",")
    .replace(/[，,]{2,}/g, ",");

if (PRINT) {
  dlg.turns.forEach((t, i) => {
    const sp = dlg.speakers[t.speaker];
    console.log(`${String(i).padStart(2)} ${sp.name}(${sp.voice})${t.claim ? " ◆" + (t.anchor || "") : ""}\n   ${t.text}\n`);
  });
  process.exit(0);
}

// ---- 配音 ----
const GAP = 0.35;
const TAIL = 0.8;
const stem = basename(input).replace(/\.json$/, "");
const mp3Out = join(dir, `${stem}.mp3`);
const timingOut = join(dir, `${stem}.timing.json`);
const tmp = join(dir, ".dialogue_tmp");
mkdirSync(tmp, { recursive: true });

const probeDuration = (f) =>
  parseFloat(execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f]).toString().trim());

const durs = [];
dlg.turns.forEach((t, i) => {
  const voice = dlg.speakers[t.speaker].voice;
  const aiff = `${tmp}/${i}.aiff`;
  const wav = `${tmp}/${i}.wav`;
  execFileSync("say", ["-v", voice, "-o", aiff, speechNorm(t.text)]);
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-i", aiff, "-ar", "44100", "-ac", "1", wav]);
  durs.push(probeDuration(wav));
  console.log(`  ${String(i).padStart(2)} ${dlg.speakers[t.speaker].name}: ${durs[i].toFixed(2)}s`);
});

const gapWav = `${tmp}/gap.wav`;
execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", String(GAP), gapWav]);

const lines = [];
dlg.turns.forEach((_, i) => {
  lines.push(`file '${i}.wav'`);
  if (i < dlg.turns.length - 1) lines.push(`file 'gap.wav'`);
});
const listPath = `${tmp}/filelist.txt`;
writeFileSync(listPath, lines.join("\n"));
execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", listPath, "-c:a", "libmp3lame", "-q:a", "3", mp3Out]);

let t = 0;
const segments = dlg.turns.map((turn, i) => {
  const startSec = Number(t.toFixed(3));
  t += durs[i];
  const out = { idx: i, speaker: turn.speaker, anchor: turn.anchor || null, claim: !!turn.claim, text: turn.text, startSec, durSec: Number(durs[i].toFixed(3)) };
  if (i < dlg.turns.length - 1) t += GAP;
  return out;
});
const totalSec = Number((t + TAIL).toFixed(3));

writeFileSync(timingOut, JSON.stringify({ audio: basename(mp3Out), totalSec, style: "notebooklm_two_voice", segments }, null, 2));
rmSync(tmp, { recursive: true, force: true });
console.log(`✅ ${basename(mp3Out)} + ${basename(timingOut)}  (${totalSec.toFixed(1)}s, ${segments.length} turn, 双人)`);

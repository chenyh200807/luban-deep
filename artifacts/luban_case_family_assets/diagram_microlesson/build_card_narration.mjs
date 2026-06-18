// 交互卡旁白离线预生成(do-once 存档复用)。
// 旁白按 narration-spec.md 总纲从卡 schema 的内容字段【派生】(不手写、卡是唯一源):
//   deriveNarration(schema) → 逐句 say 配音 → ffprobe 量真实时长
//   → 拼成 <stem>.narration.mp3 + 写 <stem>.narration.timing.json(各段 anchor + 起止秒)。
// 运行时:WebView 加载卡 HTML + <audio> 拉这条 mp3 播放,按 timing 同步高亮/reveal。
// --print: 只打印派生旁白稿(不配音),供先确认稿子。
// 安全:全程 execFileSync 数组传参,不经 shell。
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { basename } from "node:path";

const input = process.argv[2];
const PRINT = process.argv.includes("--print");
if (!input) {
  console.error("usage: node build_card_narration.mjs <card.schema.json> [--print]");
  process.exit(2);
}
const schema = JSON.parse(readFileSync(input, "utf-8"));

// ---- 旁白派生(总纲 narration-spec.md)----
const stripHtml = (s) => String(s || "").replace(/<[^>]+>/g, "").trim();
const trimTail = (s) => String(s || "").replace(/[。.，,;；\s]+$/u, "");

function deriveNarration(s) {
  const segs = [];
  // 开场: scenario.caption 优先(最口语), 退而求其次 why / goal
  const opener = trimTail(s.scenario?.caption || stripHtml(s.why_lose_points_html) || s.student_goal || "");
  if (opener) segs.push({ id: "opening", anchor: "why", text: `${opener}。我们一个一个看。` });

  // 主体: ⑤对照(逐项); 其它原型按总纲在此扩展 steps/diagnosis
  // 精简取向: 只读「点错(loss_display)+ 采分表达(scoring_expression)」;
  // 完整错法/正确做法在卡上视觉呈现(听觉精简、视觉完整、互补)。
  (s.contrast_items || []).forEach((it, i) => {
    const lead = i === 0 ? "先看" : "再看";
    const loss = trimTail(it.wrong?.loss_display || "");
    const se = trimTail(it.right?.scoring_expression || it.right?.text || "");
    let t = `${lead}${it.axis}。`;
    if (loss) t += `常见丢分是${loss};`;
    t += `记住要写:${se}。`;
    segs.push({ id: `axis_${it.id}`, anchor: `item:${it.id}`, text: t });
  });

  // ④判断: decision.judgment_points 逐条 + 结论(anchor 对齐渲染器 data-anchor)
  const dec = s.decision;
  if (dec && Array.isArray(dec.judgment_points)) {
    dec.judgment_points.forEach((p, i) => {
      const lead = i === 0 ? "先判" : "再判";
      const crit = trimTail(p.criterion || "");
      const reason = trimTail(p.verdict_reason || "");
      let t = `${lead}:${trimTail(p.question || "")}。判据是${crit}。${reason}。`;
      segs.push({ id: `jp_${p.id}`, anchor: `point:${p.id}`, text: t });
    });
    const outcomes = (dec.outcomes || []).reduce((m, o) => ((m[o.id] = o), m), {});
    const reached = outcomes[dec.reached_outcome];
    if (reached) segs.push({ id: "conclusion", anchor: "outcome", text: `所以结论:${trimTail(reached.label)}。` });
  }

  // 采分关键: scoring_points keywords 去重
  const kws = [...new Set((s.scoring_points || []).flatMap((sp) => sp.keywords || []))];
  if (kws.length) segs.push({ id: "scoring", anchor: "scoring", text: `这道题的采分关键就这几组词:${kws.join("、")}。写到了就稳。` });

  // 暖收尾(精简): 固定暖收束 + memory_hook(完整 warm_correction 在卡上视觉呈现)
  const hook = trimTail(s.memory_hook || "");
  if (hook || (s.scoring_points || []).length) {
    let t = "把这两组采分词记牢,这类题就稳了。";
    if (hook) t += `记住:${hook}。`;
    segs.push({ id: "closing", anchor: "wrap", text: t });
  }
  return segs;
}

// 朗读规范化: 只改朗读形态, 不改内容(字幕仍显示卡原文)。
const speechNorm = (t) =>
  String(t || "")
    .replace(/(\d)\s*\/\s*(\d)/g, (_, a, b) => (a === "1" && b === "3" ? "三分之一" : `${a}分之${b}`))
    .replace(/\//g, "、")
    .replace(/[（(]/g, ",")
    .replace(/[）)]/g, ",")
    .replace(/\+/g, "、")
    .replace(/[，,]{2,}/g, ",")
    .replace(/、{2,}/g, "、")
    .replace(/,\s*([。,，、])/g, "$1");

const VOICE = schema.narration?.voice_hint || "Tingting";
const derived = deriveNarration(schema);
if (!derived.length) {
  console.error("派生旁白为空: schema 缺 scenario/contrast_items 等内容字段");
  process.exit(1);
}

if (PRINT) {
  console.log(JSON.stringify({ voice: VOICE, segments: derived }, null, 2));
  process.exit(0);
}

// ---- 配音 ----
const GAP = 0.5;
const TAIL = 0.8;
const stem = basename(input).replace(/\.json$/, "");
const dir = input.replace(/[^/]+$/, "") || "./";
const tmp = `${dir}.narration_tmp`;
const mp3Out = `${dir}${stem}.narration.mp3`;
const timingOut = `${dir}${stem}.narration.timing.json`;

mkdirSync(tmp, { recursive: true });
const probeDuration = (f) =>
  parseFloat(
    execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f]).toString().trim(),
  );

const durs = [];
derived.forEach((seg, i) => {
  const aiff = `${tmp}/${i}.aiff`;
  const wav = `${tmp}/${i}.wav`;
  execFileSync("say", ["-v", VOICE, "-o", aiff, speechNorm(seg.text)]);
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-i", aiff, "-ar", "44100", "-ac", "1", wav]);
  durs.push(probeDuration(wav));
  console.log(`  ${seg.id}: ${durs[i].toFixed(2)}s`);
});

const gapWav = `${tmp}/gap.wav`;
execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", String(GAP), gapWav]);

const lines = [];
derived.forEach((_, i) => {
  lines.push(`file '${i}.wav'`);
  if (i < derived.length - 1) lines.push(`file 'gap.wav'`);
});
const listPath = `${tmp}/filelist.txt`;
writeFileSync(listPath, lines.join("\n"));
execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", listPath, "-c:a", "libmp3lame", "-q:a", "3", mp3Out]);

let t = 0;
const segments = derived.map((seg, i) => {
  const startSec = Number(t.toFixed(3));
  t += durs[i];
  const out = { id: seg.id, anchor: seg.anchor, text: seg.text, startSec, durSec: Number(durs[i].toFixed(3)) };
  if (i < derived.length - 1) t += GAP;
  return out;
});
const totalSec = Number((t + TAIL).toFixed(3));

writeFileSync(timingOut, JSON.stringify({ audio: basename(mp3Out), totalSec, derived_from: "fields", segments }, null, 2));
rmSync(tmp, { recursive: true, force: true });
console.log(`✅ ${basename(mp3Out)} + ${basename(timingOut)}  (${totalSec.toFixed(1)}s, ${segments.length} 段, 派生自卡字段)`);

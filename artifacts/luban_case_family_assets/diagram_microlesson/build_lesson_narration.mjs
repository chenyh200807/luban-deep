// 教学动画(先讲后问)离线配音 — do-once 存档复用。
// 输入 <card>.lesson.json:teach(老师主讲,每 scene 一段动画 state + 旁白) + qa(讲完后学生问/老师答)。
// 拍平成有序音频段(带 speaker/state/kind),逐段按 speaker 切音色配音,拼一条 mp3 + timing。
//   timing 段:teach 段带 state(驱动 SVG 舞台切换),qa 段带 kind=q/a。
// 防漂移闸:claim=true 的 teach/qa/closing 段 anchor 必须在 derived_from 卡里解析到真实字段,否则报错退出。
// --print: 只跑闸 + 打印拍平后的讲稿,不配音。
// 安全:全程 execFileSync 数组传参,不经 shell。
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { formatWorkflowResults, validateLessonWorkflow } from "./lesson_workflow_checks.mjs";

const input = process.argv[2];
const PRINT = process.argv.includes("--print");
if (!input) {
  console.error("usage: node build_lesson_narration.mjs <card.lesson.json> [--print]");
  process.exit(2);
}
const lesson = JSON.parse(readFileSync(input, "utf-8"));
const dir = dirname(input);

// ---- 拍平成有序音频段 ----
function flatten(lesson) {
  const segs = [];
  // teach: 优先 beats(PPT 式逐点),兼容旧 scenes;stage 不写则继承上一 beat(画面不回退)
  const beats = lesson.teach?.beats || lesson.teach?.scenes || [];
  let lastState = "intro";
  beats.forEach((b) => {
    if (b.state || b.stage) lastState = b.state || b.stage;
    segs.push({ kind: "teach", state: lastState, speaker: "T", anchor: b.anchor || null, claim: !!b.claim, keycard: b.keycard || null, text: b.narration });
  });
  (lesson.qa || []).forEach((pair, i) => {
    segs.push({ kind: "q", qaIndex: i, state: "conclude", speaker: pair.q.speaker || "S", anchor: pair.q.anchor || null, claim: !!pair.q.claim, keycard: null, text: pair.q.text });
    segs.push({ kind: "a", qaIndex: i, state: "conclude", speaker: pair.a.speaker || "T", anchor: pair.a.anchor || null, claim: !!pair.a.claim, keycard: null, text: pair.a.text });
  });
  if (lesson.closing) {
    segs.push({
      kind: "closing",
      qaIndex: null,
      state: lesson.closing.state || "closing",
      speaker: lesson.closing.speaker || "T",
      anchor: lesson.closing.anchor || null,
      claim: !!lesson.closing.claim,
      keycard: lesson.closing.keycard || null,
      text: lesson.closing.text || lesson.closing.narration,
    });
  }
  return segs;
}

// ---- 防漂移闸 ----
function resolveAnchor(card, path) {
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
function checkFaithfulness(lesson, segs) {
  const cardPath = join(dir, lesson.derived_from || "");
  if (!lesson.derived_from || !existsSync(cardPath)) {
    console.error(`✗ derived_from 卡不存在: ${lesson.derived_from}`);
    process.exit(1);
  }
  const card = JSON.parse(readFileSync(cardPath, "utf-8"));
  // 讲懂的迁移铺垫等事实,依据可能在母题(R2 不变量/R3 模板)而非讲懂卡;
  // 支持 anchor 前缀 "master:" 回 archetype_master_ref 验证(依据可追溯到母题)。
  let master = null;
  if (lesson.archetype_master_ref) {
    const mp = join(dir, lesson.archetype_master_ref);
    if (existsSync(mp)) master = JSON.parse(readFileSync(mp, "utf-8"));
  }
  const problems = [];
  segs.forEach((s, i) => {
    if (!s.claim) return;
    if (!s.anchor) return problems.push(`seg#${i}(${s.kind}) claim=true 但缺 anchor`);
    let src = card, path = s.anchor;
    if (s.anchor.startsWith("master:")) {
      if (!master) return problems.push(`seg#${i} anchor 用 master: 但 lesson 缺 archetype_master_ref 或文件不存在`);
      src = master;
      path = s.anchor.slice(7);
    }
    if (resolveAnchor(src, path) === undefined) problems.push(`seg#${i} anchor 解析不到: ${s.anchor}`);
  });
  if (problems.length) {
    console.error("✗ 防漂移闸失败:\n  " + problems.join("\n  "));
    process.exit(1);
  }
  console.log(`✓ 防漂移闸通过:${segs.filter((s) => s.claim).length} 条事实段全部 anchor 到依据(讲懂卡 / master 不变量)`);
}

function checkNarrationStructure(lesson, segs) {
  const problems = [];
  const beats = lesson.teach?.beats || lesson.teach?.scenes || [];
  beats.forEach((beat, i) => {
    if (beat.speaker && beat.speaker !== "T") {
      problems.push(`teach.beats[${i}] speaker=${beat.speaker}; 学生追问必须放顶层 qa[]`);
    }
    if (["q", "a"].includes(String(beat.kind || "").toLowerCase())) {
      problems.push(`teach.beats[${i}] kind=${beat.kind}; qa turn 必须放顶层 qa[]`);
    }
  });
  if (Array.isArray(lesson.qa) && lesson.qa.length > 0 && lesson.qa.length < 3) {
    problems.push(`qa[] 只有 ${lesson.qa.length} 组; 教学动画默认至少三问三答,否则干脆省略 qa[]`);
  }
  const teacherFillerCount = segs
    .filter((s) => s.speaker === "T")
    .reduce((count, s) => {
      const matches = String(s.text || "").match(/注意哈|别急哈|记住哈|这里[^，。；]*哈|哈[，。；]/g);
      return count + (matches ? matches.length : 0);
    }, 0);
  if (teacherFillerCount > 2) {
    problems.push(`老师口癖出现 ${teacherFillerCount} 次; 只保留 hook/closing 的自然语气`);
  }
  if (lesson.speakers?.S?.voice === "longlaotie_v3") {
    const colloquialCue = /(老师|这块|那我|能拿分不|行不|整明白|是不是|要不要|得不|咋)/;
    const denseDialectCue = /(老铁|嘎哈|贼|嗷|咋整|东北|整)/g;
    segs
      .filter((s) => s.kind === "q" || s.speaker === "S")
      .forEach((s, i) => {
        const text = String(s.text || "");
        if (!/[?？]/.test(text)) problems.push(`qa[${i}] 学生段必须是真问题`);
        if (!colloquialCue.test(text)) problems.push(`qa[${i}] 学生段太书面; 加一个自然口语钩子,但保留对象/依据/采分边界`);
        const dense = text.match(denseDialectCue) || [];
        if (dense.length > 2) problems.push(`qa[${i}] 东北口语过密(${dense.length}); 不要写成方言段子`);
      });
  }
  if (problems.length) {
    console.error("✗ 旁白结构闸失败:\n  " + problems.join("\n  "));
    process.exit(1);
  }
}

function checkLessonWorkflowContract(lessonDoc) {
  const result = validateLessonWorkflow({ lessonDoc, lessonPath: resolve(input) });
  if (!result.active) return;
  if (result.warnings.length) {
    console.warn(formatWorkflowResults({ ...result, problems: [] }));
  }
  if (result.problems.length) {
    console.error("✗ lesson workflow contract failed:\n" + formatWorkflowResults(result));
    process.exit(1);
  }
  console.log(`✓ lesson workflow ok:${basename(result.cardPath || "")} anchored to ${basename(result.packPath || "")}`);
}

const speechNorm = (t) =>
  String(t || "").replace(/\//g, "、").replace(/[（(]/g, ",").replace(/[）)]/g, ",").replace(/[，,]{2,}/g, ",");

const segs = flatten(lesson);
checkNarrationStructure(lesson, segs);
checkLessonWorkflowContract(lesson);
checkFaithfulness(lesson, segs);

if (PRINT) {
  segs.forEach((s, i) => {
    const sp = lesson.speakers[s.speaker];
    const tag = s.kind === "teach" ? `[${s.state}]` : `[${s.kind.toUpperCase()}]`;
    console.log(`${String(i).padStart(2)} ${tag} ${sp.name}(${sp.voice})${s.claim ? " ◆" + (s.anchor || "") : ""}\n   ${s.text}\n`);
  });
  process.exit(0);
}

// ---- 配音 ----
const GAP = 0.4;
const TAIL = 0.8;
const stem = basename(input).replace(/\.json$/, "");
const mp3Out = join(dir, `${stem}.mp3`);
const timingOut = join(dir, `${stem}.timing.json`);
const tmp = join(dir, ".lesson_tmp");
mkdirSync(tmp, { recursive: true });

const probeDuration = (f) =>
  parseFloat(execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f]).toString().trim());

const durs = [];
segs.forEach((s, i) => {
  const voice = lesson.speakers[s.speaker].voice;
  const aiff = `${tmp}/${i}.aiff`;
  const wav = `${tmp}/${i}.wav`;
  execFileSync("say", ["-v", voice, "-o", aiff, speechNorm(s.text)]);
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-i", aiff, "-ar", "44100", "-ac", "1", wav]);
  durs.push(probeDuration(wav));
  console.log(`  ${String(i).padStart(2)} ${s.kind === "teach" ? s.state : s.kind} ${lesson.speakers[s.speaker].name}: ${durs[i].toFixed(2)}s`);
});

const gapWav = `${tmp}/gap.wav`;
execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", String(GAP), gapWav]);

const lines = [];
segs.forEach((_, i) => {
  lines.push(`file '${i}.wav'`);
  if (i < segs.length - 1) lines.push(`file 'gap.wav'`);
});
const listPath = `${tmp}/filelist.txt`;
writeFileSync(listPath, lines.join("\n"));
execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", listPath, "-c:a", "libmp3lame", "-q:a", "3", mp3Out]);

let t = 0;
const segments = segs.map((s, i) => {
  const startSec = Number(t.toFixed(3));
  t += durs[i];
  const out = { idx: i, kind: s.kind, state: s.state, qaIndex: s.qaIndex ?? null, keycard: s.keycard ?? null, speaker: s.speaker, anchor: s.anchor, claim: s.claim, text: s.text, startSec, durSec: Number(durs[i].toFixed(3)) };
  if (i < segs.length - 1) t += GAP;
  return out;
});
const totalSec = Number((t + TAIL).toFixed(3));
const teachEndSec = (() => {
  const lastTeach = segments.filter((s) => s.kind === "teach").at(-1);
  return lastTeach ? Number((lastTeach.startSec + lastTeach.durSec).toFixed(3)) : 0;
})();

writeFileSync(timingOut, JSON.stringify({ audio: basename(mp3Out), totalSec, teachEndSec, style: "teach_then_qa", segments }, null, 2));
rmSync(tmp, { recursive: true, force: true });
console.log(`✅ ${basename(mp3Out)} + ${basename(timingOut)}  (${totalSec.toFixed(1)}s, teach 到 ${teachEndSec.toFixed(1)}s, ${segments.length} 段)`);

// Build one lesson narration with Aliyun DashScope CosyVoice.
// Reads <card>.lesson.json, validates fact anchors, synthesizes each beat, then
// concatenates a single lesson mp3 plus timing JSON used by the HTML renderer.
// Secret safety: API keys are loaded from env/.env but are never printed.
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { formatWorkflowResults, validateLessonWorkflow } from "./lesson_workflow_checks.mjs";

const ENDPOINT = "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer";
const QWEN_TTS_ENDPOINT = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation";
const MODEL = process.env.ALIYUN_TTS_MODEL || "cosyvoice-v3-flash";
const QWEN_TTS_MODEL = process.env.ALIYUN_QWEN_TTS_MODEL || "qwen3-tts-flash";
const VOICE = process.env.ALIYUN_TTS_VOICE || "longanhuan_v3";
const FORMAT = process.env.ALIYUN_TTS_FORMAT || "mp3";
const SAMPLE_RATE = Number(process.env.ALIYUN_TTS_SAMPLE_RATE || 24000);
const RATE = Number(process.env.ALIYUN_TTS_RATE || 0.95);
const VOLUME = Number(process.env.ALIYUN_TTS_VOLUME || 65);
const GAP = Number(process.env.LESSON_NARRATION_GAP || 0.4);
const TAIL = Number(process.env.LESSON_NARRATION_TAIL || 0.8);

const input = process.argv[2];
const PRINT = process.argv.includes("--print");
if (!input) {
  console.error("usage: node build_aliyun_lesson_narration.mjs <card.lesson.json> [--print]");
  process.exit(2);
}

const lessonPath = resolve(input);
const lesson = JSON.parse(readFileSync(lessonPath, "utf-8"));
const dir = dirname(lessonPath);

function loadDotEnv(paths) {
  for (const p of paths) {
    if (!existsSync(p)) continue;
    const text = readFileSync(p, "utf-8");
    for (const line of text.split(/\r?\n/)) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) continue;
      const eq = trimmed.indexOf("=");
      const key = trimmed.slice(0, eq).trim();
      let value = trimmed.slice(eq + 1).trim();
      if (
        (value.startsWith('"') && value.endsWith('"')) ||
        (value.startsWith("'") && value.endsWith("'"))
      ) {
        value = value.slice(1, -1);
      }
      if (key && process.env[key] === undefined) process.env[key] = value;
    }
  }
}

loadDotEnv([
  resolve(process.cwd(), ".env"),
  resolve(dir, "../../../.env"),
  resolve(dir, "../../../../.env"),
]);

function apiKey() {
  if (process.env.DASHSCOPE_API_KEY) return { name: "DASHSCOPE_API_KEY", value: process.env.DASHSCOPE_API_KEY };
  if (process.env.ALIYUN_DASHSCOPE_API_KEY) {
    return { name: "ALIYUN_DASHSCOPE_API_KEY", value: process.env.ALIYUN_DASHSCOPE_API_KEY };
  }
  throw new Error("missing DASHSCOPE_API_KEY or ALIYUN_DASHSCOPE_API_KEY");
}

function flatten(lessonDoc) {
  const segs = [];
  const beats = lessonDoc.teach?.beats || lessonDoc.teach?.scenes || [];
  let lastState = "intro";
  beats.forEach((b) => {
    if (b.state || b.stage) lastState = b.state || b.stage;
    segs.push({
      kind: b.kind || "teach",
      state: lastState,
      speaker: b.speaker || "T",
      anchor: b.anchor || null,
      claim: !!b.claim,
      keycard: b.keycard || null,
      text: b.narration,
    });
  });
  (lessonDoc.qa || []).forEach((pair, i) => {
    const state = pair.state || pair.stage || pair.q?.state || pair.a?.state || "conclude";
    segs.push({
      kind: "q",
      qaIndex: i,
      state,
      speaker: pair.q.speaker || "S",
      anchor: pair.q.anchor || null,
      claim: !!pair.q.claim,
      keycard: null,
      text: pair.q.text,
    });
    segs.push({
      kind: "a",
      qaIndex: i,
      state,
      speaker: pair.a.speaker || "T",
      anchor: pair.a.anchor || null,
      claim: !!pair.a.claim,
      keycard: null,
      text: pair.a.text,
    });
  });
  if (lessonDoc.closing?.text) {
    segs.push({
      kind: "a",
      qaIndex: null,
      state: lessonDoc.closing.state || lessonDoc.closing.stage || "closing",
      speaker: lessonDoc.closing.speaker || "T",
      anchor: lessonDoc.closing.anchor || null,
      claim: !!lessonDoc.closing.claim,
      keycard: null,
      text: lessonDoc.closing.text,
    });
  }
  return segs;
}

function checkNarrationStructure(lessonDoc, segs) {
  const problems = [];
  const beats = lessonDoc.teach?.beats || lessonDoc.teach?.scenes || [];
  beats.forEach((beat, i) => {
    if (beat.speaker && beat.speaker !== "T") {
      problems.push(`teach.beats[${i}] speaker=${beat.speaker}; student questions belong in top-level qa[]`);
    }
    if (["q", "a"].includes(String(beat.kind || "").toLowerCase())) {
      problems.push(`teach.beats[${i}] kind=${beat.kind}; qa turns belong in top-level qa[]`);
    }
  });
  if (Array.isArray(lessonDoc.qa) && lessonDoc.qa.length > 0 && lessonDoc.qa.length < 3) {
    problems.push(`qa[] has ${lessonDoc.qa.length} pair(s); teaching animations should use at least 3 real boundary questions or omit qa[]`);
  }
  const teacherTexts = segs.filter((s) => s.speaker === "T").map((s) => s.text || "");
  const fillerCount = teacherTexts.reduce((count, text) => {
    const matches = String(text).match(/注意哈|别急哈|记住哈|这里[^，。；]*哈|哈[，。；]/g);
    return count + (matches ? matches.length : 0);
  }, 0);
  if (fillerCount > 2) {
    problems.push(`teacher filler appears ${fillerCount} times; keep dialect/filler to hook and closing, not every beat`);
  }
  const studentVoice = lessonDoc.speakers?.S?.voice || "";
  const studentQuestions = segs.filter((s) => s.kind === "q" || s.speaker === "S");
  if (studentVoice === "longlaotie_v3") {
    const colloquialCue = /(老师|这块|那我|能拿分不|行不|整明白|是不是|要不要|得不|咋)/;
    const denseDialectCue = /(老铁|嘎哈|贼|嗷|咋整|东北|整)/g;
    studentQuestions.forEach((s, i) => {
      const text = String(s.text || "");
      if (!/[?？]/.test(text)) {
        problems.push(`qa[${i}] student line should be a real question for longlaotie_v3 voice`);
      }
      if (!colloquialCue.test(text)) {
        problems.push(`qa[${i}] student line is too written; add one natural spoken cue without losing the exam object/basis`);
      }
      const dense = text.match(denseDialectCue) || [];
      if (dense.length > 2) {
        problems.push(`qa[${i}] has ${dense.length} dialect markers; keep Northeastern flavor light, not a comedy bit`);
      }
    });
  }
  if (problems.length) {
    console.error("narration structure check failed:\n  " + problems.join("\n  "));
    process.exit(1);
  }
}

function checkLessonWorkflowContract(lessonDoc) {
  const result = validateLessonWorkflow({ lessonDoc, lessonPath });
  if (!result.active) return;
  if (result.warnings.length) {
    console.warn(formatWorkflowResults({ ...result, problems: [] }));
  }
  if (result.problems.length) {
    console.error("lesson workflow contract failed:\n" + formatWorkflowResults(result));
    process.exit(1);
  }
  console.log(`lesson workflow ok: ${basename(result.cardPath || "")} anchored to ${basename(result.packPath || "")}`);
}

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

function checkFaithfulness(lessonDoc, segs) {
  const cardPath = join(dir, lessonDoc.derived_from || "");
  if (!lessonDoc.derived_from || !existsSync(cardPath)) {
    console.error(`derived_from card missing: ${lessonDoc.derived_from}`);
    process.exit(1);
  }
  const card = JSON.parse(readFileSync(cardPath, "utf-8"));
  let master = null;
  if (lessonDoc.archetype_master_ref) {
    const masterPath = join(dir, lessonDoc.archetype_master_ref);
    if (existsSync(masterPath)) master = JSON.parse(readFileSync(masterPath, "utf-8"));
  }
  const problems = [];
  segs.forEach((s, i) => {
    if (!s.claim) return;
    if (!s.anchor) {
      problems.push(`seg#${i} ${s.kind}: claim=true but anchor is missing`);
      return;
    }
    let src = card;
    let path = s.anchor;
    if (s.anchor.startsWith("master:")) {
      if (!master) {
        problems.push(`seg#${i}: master anchor used but archetype_master_ref is missing`);
        return;
      }
      src = master;
      path = s.anchor.slice(7);
    }
    if (resolveAnchor(src, path) === undefined) problems.push(`seg#${i}: anchor not found: ${s.anchor}`);
  });
  if (problems.length) {
    console.error("faithfulness check failed:\n  " + problems.join("\n  "));
    process.exit(1);
  }
  console.log(`faithfulness ok: ${segs.filter((s) => s.claim).length} claimed segment(s) anchored`);
}

function speechNorm(text) {
  return String(text || "")
    .replace(/A、B/g, "A 和 B")
    .replace(/C、D/g, "C 和 D")
    .replace(/A、C、E/g, "A、C、E")
    .replace(/\//g, "、")
    .replace(/[（(]/g, "，")
    .replace(/[）)]/g, "，")
    .replace(/[，,]{2,}/g, "，")
    .trim();
}

function instructionForVoice(voice) {
  if (process.env.ALIYUN_TTS_INSTRUCTION !== undefined) return process.env.ALIYUN_TTS_INSTRUCTION;
  return "";
}

const QWEN_TTS_VOICES = new Set([
  "Aiden",
  "Arthur",
  "Bella",
  "Bellona",
  "Bunny",
  "Cherry",
  "Chelsie",
  "Eldric Sage",
  "Elias",
  "Ethan",
  "Jennifer",
  "Kai",
  "Katerina",
  "Maia",
  "Mia",
  "Mochi",
  "Momo",
  "Moon",
  "Neil",
  "Nini",
  "Nofish",
  "Ryan",
  "Serena",
  "Seren",
  "Vivian",
]);

function providerForVoice(voice) {
  return QWEN_TTS_VOICES.has(voice) ? "aliyun_qwen_tts" : "aliyun_cosyvoice";
}

function probeDuration(file) {
  return parseFloat(
    execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", file])
      .toString()
      .trim(),
  );
}

async function synthesizeSegment({ key, segment, voice, outFile }) {
  if (providerForVoice(voice) === "aliyun_qwen_tts") {
    return synthesizeQwenSegment({ key, segment, voice, outFile });
  }

  const inputPayload = {
    text: speechNorm(segment.text),
    voice,
    format: FORMAT,
    sample_rate: SAMPLE_RATE,
    volume: VOLUME,
    rate: RATE,
    language_hints: ["zh"],
  };
  const instruction = instructionForVoice(voice);
  if (instruction) inputPayload.instruction = instruction;

  const response = await fetch(ENDPOINT, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${key.value}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: MODEL,
      input: inputPayload,
    }),
  });

  const bodyText = await response.text();
  let body = null;
  try {
    body = JSON.parse(bodyText);
  } catch {
    // Leave body as text for error reporting below.
  }
  if (!response.ok) {
    throw new Error(`Aliyun TTS HTTP ${response.status}: ${bodyText.slice(0, 500)}`);
  }
  const audioUrl = body?.output?.audio?.url;
  if (!audioUrl) {
    throw new Error(`Aliyun TTS response missing output.audio.url: ${bodyText.slice(0, 500)}`);
  }

  const audio = await fetch(audioUrl);
  if (!audio.ok) throw new Error(`audio download HTTP ${audio.status}`);
  writeFileSync(outFile, Buffer.from(await audio.arrayBuffer()));
  return {
    provider: "aliyun_cosyvoice",
    model: MODEL,
    requestId: body?.request_id || null,
    characters: body?.usage?.characters ?? null,
    finishReason: body?.output?.finish_reason || null,
  };
}

async function synthesizeQwenSegment({ key, segment, voice, outFile }) {
  const response = await fetch(QWEN_TTS_ENDPOINT, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${key.value}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: QWEN_TTS_MODEL,
      input: {
        text: speechNorm(segment.text),
        voice,
        language_type: "Chinese",
      },
    }),
  });

  const bodyText = await response.text();
  let body = null;
  try {
    body = JSON.parse(bodyText);
  } catch {
    // Leave body as text for error reporting below.
  }
  if (!response.ok || body?.status_code >= 400 || body?.code) {
    throw new Error(`Aliyun Qwen-TTS HTTP ${response.status}: ${bodyText.slice(0, 500)}`);
  }
  const audioUrl = body?.output?.audio?.url;
  if (!audioUrl) {
    throw new Error(`Aliyun Qwen-TTS response missing output.audio.url: ${bodyText.slice(0, 500)}`);
  }

  const audio = await fetch(audioUrl);
  if (!audio.ok) throw new Error(`Qwen-TTS audio download HTTP ${audio.status}`);
  writeFileSync(outFile, Buffer.from(await audio.arrayBuffer()));
  return {
    provider: "aliyun_qwen_tts",
    model: QWEN_TTS_MODEL,
    requestId: body?.request_id || null,
    characters: body?.usage?.characters ?? body?.usage?.input_tokens ?? null,
    finishReason: body?.output?.finish_reason || null,
  };
}

const segs = flatten(lesson);
checkNarrationStructure(lesson, segs);
checkLessonWorkflowContract(lesson);
checkFaithfulness(lesson, segs);

function voiceForSegment(segment) {
  const speakerVoice = lesson.speakers?.[segment.speaker]?.voice;
  if (speakerVoice) return speakerVoice;
  if (segment.kind === "teach" && lesson.teach?.voice) return lesson.teach.voice;
  return VOICE;
}

if (PRINT) {
  const voices = Array.from(new Set(segs.map((s) => voiceForSegment(s))));
  const providers = Array.from(new Set(voices.map((voice) => `${providerForVoice(voice)}:${voice}`)));
  console.log(`provider=aliyun_mixed cosyvoice=${MODEL} qwen=${QWEN_TTS_MODEL} voices=${providers.join(",")}`);
  segs.forEach((s, i) => {
    const tag = s.kind === "teach" ? `[${s.state}]` : `[${s.kind.toUpperCase()}]`;
    console.log(
      `${String(i).padStart(2, "0")} ${tag} speaker=${s.speaker} voice=${voiceForSegment(s)}${
        s.claim ? ` anchor=${s.anchor}` : ""
      }\n   ${speechNorm(s.text)}\n`,
    );
  });
  process.exit(0);
}

const key = apiKey();
const stem = basename(lessonPath).replace(/\.json$/, "");
const mp3Out = join(dir, `${stem}.mp3`);
const timingOut = join(dir, `${stem}.timing.json`);
const tmp = join(dir, ".aliyun_lesson_tmp");
mkdirSync(tmp, { recursive: true });

try {
  const voices = Array.from(new Set(segs.map((s) => voiceForSegment(s))));
  const providers = Array.from(new Set(voices.map((voice) => `${providerForVoice(voice)}:${voice}`)));
  console.log(`tts provider=aliyun_mixed cosyvoice=${MODEL} qwen=${QWEN_TTS_MODEL} voices=${providers.join(",")} key=${key.name}`);
  const durs = [];
  const meta = [];
  for (const [i, s] of segs.entries()) {
    const raw = join(tmp, `${i}.${FORMAT}`);
    const wav = join(tmp, `${i}.wav`);
    const voice = voiceForSegment(s);
    const info = await synthesizeSegment({ key, segment: s, voice, outFile: raw });
    execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-i", raw, "-ar", "44100", "-ac", "1", wav]);
    const dur = probeDuration(wav);
    durs.push(dur);
    meta.push({ ...info, voice });
    console.log(
      `  ${String(i).padStart(2, "0")} ${s.state} ${info.provider}:${voice} ${dur.toFixed(2)}s chars=${
        info.characters ?? "?"
      } request_id=${info.requestId ?? "?"}`,
    );
  }

  const gapWav = join(tmp, "gap.wav");
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", String(GAP), gapWav]);

  const fileList = [];
  segs.forEach((_, i) => {
    fileList.push(`file '${i}.wav'`);
    if (i < segs.length - 1) fileList.push("file 'gap.wav'");
  });
  writeFileSync(join(tmp, "filelist.txt"), fileList.join("\n"));
  execFileSync(
    "ffmpeg",
    ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", "filelist.txt", "-c:a", "libmp3lame", "-q:a", "3", mp3Out],
    { cwd: tmp },
  );

  let t = 0;
  const segments = segs.map((s, i) => {
    const startSec = Number(t.toFixed(3));
    t += durs[i];
    const out = {
      idx: i,
      kind: s.kind,
      state: s.state,
      qaIndex: s.qaIndex ?? null,
      keycard: s.keycard ?? null,
      speaker: s.speaker,
      voice: meta[i].voice,
      anchor: s.anchor,
      claim: s.claim,
      text: s.text,
      startSec,
      durSec: Number(durs[i].toFixed(3)),
      requestId: meta[i].requestId,
      provider: meta[i].provider,
      model: meta[i].model,
    };
    if (i < segs.length - 1) t += GAP;
    return out;
  });
  const totalSec = Number((t + TAIL).toFixed(3));
  const lastTeach = segments.filter((s) => s.kind === "teach").at(-1);
  const teachEndSec = lastTeach ? Number((lastTeach.startSec + lastTeach.durSec).toFixed(3)) : 0;

  writeFileSync(
    timingOut,
    JSON.stringify(
      {
        audio: basename(mp3Out),
        provider: "aliyun_mixed",
        providers: Array.from(new Set(segments.map((s) => `${s.provider}:${s.model}`))),
        model: MODEL,
        qwenModel: QWEN_TTS_MODEL,
        voices: Array.from(new Set(segments.map((s) => s.voice))),
        defaultVoice: VOICE,
        instruction: process.env.ALIYUN_TTS_INSTRUCTION || null,
        sampleRate: SAMPLE_RATE,
        rate: RATE,
        volume: VOLUME,
        totalSec,
        teachEndSec,
        style: "teach_then_qa",
        segments,
      },
      null,
      2,
    ),
  );
  console.log(
    `done ${basename(mp3Out)} + ${basename(timingOut)} (${totalSec.toFixed(1)}s, teach ${teachEndSec.toFixed(1)}s, ${segments.length} segments)`,
  );
} finally {
  rmSync(tmp, { recursive: true, force: true });
}

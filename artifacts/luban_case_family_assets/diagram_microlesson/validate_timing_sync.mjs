#!/usr/bin/env node
// timing gate(方法2 §4 新增门 / production-workflow §6 缺门之一)
// 校验讲懂动画【总时长】+ 每 claim 段【sync_keyword】覆盖并命中对应旁白段。
// fail-closed,三段式 message(可串 gate.sh)。
// 用法: node validate_timing_sync.mjs <topic>.lesson.timing.json [--max 150] [--teach-max 110]
//   读同名 <topic>.lesson.json 查 sync_keyword(teach.beats / qa.a)。
// 为什么:MVP 暴露 J01 讲懂 207s(远超 ~2 分钟轻练定位),防漂移闸/preview 门都拦不住——本门专拦超长 + 音画对齐缺口。
import { readFileSync, existsSync } from "node:fs";

const argv = process.argv.slice(2);
const timingPath = argv.find((x) => !x.startsWith("--"));
const num = (flag, def) => (argv.includes(flag) ? Number(argv[argv.indexOf(flag) + 1]) : def);
const MAX = num("--max", 150); // 总时长上限(秒):讲懂动画应控时 ~2 分钟
const TEACH_MAX = num("--teach-max", 110); // 讲解段(到答疑前)上限

if (!timingPath || !existsSync(timingPath)) {
  console.error(`FAIL - timing.json 不存在: ${timingPath}`);
  process.exit(2);
}
const t = JSON.parse(readFileSync(timingPath, "utf-8"));
const file = timingPath.split("/").pop();
let fails = 0;

function normalizeText(value) {
  return String(value ?? "")
    .toLowerCase()
    .replace(/\s+/g, "")
    .replace(/[，,。.;；:：、"'‘’“”()（）【】\[\]·\-—_]/g, "");
}

function keywordHitsSegment(keyword, segment) {
  const needle = normalizeText(keyword);
  if (!needle) return false;
  const haystack = normalizeText(
    [
      segment?.text,
      segment?.keycard?.text,
      segment?.anchor,
    ].filter(Boolean).join(" ")
  );
  return haystack.includes(needle);
}

function expectedClaimSegments(lesson, timing) {
  const expected = [];
  const teachSegments = (timing.segments || []).filter((segment) => segment.kind === "teach");
  (lesson.teach?.beats || []).forEach((beat, index) => {
    if (!beat.claim) return;
    expected.push({
      source: `teach:${beat.id}`,
      syncKeyword: beat.sync_keyword,
      segment: teachSegments[index],
      hasActions: Array.isArray(beat.animation_action) && beat.animation_action.length > 0,
    });
  });
  (lesson.qa || []).forEach((pair, index) => {
    if (!pair.a?.claim) return;
    const segment = (timing.segments || []).find(
      (item) => item.kind === "a" && item.qaIndex === index
    );
    expected.push({
      source: `qa${index}.a`,
      syncKeyword: pair.a.sync_keyword,
      segment,
      hasActions: false,
    });
  });
  return expected;
}

// 1. 总时长
if (typeof t.totalSec === "number" && t.totalSec > MAX) {
  console.log(`FAIL ${file} total_duration: 总时长 ${t.totalSec.toFixed(1)}s 超过上限 ${MAX}s —— 讲懂动画应控时 ~2 分钟,砍 hook 冗余/合并旁白`);
  fails++;
} else {
  console.log(`PASS ${file} total_duration: ${(t.totalSec ?? 0).toFixed(1)}s <= ${MAX}s`);
}

// 2. 讲解段时长(到答疑前)
if (typeof t.teachEndSec === "number" && t.teachEndSec > TEACH_MAX) {
  console.log(`WARN ${file} teach_duration: 讲解段 ${t.teachEndSec.toFixed(1)}s > ${TEACH_MAX}s,讲懂偏长(答疑可另算)`);
}

// 3. sync_keyword 覆盖(读同名 lesson.json)
const lessonPath = timingPath.replace(/\.timing\.json$/, ".json");
if (existsSync(lessonPath)) {
  const L = JSON.parse(readFileSync(lessonPath, "utf-8"));
  const missing = [];
  const mismatched = [];
  const missingSegments = [];
  const missingActionTimes = [];
  for (const item of expectedClaimSegments(L, t)) {
    if (!item.syncKeyword) {
      missing.push(item.source);
      continue;
    }
    if (!item.segment) {
      missingSegments.push(item.source);
      continue;
    }
    if (typeof item.segment.startSec !== "number" || typeof item.segment.durSec !== "number") {
      missingActionTimes.push(item.source);
    }
    if (!keywordHitsSegment(item.syncKeyword, item.segment)) {
      mismatched.push(`${item.source}(${item.syncKeyword})`);
    }
  }
  if (missing.length) {
    console.log(`FAIL ${file} sync_keyword: ${missing.length} 个 claim 段缺 sync_keyword(音画对齐无依据): ${missing.join(", ")}`);
    fails++;
  } else if (missingSegments.length) {
    console.log(`FAIL ${file} sync_keyword: ${missingSegments.length} 个 claim 段找不到对应 timing segment: ${missingSegments.join(", ")}`);
    fails++;
  } else if (missingActionTimes.length) {
    console.log(`FAIL ${file} sync_keyword: ${missingActionTimes.length} 个 claim 段缺 startSec/durSec,无法绑定动作时间: ${missingActionTimes.join(", ")}`);
    fails++;
  } else if (mismatched.length) {
    console.log(`FAIL ${file} sync_keyword: ${mismatched.length} 个 sync_keyword 未命中对应旁白/keycard 文本: ${mismatched.join(", ")}`);
    fails++;
  } else {
    console.log(`PASS ${file} sync_keyword: 所有 claim 段都带 sync_keyword 且命中对应 timing 文本`);
  }
} else {
  console.log(`WARN ${file} sync_keyword: 找不到同名 lesson.json(${lessonPath.split("/").pop()}),跳过 sync_keyword 检查`);
}

process.exit(fails ? 1 : 0);

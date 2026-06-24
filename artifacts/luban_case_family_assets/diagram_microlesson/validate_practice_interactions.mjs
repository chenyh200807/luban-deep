#!/usr/bin/env node
import fs from "node:fs";

const [htmlPath] = process.argv.slice(2);
if (!htmlPath) {
  console.error("usage: validate_practice_interactions.mjs <practice.html>");
  process.exit(2);
}

const html = fs.readFileSync(htmlPath, "utf8");
const dataMatch = html.match(/<script[^>]+id=["']practiceData["'][^>]*>([\s\S]*?)<\/script>/);
let practiceData = null;
let dataError = "";
if (dataMatch) {
  try {
    practiceData = JSON.parse(dataMatch[1]);
  } catch (error) {
    dataError = error instanceof Error ? error.message : String(error);
  }
}

const checks = [
  ["practice shell", /data-practice-shell=["']animation-ir-practice["']/.test(html)],
  ["practice data", /id=["']practiceData["']/.test(html)],
  ["feedback target", /id=["']practiceFeedback["']/.test(html)],
  ["primary answer action", /data-answer-action=["']submit-or-next["']/.test(html)],
  ["option ids", /data-option-id/.test(html)],
  ["choice click handler", /addEventListener\(["']click["'],\s*\(\)\s*=>\s*choose/.test(html)],
  ["submit click handler", /primary\.addEventListener\(["']click["'],\s*goNext\)/.test(html)],
  ["blocked feedback", /先选一个判断/.test(html)],
  ["done state", /practiceState=['"]done['"]/.test(html) || /dataset\.practiceState\s*=\s*['"]done['"]/.test(html)],
  ["learner diagnosis", /buildDiagnosis/.test(html) && /表现分析/.test(html)],
  ["needs drill flag", /practiceNeedsDrill/.test(html)],
  ["weak drill action", /id=["']drillBtn["']/.test(html) && /data-answer-action=["']drill-weak-points["']/.test(html)],
  ["luban followup action", /id=["']aiCoachBtn["']/.test(html) && /data-answer-action=["']ask-luban-followup["']/.test(html)],
  ["luban context payload", /luban_practice_diagnosis/.test(html) && /buildAskPayload/.test(html)],
  ["host bridge", /miniProgram\.postMessage/.test(html) || /parent\.postMessage/.test(html)],
  ["practice data parses", !!practiceData && !dataError],
  ["no keypoint label answers", practiceData ? noKeypointLabelAnswers(practiceData) : false],
  ["scenario question fields", practiceData ? hasScenarioQuestionFields(practiceData) : false],
  ["per-option feedback", practiceData ? hasPerOptionFeedback(practiceData) : false],
  ["readable explanations", practiceData ? hasReadableExplanations(practiceData) : false],
  ["no pre-answer answer leak", /hotIndex\s*=\s*a\s*\?\s*Number\(visual\.hotIndex\)\s*:\s*-1/.test(html) && !/els\.qFocus\.textContent\s*=\s*DATA\.keyPoints\[q\.focusIndex\]/.test(html)],
];

function norm(value) {
  return String(value || "").replace(/\s+/g, "").trim();
}

function questions(data) {
  return Array.isArray(data.questions) ? data.questions : [];
}

function noKeypointLabelAnswers(data) {
  const keyPoints = new Set((Array.isArray(data.keyPoints) ? data.keyPoints : []).map(norm).filter(Boolean));
  return questions(data).length > 0 && questions(data).every((question) => {
    const options = Array.isArray(question.options) ? question.options : [];
    return options.length >= 3 && options.every((option) => {
      const label = norm(option.label);
      const reason = norm(option.reason);
      return label.length >= 10 && !keyPoints.has(label) && reason !== "路径+判断依据";
    });
  });
}

function hasScenarioQuestionFields(data) {
  return questions(data).length > 0 && questions(data).every((question) => {
    const visual = question.visual || {};
    return Boolean(
      question.stageLabel
        && question.skill
        && question.student
        && question.stem
        && Array.isArray(visual.items)
        && visual.items.length >= 3
        && Number.isInteger(visual.hotIndex)
    );
  });
}

function hasPerOptionFeedback(data) {
  return questions(data).length > 0 && questions(data).every((question) => {
    const feedback = question.optionFeedback || {};
    const options = Array.isArray(question.options) ? question.options : [];
    return options
      .filter((option) => option.id !== question.answer)
      .every((option) => norm(feedback[option.id]).length >= 18);
  });
}

function hasReadableExplanations(data) {
  const markers = ["因为", "不是", "不能", "要", "先", "必须", "阅卷", "扣分", "采分"];
  return questions(data).length > 0 && questions(data).every((question) => {
    const texts = [question.correct, question.wrong, ...Object.values(question.optionFeedback || {})].map(String);
    return texts.every((text) => norm(text).length >= 18 && markers.some((marker) => text.includes(marker)));
  });
}

const failed = checks.filter(([, ok]) => !ok).map(([name]) => name);
if (failed.length) {
  console.error(`practice interaction gate: FAIL ${htmlPath}`);
  for (const name of failed) console.error(`- missing ${name}`);
  if (dataError) console.error(`- practice data parse error: ${dataError}`);
  process.exit(1);
}

console.log(`practice interaction gate: PASS ${htmlPath}`);

function asObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function asList(value) {
  return Array.isArray(value) ? value : [];
}

function compactText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function multilineText(value) {
  return String(value || "").replace(/\r\n/g, "\n").trim();
}

function normalizeTurn(item, index) {
  var source = asObject(item);
  var role = compactText(source.role || "system");
  var label = compactText(source.label || (role === "student" ? "学员" : "系统"));
  var content = multilineText(source.content || source.text || "");
  if (!content) return null;
  return {
    key: compactText(source.key || role + "-" + index),
    role: role === "student" || role === "user" ? "student" : "system",
    label: label,
    content: content,
  };
}

function fallbackTurns(card) {
  var source = asObject(card);
  var turns = [
    normalizeTurn(
      {
        role: "system",
        label: "系统出题",
        content: compactText(source.questionText || source.title),
      },
      0,
    ),
    normalizeTurn(
      {
        role: "student",
        label: "学员作答",
        content: compactText(source.answerLine),
      },
      1,
    ),
    normalizeTurn(
      {
        role: "system",
        label: "系统解析",
        content: multilineText(source.diagnosisDetail || source.diagnosis || source.explanation),
      },
      2,
    ),
  ];
  return turns.filter(Boolean);
}

function detailTurns(detail, card) {
  var payload = asObject(detail);
  var direct = asList(asObject(payload.conversation).turns)
    .map(normalizeTurn)
    .filter(Boolean);
  return direct.length ? direct : fallbackTurns(card);
}

function buildAttemptDetailViewModel(detail, card) {
  var payload = asObject(detail);
  var source = asObject(card);
  var question = asObject(payload.question);
  var answer = asObject(payload.answer);
  var diagnosis = asObject(payload.diagnosis);
  var explanation = asObject(payload.explanation);
  var title = compactText(
    asObject(payload.conversation).title ||
      question.stem ||
      source.questionText ||
      source.title ||
      "本次作答复盘",
  );
  var resultLabel = compactText(answer.result_label || source.resultLabel || "");
  var concept = compactText(diagnosis.concept_label || source.concept || "");
  var error = compactText(diagnosis.detail || diagnosis.error_label || source.diagnosisDetail || source.diagnosis);
  var answerLine = compactText(source.answerLine);
  if (!answerLine && (answer.user_answer || answer.correct_answer)) {
    answerLine = ["你选：" + compactText(answer.user_answer), "正确：" + compactText(answer.correct_answer)]
      .filter(function (item) {
        return item.indexOf("：") < item.length - 1;
      })
      .join(" · ");
  }
  return {
    title: title,
    subtitle: compactText(source.timeLabel || "来自学情作答记录"),
    resultLabel: resultLabel,
    tone: compactText(source.tone || (resultLabel === "答对" ? "good" : "bad")),
    concept: concept,
    answerLine: answerLine,
    error: error,
    explanation: multilineText(explanation.summary || source.explanation),
    nextTraining: compactText(asObject(payload.next_training).focus || asObject(payload.next_training).concept || ""),
    turns: detailTurns(payload, source),
  };
}

module.exports = {
  buildAttemptDetailViewModel: buildAttemptDetailViewModel,
};

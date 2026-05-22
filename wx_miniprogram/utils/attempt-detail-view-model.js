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

function richExplanationText(detail, card) {
  var payload = asObject(detail);
  var source = asObject(card);
  var explanation = asObject(payload.explanation);
  var fullText = multilineText(explanation.full_text || explanation.content || explanation.text || "");
  if (fullText) return fullText;
  var systemTurn = detailTurns(payload, source).filter(function (item) {
    return item.role === "system" && item.label.indexOf("解析") >= 0;
  })[0];
  return multilineText((systemTurn && systemTurn.content) || explanation.summary || source.explanation);
}

function normalizeHeading(value) {
  var text = compactText(value).replace(/^[:：\-\s]+/, "").replace(/[:：\-\s]+$/, "");
  var aliases = {
    "阅卷结论": "阅卷结论",
    "正确答案": "正确答案",
    "为什么错": "为什么错",
    "知识点": "知识点",
    "易错点": "易错点",
    "记忆口诀": "记忆口诀",
    "下一步": "下一步",
    "逐项解析": "逐项解析",
  };
  return aliases[text] || text;
}

function parseExplanationSections(text) {
  var raw = multilineText(text);
  if (!raw) return [];
  var lines = raw.split("\n");
  var sections = [];
  var current = null;
  lines.forEach(function (line) {
    var match = String(line || "").match(/^#{2,4}\s+(.+?)\s*$/);
    if (match) {
      if (current && multilineText(current.content).length) {
        sections.push(current);
      }
      current = {
        key: "section-" + sections.length,
        label: normalizeHeading(match[1]),
        content: "",
      };
      return;
    }
    if (!current) {
      current = { key: "section-0", label: "系统解析", content: "" };
    }
    current.content = [current.content, line].filter(Boolean).join("\n");
  });
  if (current && multilineText(current.content).length) {
    sections.push(current);
  }
  return sections
    .map(function (item, index) {
      return {
        key: item.key || "section-" + index,
        label: compactText(item.label || "系统解析"),
        content: multilineText(item.content),
      };
    })
    .filter(function (item) {
      return item.content;
    });
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
  var richText = richExplanationText(payload, source);
  var explanationSections = parseExplanationSections(richText);
  return {
    title: title,
    subtitle: compactText(source.timeLabel || "来自学情作答记录"),
    resultLabel: resultLabel,
    tone: compactText(source.tone || (resultLabel === "答对" ? "good" : "bad")),
    concept: concept,
    answerLine: answerLine,
    error: error,
    explanation: multilineText(explanation.summary || source.explanation),
    explanationSections: explanationSections,
    nextTraining: compactText(asObject(payload.next_training).focus || asObject(payload.next_training).concept || ""),
    turns: detailTurns(payload, source),
  };
}

module.exports = {
  buildAttemptDetailViewModel: buildAttemptDetailViewModel,
  parseExplanationSections: parseExplanationSections,
};

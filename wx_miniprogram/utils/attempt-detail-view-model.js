var markdown = require("./markdown");

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

function studentFacingText(value) {
  var text = multilineText(value);
  if (!text) return "";
  var lines = text.split("\n");
  var output = [];
  var tableHeaders = null;
  for (var i = 0; i < lines.length; i++) {
    var line = String(lines[i] || "");
    if (/^\s*(?:---+|\*\*\*+)\s*$/.test(line)) continue;
    if (isMarkdownTableSeparator(line)) continue;
    if (isMarkdownTableRow(line)) {
      var cells = markdownTableCells(line);
      if (i + 1 < lines.length && isMarkdownTableSeparator(lines[i + 1])) {
        tableHeaders = cells;
        continue;
      }
      output.push(tableRowToStudentText(cells, tableHeaders));
      continue;
    }
    output.push(cleanStudentLine(line));
  }
  return output.filter(Boolean).join("\n").trim();
}

function cleanStudentLine(line) {
  return String(line || "")
    .replace(/^#{1,6}\s*/g, "")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/[✅✔️]/g, "正确")
    .replace(/[❌✘]/g, "错误")
    .replace(/\btraining_mode\s*=\s*mixed_rev\b/gi, "")
    .replace(/\btraining_mode\s*=\s*[A-Za-z0-9_\-]+\b/gi, "")
    .replace(/\bmixed_rev\b/gi, "混合复习")
    .replace(/\bdiscovery_probe\b/gi, "摸底测评")
    .replace(/\bcode_application\b/gi, "规范应用")
    .replace(/\bquestion_reading\b/gi, "审题")
    .replace(/\brecurrence\b/gi, "同类错误复发")
    .replace(/[；;，,]\s*$/g, "")
    .trim();
}

function isMarkdownTableRow(line) {
  return /^\s*\|.+\|\s*$/.test(String(line || ""));
}

function isMarkdownTableSeparator(line) {
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(String(line || ""));
}

function markdownTableCells(line) {
  return String(line || "")
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map(cleanStudentLine)
    .filter(Boolean);
}

function tableRowToStudentText(cells, headers) {
  var values = Array.isArray(cells) ? cells : [];
  var keys = Array.isArray(headers) ? headers : [];
  if (!values.length) return "";
  if (keys.length === values.length) {
    return values
      .map(function (cell, index) {
        return keys[index] + "：" + cell;
      })
      .join("；");
  }
  return values.join("；");
}

function normalizeTurn(item, index) {
  var source = asObject(item);
  var role = compactText(source.role || "system");
  var label = compactText(source.label || (role === "student" ? "学员" : "系统"));
  var content = studentFacingText(source.content || source.text || "");
  if (!content) return null;
  return {
    key: compactText(source.key || role + "-" + index),
    role: role === "student" || role === "user" ? "student" : "system",
    label: label,
    content: content,
  };
}

function normalizeNextTraining(value) {
  var text = studentFacingText(value);
  if (!text) return "";
  text = text.replace(/\s*[；;，,]\s*$/g, "").trim();
  if (!text || text === "混合复习") return "做一组混合复习训练";
  return text;
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
      var content = multilineText(item.content);
      return {
        key: item.key || "section-" + index,
        label: compactText(item.label || "系统解析"),
        content: content,
        blocks: parseExplanationBlocks(content),
      };
    })
    .filter(function (item) {
      return item.content;
    });
}

function parseExplanationBlocks(content) {
  var text = multilineText(content);
  if (!text) return [];
  try {
    return markdown.parse(text).filter(function (block) {
      return block && block.type !== "hr";
    });
  } catch (_err) {
    return [
      {
        type: "paragraph",
        raw: text,
        content: markdown.parseInline ? markdown.parseInline(text) : [{ type: "text", text: text }],
        nodes: markdown.spansToRichTextNodes
          ? markdown.spansToRichTextNodes(markdown.parseInline ? markdown.parseInline(text) : [{ type: "text", text: text }])
          : [{ type: "text", text: text }],
      },
    ];
  }
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
    nextTraining: normalizeNextTraining(asObject(payload.next_training).focus || asObject(payload.next_training).concept || ""),
    turns: detailTurns(payload, source),
  };
}

module.exports = {
  buildAttemptDetailViewModel: buildAttemptDetailViewModel,
  parseExplanationSections: parseExplanationSections,
  parseExplanationBlocks: parseExplanationBlocks,
};

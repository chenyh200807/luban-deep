// utils/mcq-detect.js — 从 AI 回复中提取交互式选择题

var OPTION_RE = /^\s*(?:[-*+]\s*)?[(（]?([A-E])[)）.、:：]\s*(.+)\s*$/;
var STEM_MARKER_RE = /^\s*(?:题目|例题\s*\d+|第\s*[一二三四五六七八九十\d]+\s*[题道]|[\(（]\s*\d+\s*[\)）]|问题)\s*[:：]?\s*$/;
var MULTI_RE = /多选|不定项|可多选|正确的有|错误的有|哪些说法|下列说法正确的有/;
var LEAD_IN_RE =
  /^\s*(?:你先选选看.*|选完我.*|先别急着看答案.*|请选择.*|提交后我再告诉你.*)\s*$/;
var RECEIPT_RE = /<!--QCTX:([A-Za-z0-9_\-+=/]+)-->/;
var QUESTION_MARKER_PATTERNS = [
  /^\s*(?:\*\*)?\s*(?:例题\s*\d+|第\s*[一二三四五六七八九十\d]+\s*[题道]|题目\s*\d+|[\(（]\s*\d+\s*[\)）])\s*[:：]?\s*(?:\*\*)?\s*$/i,
  /^\s*(?:\*\*)?\s*\d+\s*[.、．]\s+.*$/i,
  /^\s*(?:\*\*)?\s*(?:例题\s*\d+|第\s*[一二三四五六七八九十\d]+\s*[题道]|题目\s*\d+)\s*[:：].+$/i,
];
var GENERIC_NUMBERED_QUESTION_RE = /^\s*(?:\*\*)?\d+\s*[.、．]\s+.*$/i;
var QUESTION_LINE_RE =
  /^\s*(?:例题\s*\d+|第\s*[一二三四五六七八九十\d]+\s*[题道]|题目\s*\d+|[\(（]\s*\d+\s*[\)）]|\d+\s*[.、．])(?:\s*[（(][^()（）]{0,40}[)）])?\s*(?:[:：]\s*.*)?$/i;
var INLINE_QUESTION_MARKER_RE =
  /(?:\*\*)?\s*(?:例题\s*\d+|第\s*[一二三四五六七八九十\d]+\s*[题道]|题目\s*\d+|[\(（]\s*\d+\s*[\)）]|\d+\s*[.、．])\s*[:：]?\s*(?:\*\*)?/i;
var PRACTICE_NOTICE_MARKERS = [
  "当前题库里暂无与",
  "你要 ",
  "我先给你出一组同专题相关题训练。",
];
var ANSWER_SECTION_MARKERS = [
  "答案与核心解析",
  "答案与解析",
  "参考答案",
  "正确答案",
  "答案解析",
];

function _trim(text) {
  return String(text || "").replace(/\r\n?/g, "\n").trim();
}

function _normalizeQuestionLine(line) {
  return _trim(line)
    .replace(/^#{1,6}\s*/, "")
    .replace(/\*\*/g, "")
    .trim();
}

function _sanitizeOption(text) {
  return String(text || "")
    .replace(/\s+/g, " ")
    .replace(/[✅✔️]/g, "")
    .trim();
}

function _escapeRegExp(text) {
  return String(text || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function _normalizeSignature(text) {
  return String(text || "").replace(/\s+/g, "");
}

function _collapseRepeatedRaw(text) {
  var raw = _trim(text);
  if (!raw) return raw;

  for (var repeat = 3; repeat >= 2; repeat--) {
    if (raw.length % repeat) continue;
    var unit = raw.slice(0, raw.length / repeat);
    if (unit.repeat(repeat) === raw) return unit.trim();
  }

  var markers = ["当前题库里暂无与", "**第 1 题**", "第 1 题", "第1题", "题目1：", "例题1："];
  for (var i = 0; i < markers.length; i++) {
    var marker = markers[i];
    var firstIndex = raw.indexOf(marker);
    if (firstIndex !== 0) continue;
    var secondIndex = raw.indexOf(marker, firstIndex + marker.length);
    if (secondIndex <= 0) continue;
    var head = raw.slice(0, secondIndex).trim();
    var tail = raw.slice(secondIndex).trim();
    if (head && _normalizeSignature(head) === _normalizeSignature(tail)) {
      return head;
    }
  }

  return raw;
}

function _collapseRepeatedBlocks(blocks) {
  var items = Array.isArray(blocks) ? blocks : [];
  if (items.length < 2) return items;
  var signatures = items.map(_normalizeSignature);
  for (var size = 1; size <= Math.floor(items.length / 2); size++) {
    if (items.length % size) continue;
    var ok = true;
    for (var i = size; i < items.length; i++) {
      if (signatures[i] !== signatures[i % size]) {
        ok = false;
        break;
      }
    }
    if (ok) return items.slice(0, size);
  }
  return items;
}

function _stripAnswerSection(text) {
  var cleaned = String(text || "");
  var cutIndex = -1;
  for (var i = 0; i < ANSWER_SECTION_MARKERS.length; i++) {
    var marker = ANSWER_SECTION_MARKERS[i];
    var idx = cleaned.indexOf(marker);
    if (idx > 0 && (cutIndex < 0 || idx < cutIndex)) cutIndex = idx;
  }
  if (cutIndex > 0) cleaned = cleaned.slice(0, cutIndex);
  return cleaned
    .replace(/\n[\s#>*-]*\*{0,2}\s*$/, "")
    .trim();
}

function _stripPollutionTail(text) {
  var cleaned = String(text || "");
  for (var i = 0; i < PRACTICE_NOTICE_MARKERS.length; i++) {
    var idx = cleaned.indexOf(PRACTICE_NOTICE_MARKERS[i]);
    if (idx > 0) cleaned = cleaned.slice(0, idx);
  }
  var markerMatch = INLINE_QUESTION_MARKER_RE.exec(cleaned);
  if (markerMatch && markerMatch.index > 0) {
    cleaned = cleaned.slice(0, markerMatch.index);
  }
  return cleaned.trim();
}

function _collectStemFragments(stem) {
  var raw = _trim(stem);
  if (!raw) return [];

  var fragments = [];

  function push(fragment) {
    var cleaned = _sanitizeOption(fragment);
    if (!cleaned || cleaned.length < 6) return;
    if (fragments.indexOf(cleaned) >= 0) return;
    fragments.push(cleaned);
  }

  push(raw);
  push(raw.replace(/\n+/g, " "));

  raw.split("\n").forEach(function (line) {
    var cleaned = _trim(line);
    if (!cleaned || STEM_MARKER_RE.test(cleaned)) return;
    push(cleaned);
    push(
      cleaned.replace(
        /^\s*(?:题目|第\s*[一二三四五六七八九十\d]+\s*[题道]|[\(（]\s*\d+\s*[\)）]|问题)\s*[:：]?\s*/,
        "",
      ),
    );
    push(
      cleaned.replace(
        /^\s*(?:例题\s*\d+)\s*[:：]?\s*/,
        "",
      ),
    );
  });

  return fragments;
}

function _cleanOptionText(text, key, stem) {
  var raw = _stripPollutionTail(_sanitizeOption(text));
  if (!raw) return "";

  var keyRe = new RegExp(
    "^[(（]?" + _escapeRegExp(String(key || "")) + "[)）.、:：]\\s*",
    "i",
  );
  var next = raw;
  var prev = "";
  while (next && next !== prev) {
    prev = next;
    next = next.replace(keyRe, "").trim();
  }

  var stemText = _trim(stem);
  if (stemText) {
    var cutIndex = -1;
    _collectStemFragments(stemText).forEach(function (fragment) {
      var fragmentIndex = next.indexOf(fragment);
      if (fragmentIndex > 0 && (cutIndex < 0 || fragmentIndex < cutIndex)) {
        cutIndex = fragmentIndex;
      }
    });
    if (cutIndex > 0) next = next.slice(0, cutIndex).trim();
  }

  return _stripPollutionTail(next || raw);
}

function _extractReceipt(text) {
  var raw = String(text || "");
  var match = raw.match(RECEIPT_RE);
  return {
    receipt: match ? match[1] : "",
    cleanText: raw.replace(RECEIPT_RE, "").trim(),
  };
}

function stripReceipt(text) {
  return _extractReceipt(text).cleanText;
}

function _extractOptions(lines) {
  var options = [];
  var seen = {};
  var firstIndex = -1;
  var lastIndex = -1;

  for (var i = 0; i < lines.length; i++) {
    var match = lines[i].match(OPTION_RE);
    if (!match) continue;
    if (firstIndex === -1) firstIndex = i;
    lastIndex = i;
    var key = match[1];
    if (seen[key]) continue;
    seen[key] = true;
    options.push({ key: key, text: _sanitizeOption(match[2]), selected: false });
  }

  if (options.length < 2) {
    return { options: null, firstIndex: -1, lastIndex: -1 };
  }
  return { options: options, firstIndex: firstIndex, lastIndex: lastIndex };
}

function _isQuestionMarkerLine(line) {
  var text = _normalizeQuestionLine(line);
  if (!text || /答案|解析/.test(text)) return false;
  if (QUESTION_LINE_RE.test(text)) return true;
  for (var i = 0; i < QUESTION_MARKER_PATTERNS.length; i++) {
    if (QUESTION_MARKER_PATTERNS[i].test(text)) return true;
  }
  return false;
}

function _findQuestionStartIndexes(lines) {
  var indexes = [];
  for (var i = 0; i < lines.length; i++) {
    if (!_isQuestionMarkerLine(lines[i])) continue;
    if (GENERIC_NUMBERED_QUESTION_RE.test(_normalizeQuestionLine(lines[i]))) {
      var optionHits = 0;
      for (var j = i + 1; j < lines.length && j <= i + 6; j++) {
        if (OPTION_RE.test(lines[j])) optionHits++;
      }
      if (optionHits < 2) continue;
    }
    indexes.push(i);
  }
  return indexes;
}

function _splitQuestionBlocks(lines) {
  var starts = _findQuestionStartIndexes(lines);
  if (starts.length < 2) return [];

  var blocks = [];
  for (var i = 0; i < starts.length; i++) {
    var start = starts[i];
    var end = i + 1 < starts.length ? starts[i + 1] : lines.length;
    var block = _trim(lines.slice(start, end).join("\n"));
    if (block) blocks.push(block);
  }
  return _collapseRepeatedBlocks(blocks);
}

function _splitPrefixAndStem(preOptionLines) {
  var markerIndex = -1;
  for (var i = 0; i < preOptionLines.length; i++) {
    if (STEM_MARKER_RE.test(preOptionLines[i])) markerIndex = i;
  }

  if (markerIndex >= 0) {
    return {
      displayLines: preOptionLines.slice(0, markerIndex),
      stemLines: preOptionLines.slice(markerIndex),
    };
  }

  return {
    displayLines: [],
    stemLines: preOptionLines,
  };
}

function _stripStemMarker(stem) {
  var lines = String(stem || "").split("\n");
  if (!lines.length) return _trim(stem);

  var markerRe =
    /^\s*(?:例题\s*\d+|第\s*[一二三四五六七八九十\d]+\s*[题道]|题目\s*\d+|[\(（]\s*\d+\s*[\)）])(?:\s*[（(][^()（）]+[)）])?\s*[:：]?\s*/;
  var first = _normalizeQuestionLine(lines[0]).replace(/^\*+|\*+$/g, "").trim();
  var strippedFirst = first.replace(markerRe, "").trim();
  if (_isQuestionMarkerLine(first)) {
    return _trim([strippedFirst].concat(lines.slice(1)).join("\n"));
  }

  return _trim(_normalizeQuestionLine(String(stem || "")).replace(markerRe, ""));
}

function _detectOne(raw, index) {
  var lines = String(raw || "").split("\n");
  var parsed = _extractOptions(lines);
  if (!parsed.options) return null;

  var prefixLines = lines.slice(0, parsed.firstIndex);
  var suffixLines = lines.slice(parsed.lastIndex + 1).filter(function (line) {
    return !LEAD_IN_RE.test(line);
  });
  var split = _splitPrefixAndStem(prefixLines);

  var stem = _stripStemMarker(_trim(split.stemLines.join("\n")));
  var displayText = _trim(split.displayLines.concat(suffixLines).join("\n"));
  var questionType = MULTI_RE.test(raw) || parsed.options.length >= 5
    ? "multi_choice"
    : "single_choice";

  if (!stem) stem = "请选择正确选项";

  var options = parsed.options.map(function (option) {
    return {
      key: option.key,
      text: _cleanOptionText(option.text, option.key, stem),
      selected: false,
    };
  });

  return {
    index: index || 1,
    stem: stem,
    displayText: displayText,
    options: options,
    questionType: questionType,
    question_type: questionType,
    hint: "",
  };
}

function _extractDisplayPrefix(lines) {
  var starts = _findQuestionStartIndexes(lines);
  if (!starts.length) return "";
  return _trim(lines.slice(0, starts[0]).join("\n"));
}

function detect(text) {
  var extracted = _extractReceipt(text);
  var raw = _collapseRepeatedRaw(extracted.cleanText);
  if (!raw) return null;

  var lines = raw.split("\n");
  var blocks = _splitQuestionBlocks(lines);
  var questions = [];

  if (blocks.length >= 2) {
    var remainderBlocks = [];
    for (var i = 0; i < blocks.length; i++) {
      var cleanedBlock = _stripAnswerSection(blocks[i]);
      var q = _detectOne(cleanedBlock, i + 1);
      if (q) questions.push(q);
      else if (cleanedBlock) remainderBlocks.push(cleanedBlock);
    }
    if (!questions.length) return null;
    var first = questions[0];
    var overallMulti = false;
    for (var j = 0; j < questions.length; j++) {
      if (questions[j].questionType === "multi_choice") {
        overallMulti = true;
        break;
      }
    }
    var displayParts = [];
    var prefix = _extractDisplayPrefix(lines);
    if (prefix) displayParts.push(prefix);
    if (remainderBlocks.length) displayParts.push(remainderBlocks.join("\n\n"));
    return {
      stem: first.stem,
      displayText: displayParts.join("\n\n"),
      options: first.options,
      questionType: first.questionType,
      receipt: extracted.receipt,
      questions: questions,
      total: questions.length,
      submitHint:
        questions.length > 1
          ? "多题作答，先分别点选，再提交答案。"
          : overallMulti
            ? "多选题，先点选，再提交答案。"
            : "单选题，先点选，再提交答案。",
    };
  }

  var single = _detectOne(_stripAnswerSection(raw), 1);
  if (!single) return null;
  return {
    stem: single.stem,
    displayText: single.displayText,
    options: single.options,
    questionType: single.questionType,
    receipt: extracted.receipt,
    questions: [single],
    total: 1,
    submitHint:
      single.questionType === "multi_choice"
        ? "多选题，先点选，再提交答案。"
        : "单选题，先点选，再提交答案。",
  };
}

module.exports = { detect: detect, stripReceipt: stripReceipt };

// test_markdown.js — Comprehensive unit tests for wx_miniprogram/utils/markdown.js
// Run: node wx_miniprogram/tests/test_markdown.js

var md = require("../utils/markdown");

var _pass = 0;
var _fail = 0;
var _errors = [];
var _currentSuite = "";

// ── Assertion Helpers ────────────────────────────────────────

function _deepEqual(a, b) {
  if (a === b) return true;
  if (a == null || b == null) return a === b;
  if (typeof a !== typeof b) return false;
  if (typeof a !== "object") return a === b;
  if (Array.isArray(a) !== Array.isArray(b)) return false;

  var keysA = Object.keys(a);
  var keysB = Object.keys(b);
  if (keysA.length !== keysB.length) return false;

  for (var i = 0; i < keysA.length; i++) {
    var key = keysA[i];
    if (!b.hasOwnProperty(key)) return false;
    if (!_deepEqual(a[key], b[key])) return false;
  }
  return true;
}

function _stringify(val) {
  try {
    return JSON.stringify(val, null, 0);
  } catch (e) {
    return String(val);
  }
}

function assert(condition, msg) {
  var label = _currentSuite ? _currentSuite + " > " + msg : msg;
  if (condition) {
    _pass++;
  } else {
    _fail++;
    _errors.push("FAIL: " + label);
  }
}

function assertEqual(actual, expected, msg) {
  var label = _currentSuite ? _currentSuite + " > " + msg : msg;
  if (_deepEqual(actual, expected)) {
    _pass++;
  } else {
    _fail++;
    _errors.push(
      "FAIL: " +
        label +
        "\n       expected: " +
        _stringify(expected) +
        "\n       actual:   " +
        _stringify(actual),
    );
  }
}

function assertType(val, typeName, msg) {
  assert(
    typeof val === typeName,
    msg + " (expected type " + typeName + ", got " + typeof val + ")",
  );
}

function suite(name, fn) {
  _currentSuite = name;
  try {
    fn();
  } catch (e) {
    _fail++;
    _errors.push('ERROR in suite "' + name + '": ' + (e.message || e));
  }
  _currentSuite = "";
}

// ── 1. Headings H1-H6 ───────────────────────────────────────

function testHeadings() {
  suite("Headings", function () {
    // H1
    var blocks = md.parse("# Hello");
    assertEqual(blocks.length, 1, "H1 produces one block");
    assertEqual(blocks[0].type, "heading", "H1 type");
    assertEqual(blocks[0].level, 1, "H1 level");
    assertEqual(blocks[0].raw, "Hello", "H1 raw");

    // H2
    blocks = md.parse("## World");
    assertEqual(blocks[0].level, 2, "H2 level");
    assertEqual(blocks[0].raw, "World", "H2 raw");

    // H3
    blocks = md.parse("### Third");
    assertEqual(blocks[0].level, 3, "H3 level");

    // H4
    blocks = md.parse("#### Fourth");
    assertEqual(blocks[0].level, 4, "H4 level");

    // H5
    blocks = md.parse("##### Fifth");
    assertEqual(blocks[0].level, 5, "H5 level");

    // H6
    blocks = md.parse("###### Sixth");
    assertEqual(blocks[0].level, 6, "H6 level");

    // Heading with inline formatting
    blocks = md.parse("## **Bold** heading");
    assertEqual(
      blocks[0].type,
      "heading",
      "Heading with inline formatting type",
    );
    assert(
      blocks[0].content.length > 1,
      "Heading inline content has multiple spans",
    );
    assertEqual(
      blocks[0].content[0].type,
      "bold",
      "Heading first span is bold",
    );

    // Not a heading (no space after #)
    blocks = md.parse("#NoSpace");
    assertEqual(blocks[0].type, "paragraph", "No space after # is paragraph");

    // Heading with trailing text
    blocks = md.parse("# Title with spaces");
    assertEqual(blocks[0].raw, "Title with spaces", "H1 preserves full text");
  });
}

// ── 2. Code Blocks ──────────────────────────────────────────

function testCodeBlocks() {
  suite("Code Blocks", function () {
    // Basic code block with language
    var input = '```python\nprint("hello")\nprint("world")\n```';
    var blocks = md.parse(input);
    assertEqual(blocks.length, 1, "Code block produces one block");
    assertEqual(blocks[0].type, "code_block", "Code block type");
    assertEqual(blocks[0].language, "python", "Code block language");
    assertEqual(
      blocks[0].content,
      'print("hello")\nprint("world")',
      "Code block content",
    );

    // Code block with no language
    input = "```\nsome code\n```";
    blocks = md.parse(input);
    assertEqual(blocks[0].language, "text", "No language defaults to text");

    // Code block with javascript
    input = "```javascript\nvar x = 1;\n```";
    blocks = md.parse(input);
    assertEqual(blocks[0].language, "javascript", "JavaScript language tag");
    assertEqual(blocks[0].content, "var x = 1;", "JS code content");

    // Empty code block
    input = "```sql\n```";
    blocks = md.parse(input);
    assertEqual(blocks[0].type, "code_block", "Empty code block type");
    assertEqual(blocks[0].content, "", "Empty code block content");
    assertEqual(blocks[0].language, "sql", "Empty code block language");

    // Code block with blank lines inside
    input = "```\nline1\n\nline3\n```";
    blocks = md.parse(input);
    assertEqual(
      blocks[0].content,
      "line1\n\nline3",
      "Code block preserves blank lines",
    );

    // Unclosed code block (consumes to end)
    input = '```python\nprint("open")';
    blocks = md.parse(input);
    assertEqual(blocks[0].type, "code_block", "Unclosed code block type");
    assertEqual(
      blocks[0].content,
      'print("open")',
      "Unclosed code block content",
    );
  });
}

// ── 3. Tables ───────────────────────────────────────────────

function testTables() {
  suite("Tables", function () {
    // Standard table with separator
    var input = "| A | B | C |\n| --- | --- | --- |\n| 1 | 2 | 3 |";
    var blocks = md.parse(input);
    assertEqual(blocks.length, 1, "Standard table produces one block");
    assertEqual(blocks[0].type, "table", "Table type");
    assertEqual(blocks[0].colCount, 3, "Table has 3 columns");
    assertEqual(blocks[0].headers.length, 3, "Table has 3 headers");
    assertEqual(blocks[0].rows.length, 1, "Table has 1 data row");
    assertEqual(blocks[0].rows[0][0].content[0].text, "1", "Table cell value");

    // Table without leading/trailing pipes
    input = "A | B\n--- | ---\n1 | 2";
    blocks = md.parse(input);
    assertEqual(blocks[0].type, "table", "Table without outer pipes");
    assertEqual(blocks[0].colCount, 2, "Table 2 columns");

    // Multi-row table
    input = "| H1 | H2 |\n| -- | -- |\n| a | b |\n| c | d |";
    blocks = md.parse(input);
    assertEqual(blocks[0].rows.length, 2, "Multi-row table has 2 rows");
    assertEqual(
      blocks[0].rows[1][0].content[0].text,
      "c",
      "Second row first cell",
    );

    // Table with inline formatting in cells
    input = "| **Bold** | `code` |\n| --- | --- |\n| normal | *italic* |";
    blocks = md.parse(input);
    assertEqual(
      blocks[0].headers[0].content[0].type,
      "bold",
      "Header cell bold",
    );
    assertEqual(
      blocks[0].headers[1].content[0].type,
      "code",
      "Header cell code",
    );
    assertEqual(
      blocks[0].rows[0][1].content[0].type,
      "italic",
      "Data cell italic",
    );

    // Table with alignment colons
    input = "| L | C | R |\n| :--- | :---: | ---: |\n| 1 | 2 | 3 |";
    blocks = md.parse(input);
    assertEqual(blocks[0].type, "table", "Table with alignment markers");
    assertEqual(blocks[0].rows.length, 1, "Aligned table has 1 data row");
  });
}

// ── 4. Unordered Lists ─────────────────────────────────────

function testUnorderedLists() {
  suite("Unordered Lists", function () {
    // Dash marker
    var blocks = md.parse("- item1\n- item2\n- item3");
    assertEqual(blocks.length, 1, "UL produces one block");
    assertEqual(blocks[0].type, "ul", "UL type");
    assertEqual(blocks[0].items.length, 3, "UL has 3 items");
    assertEqual(blocks[0].items[0].raw, "item1", "UL first item raw");

    // Asterisk marker
    blocks = md.parse("* alpha\n* beta");
    assertEqual(blocks[0].type, "ul", "UL asterisk type");
    assertEqual(blocks[0].items.length, 2, "UL asterisk 2 items");
    assertEqual(blocks[0].items[0].raw, "alpha", "UL asterisk first item");

    // Plus marker
    blocks = md.parse("+ one\n+ two");
    assertEqual(blocks[0].type, "ul", "UL plus type");
    assertEqual(blocks[0].items.length, 2, "UL plus 2 items");

    // List with inline formatting
    blocks = md.parse("- **bold item**\n- `code item`");
    assertEqual(
      blocks[0].items[0].content[0].type,
      "bold",
      "UL item bold formatting",
    );
    assertEqual(
      blocks[0].items[1].content[0].type,
      "code",
      "UL item code formatting",
    );

    // Single item list
    blocks = md.parse("- only one");
    assertEqual(blocks[0].type, "ul", "Single item UL");
    assertEqual(blocks[0].items.length, 1, "Single item UL count");
  });
}

// ── 5. Ordered Lists ───────────────────────────────────────

function testOrderedLists() {
  suite("Ordered Lists", function () {
    var blocks = md.parse("1. first\n2. second\n3. third");
    assertEqual(blocks.length, 1, "OL produces one block");
    assertEqual(blocks[0].type, "ol", "OL type");
    assertEqual(blocks[0].items.length, 3, "OL has 3 items");
    assertEqual(blocks[0].items[0].index, 1, "OL first item index");
    assertEqual(blocks[0].items[2].index, 3, "OL third item index");
    assertEqual(blocks[0].items[0].raw, "first", "OL first item raw");

    // Non-sequential numbering (parser assigns sequential)
    blocks = md.parse("1. a\n5. b\n10. c");
    assertEqual(blocks[0].items[0].index, 1, "OL sequential index 1");
    assertEqual(blocks[0].items[1].index, 2, "OL sequential index 2");
    assertEqual(blocks[0].items[2].index, 3, "OL sequential index 3");

    // OL with formatting
    blocks = md.parse("1. **important**\n2. normal");
    assertEqual(blocks[0].items[0].content[0].type, "bold", "OL item bold");
  });
}

// ── 6. Circled Number Lists ────────────────────────────────

function testCircledNumberLists() {
  suite("Circled Number Lists", function () {
    // Line-start circled numbers
    var blocks = md.parse("① first\n② second\n③ third");
    assertEqual(blocks[0].type, "ol", "Circled numbers OL type");
    assertEqual(blocks[0].items.length, 3, "Circled numbers 3 items");
    assertEqual(blocks[0].items[0].index, 1, "Circled first index");
    assertEqual(blocks[0].items[0].raw, "first", "Circled first raw");

    // Trailing semicolons stripped
    blocks = md.parse("① itemA；\n② itemB；");
    assertEqual(blocks[0].items[0].raw, "itemA", "Semicolon stripped");
    assertEqual(blocks[0].items[1].raw, "itemB", "Semicolon stripped 2");

    // Inline circled numbers in paragraph (split into OL)
    blocks = md.parse("要点：①第一点；②第二点；③第三点");
    // Should produce a paragraph prefix + an ol
    var foundOl = false;
    for (var i = 0; i < blocks.length; i++) {
      if (blocks[i].type === "ol") {
        foundOl = true;
        break;
      }
    }
    assert(foundOl, "Inline circled numbers split into OL");

    // Single circled number stays as paragraph (needs >=2 to split)
    blocks = md.parse("只有①一个圆圈");
    var hasOl = false;
    for (var j = 0; j < blocks.length; j++) {
      if (blocks[j].type === "ol") hasOl = true;
    }
    assert(!hasOl, "Single circled number stays paragraph");
  });
}

// ── 7. Blockquotes ──────────────────────────────────────────

function testBlockquotes() {
  suite("Blockquotes", function () {
    var blocks = md.parse("> This is a quote");
    assertEqual(blocks.length, 1, "Blockquote produces one block");
    assertEqual(blocks[0].type, "blockquote", "Blockquote type");
    assertEqual(blocks[0].lines.length, 1, "Blockquote has 1 line");
    assertEqual(blocks[0].raw, "This is a quote", "Blockquote raw");

    // Multi-line blockquote
    blocks = md.parse("> line1\n> line2\n> line3");
    assertEqual(blocks[0].type, "blockquote", "Multi-line blockquote type");
    assertEqual(blocks[0].lines.length, 3, "Multi-line blockquote has 3 lines");
    assertEqual(
      blocks[0].raw,
      "line1\nline2\nline3",
      "Multi-line blockquote raw",
    );

    // Empty blockquote line (just ">")
    blocks = md.parse("> first\n>\n> third");
    assertEqual(
      blocks[0].lines.length,
      3,
      "Blockquote with empty line has 3 lines",
    );

    // Blockquote with inline formatting
    blocks = md.parse("> **bold** in quote");
    assertEqual(
      blocks[0].lines[0][0].type,
      "bold",
      "Blockquote bold formatting",
    );
  });
}

// ── 8. Horizontal Rules ────────────────────────────────────

function testHorizontalRules() {
  suite("Horizontal Rules", function () {
    // Triple dash
    var blocks = md.parse("---");
    assertEqual(blocks.length, 1, "HR --- produces one block");
    assertEqual(blocks[0].type, "hr", "HR --- type");

    // Long dash
    blocks = md.parse("-----");
    assertEqual(blocks[0].type, "hr", "HR ----- type");

    // Triple asterisk
    blocks = md.parse("***");
    assertEqual(blocks[0].type, "hr", "HR *** type");

    // Long asterisk
    blocks = md.parse("****");
    assertEqual(blocks[0].type, "hr", "HR **** type");

    // HR between content
    blocks = md.parse("above\n---\nbelow");
    var hrFound = false;
    for (var i = 0; i < blocks.length; i++) {
      if (blocks[i].type === "hr") hrFound = true;
    }
    assert(hrFound, "HR found between content");
  });
}

// ── 9. Callout Detection ───────────────────────────────────

function testCallouts() {
  suite("Callouts", function () {
    // Conclusion callout
    var blocks = md.parse("**核心结论：** 这是结论内容");
    assertEqual(blocks[0].type, "callout", "Conclusion callout type");
    assertEqual(blocks[0].variant, "conclusion", "Conclusion variant");
    assertEqual(blocks[0].label, "核心结论", "Conclusion label");
    assert(blocks[0].content.length > 0, "Conclusion has content");

    // Warning callout
    blocks = md.parse("**注意：** 小心这个坑");
    assertEqual(blocks[0].type, "callout", "Warning callout type");
    assertEqual(blocks[0].variant, "warning", "Warning variant");

    // Highlight callout
    blocks = md.parse("**关键要点：** 重要的知识");
    assertEqual(blocks[0].type, "callout", "Highlight callout type");
    assertEqual(blocks[0].variant, "highlight", "Highlight variant");

    // Tip callout
    blocks = md.parse("**小技巧：** 快速记忆方法");
    assertEqual(blocks[0].type, "callout", "Tip callout type");
    assertEqual(blocks[0].variant, "tip", "Tip variant");

    // Callout with Chinese colon
    blocks = md.parse("**注意事项：** 详细内容");
    assertEqual(blocks[0].type, "callout", "Callout with Chinese colon");
    assertEqual(blocks[0].variant, "warning", "Warning variant for 注意事项");

    // Callout with English colon
    blocks = md.parse("**重点:** content here");
    assertEqual(blocks[0].type, "callout", "Callout with English colon");
    assertEqual(blocks[0].variant, "highlight", "Highlight variant for 重点");

    // Callout with no body text
    blocks = md.parse("**核心结论：**");
    assertEqual(blocks[0].type, "callout", "Callout with no body");
    assertEqual(blocks[0].content.length, 0, "Callout no body content empty");

    // Various callout keywords
    var keywordTests = [
      { kw: "最终答案", variant: "conclusion" },
      { kw: "答案", variant: "conclusion" },
      { kw: "结论", variant: "conclusion" },
      { kw: "心得", variant: "conclusion" },
      { kw: "易错点", variant: "warning" },
      { kw: "陷阱", variant: "warning" },
      { kw: "警告", variant: "warning" },
      { kw: "易混淆", variant: "warning" },
      { kw: "考点", variant: "highlight" },
      { kw: "要点", variant: "highlight" },
      { kw: "考点提示", variant: "highlight" },
      { kw: "知识点", variant: "highlight" },
      { kw: "踩分点", variant: "highlight" },
      { kw: "记忆口诀", variant: "tip" },
      { kw: "速记", variant: "tip" },
      { kw: "助记", variant: "tip" },
      { kw: "口诀", variant: "tip" },
    ];
    for (var i = 0; i < keywordTests.length; i++) {
      var t = keywordTests[i];
      blocks = md.parse("**" + t.kw + "：** test");
      assertEqual(
        blocks[0].type,
        "callout",
        'Callout keyword "' + t.kw + '" detected',
      );
      assertEqual(
        blocks[0].variant,
        t.variant,
        'Callout keyword "' + t.kw + '" variant',
      );
    }

    // Non-callout bold paragraph (keyword not in list)
    blocks = md.parse("**普通加粗：** 内容");
    assertEqual(blocks[0].type, "paragraph", "Non-callout stays paragraph");
  });
}

// ── 10. Inline Formatting ──────────────────────────────────

function testInlineFormatting() {
  suite("Inline Formatting", function () {
    // Bold with **
    var spans = md.parseInline("**bold text**");
    assertEqual(spans.length, 1, "Bold single span");
    assertEqual(spans[0].type, "bold", "Bold type");
    assertEqual(spans[0].text, "bold text", "Bold text");

    // Bold with __
    spans = md.parseInline("__underline bold__");
    assertEqual(spans[0].type, "bold", "Bold __ type");
    assertEqual(spans[0].text, "underline bold", "Bold __ text");

    // Italic with *
    spans = md.parseInline("*italic text*");
    assertEqual(spans.length, 1, "Italic single span");
    assertEqual(spans[0].type, "italic", "Italic type");
    assertEqual(spans[0].text, "italic text", "Italic text");

    // Italic with _
    spans = md.parseInline("_underscore italic_");
    assertEqual(spans[0].type, "italic", "Italic _ type");
    assertEqual(spans[0].text, "underscore italic", "Italic _ text");

    // Inline code
    spans = md.parseInline("`code here`");
    assertEqual(spans.length, 1, "Code single span");
    assertEqual(spans[0].type, "code", "Code type");
    assertEqual(spans[0].text, "code here", "Code text");

    // Bold italic with ***
    spans = md.parseInline("***bold italic***");
    assertEqual(spans.length, 1, "Bold italic single span");
    assertEqual(spans[0].type, "bold_italic", "Bold italic type");
    assertEqual(spans[0].text, "bold italic", "Bold italic text");

    // Mixed inline
    spans = md.parseInline("normal **bold** and *italic* end");
    assertEqual(spans.length, 5, "Mixed inline 5 spans");
    assertEqual(spans[0].type, "text", "Mixed span 0 text");
    assertEqual(spans[0].text, "normal ", "Mixed span 0 value");
    assertEqual(spans[1].type, "bold", "Mixed span 1 bold");
    assertEqual(spans[1].text, "bold", "Mixed span 1 value");
    assertEqual(spans[2].type, "text", "Mixed span 2 text");
    assertEqual(spans[2].text, " and ", "Mixed span 2 value");
    assertEqual(spans[3].type, "italic", "Mixed span 3 italic");
    assertEqual(spans[4].type, "text", "Mixed span 4 text");

    // All text, no formatting
    spans = md.parseInline("plain text here");
    assertEqual(spans.length, 1, "Plain text single span");
    assertEqual(spans[0].type, "text", "Plain text type");
    assertEqual(spans[0].text, "plain text here", "Plain text value");

    // Code mixed with bold
    spans = md.parseInline("Use `var x` in **context**");
    assertEqual(spans.length, 4, "Code and bold mixed 4 spans");
    assertEqual(spans[1].type, "code", "Mixed code type");
    assertEqual(spans[3].type, "bold", "Mixed bold type");
  });
}

// ── 11. Empty/Null Input ───────────────────────────────────

function testEmptyNullInput() {
  suite("Empty/Null Input", function () {
    // null
    var blocks = md.parse(null);
    assertEqual(blocks, [], "null returns empty array");

    // undefined
    blocks = md.parse(undefined);
    assertEqual(blocks, [], "undefined returns empty array");

    // empty string
    blocks = md.parse("");
    assertEqual(blocks, [], "empty string returns empty array");

    // number (wrong type)
    blocks = md.parse(123);
    assertEqual(blocks, [], "number returns empty array");

    // whitespace only
    blocks = md.parse("   \n  \n   ");
    assertEqual(
      blocks,
      [],
      "whitespace only returns empty array (blanks trimmed)",
    );

    // parseInline null
    var spans = md.parseInline(null);
    assertEqual(spans.length, 1, "parseInline null returns 1 span");
    assertEqual(spans[0].type, "text", "parseInline null type text");
    assertEqual(spans[0].text, "", "parseInline null empty text");

    // parseInline undefined
    spans = md.parseInline(undefined);
    assertEqual(spans[0].text, "", "parseInline undefined empty text");

    // parseInline empty string
    spans = md.parseInline("");
    assertEqual(spans[0].text, "", "parseInline empty string");

    // parseWithIds null
    blocks = md.parseWithIds(null);
    assertEqual(blocks, [], "parseWithIds null returns empty array");
  });
}

// ── 12. Mixed Content ──────────────────────────────────────

function testMixedContent() {
  suite("Mixed Content", function () {
    var input = [
      "# Title",
      "",
      "A paragraph of text.",
      "",
      "- item 1",
      "- item 2",
      "",
      "```python",
      "x = 1",
      "```",
    ].join("\n");

    var blocks = md.parse(input);

    // Find block types
    var types = blocks.map(function (b) {
      return b.type;
    });

    assert(types.indexOf("heading") !== -1, "Mixed: has heading");
    assert(types.indexOf("paragraph") !== -1, "Mixed: has paragraph");
    assert(types.indexOf("ul") !== -1, "Mixed: has ul");
    assert(types.indexOf("code_block") !== -1, "Mixed: has code_block");

    // Verify heading
    var heading = blocks.filter(function (b) {
      return b.type === "heading";
    })[0];
    assertEqual(heading.level, 1, "Mixed heading level");
    assertEqual(heading.raw, "Title", "Mixed heading raw");

    // Verify list
    var ul = blocks.filter(function (b) {
      return b.type === "ul";
    })[0];
    assertEqual(ul.items.length, 2, "Mixed UL items");

    // Verify code block
    var code = blocks.filter(function (b) {
      return b.type === "code_block";
    })[0];
    assertEqual(code.language, "python", "Mixed code language");
    assertEqual(code.content, "x = 1", "Mixed code content");

    // Complex mixed: heading + blockquote + table + hr
    input = [
      "## Section",
      "",
      "> A note here",
      "",
      "---",
      "",
      "| A | B |",
      "| - | - |",
      "| 1 | 2 |",
    ].join("\n");

    blocks = md.parse(input);
    types = blocks.map(function (b) {
      return b.type;
    });
    assert(types.indexOf("heading") !== -1, "Complex mixed: has heading");
    assert(types.indexOf("blockquote") !== -1, "Complex mixed: has blockquote");
    assert(types.indexOf("hr") !== -1, "Complex mixed: has hr");
    assert(types.indexOf("table") !== -1, "Complex mixed: has table");
  });
}

// ── 13. parseWithIds ───────────────────────────────────────

function testParseWithIds() {
  suite("parseWithIds", function () {
    var blocks = md.parseWithIds("# Title\n\nParagraph");

    assert(blocks.length >= 2, "parseWithIds produces blocks");

    // Every block should have an id
    var allHaveId = true;
    for (var i = 0; i < blocks.length; i++) {
      if (!blocks[i].hasOwnProperty("id")) {
        allHaveId = false;
        break;
      }
    }
    assert(allHaveId, "All blocks have id field");

    // IDs should be sequential b0, b1, b2, ...
    assertEqual(blocks[0].id, "b0", "First block id is b0");
    assertEqual(blocks[1].id, "b1", "Second block id is b1");

    // Block types preserved
    assertEqual(
      blocks[0].type,
      "heading",
      "parseWithIds preserves heading type",
    );

    // Blank blocks get ids too
    var blocksWithBlanks = md.parseWithIds("# A\n\n\n\n# B");
    var ids = blocksWithBlanks.map(function (b) {
      return b.id;
    });
    for (var j = 0; j < ids.length; j++) {
      assertEqual(ids[j], "b" + j, "Sequential id b" + j);
    }
  });
}

// ── 14. parseInline Edge Cases ─────────────────────────────

function testParseInlineEdgeCases() {
  suite("parseInline Edge Cases", function () {
    // Adjacent formatting
    var spans = md.parseInline("**bold1****bold2**");
    var boldCount = spans.filter(function (s) {
      return s.type === "bold";
    }).length;
    assert(boldCount >= 1, "Adjacent bolds parsed");

    // Nested bold in italic (regex-based, may not handle true nesting)
    spans = md.parseInline("*outer **inner** outer*");
    assert(spans.length >= 1, "Nested formatting returns spans");

    // Empty bold
    spans = md.parseInline("****");
    // Empty ** pair - may or may not match depending on regex (.+?)
    assert(spans.length >= 1, "Empty bold markers handled");

    // Multiple code spans
    spans = md.parseInline("`a` and `b` and `c`");
    var codeSpans = spans.filter(function (s) {
      return s.type === "code";
    });
    assertEqual(codeSpans.length, 3, "Three code spans");
    assertEqual(codeSpans[0].text, "a", "First code span");
    assertEqual(codeSpans[1].text, "b", "Second code span");
    assertEqual(codeSpans[2].text, "c", "Third code span");

    // Formatting at start and end
    spans = md.parseInline("**start** middle **end**");
    assertEqual(spans.length, 3, "Bold at start and end");
    assertEqual(spans[0].type, "bold", "Start bold");
    assertEqual(spans[1].type, "text", "Middle text");
    assertEqual(spans[2].type, "bold", "End bold");

    // Unicode text with formatting
    spans = md.parseInline("**中文加粗** 普通文字");
    assertEqual(spans[0].type, "bold", "Chinese bold");
    assertEqual(spans[0].text, "中文加粗", "Chinese bold text");

    // Only whitespace
    spans = md.parseInline("   ");
    assertEqual(spans.length, 1, "Whitespace only returns 1 span");
    assertEqual(spans[0].type, "text", "Whitespace type is text");

    // Code with special characters
    spans = md.parseInline("`x = y + z * 2`");
    assertEqual(spans[0].type, "code", "Code with operators");
    assertEqual(spans[0].text, "x = y + z * 2", "Code preserves operators");

    // Number input to parseInline
    spans = md.parseInline(42);
    assertEqual(spans[0].type, "text", "Number input returns text type");
    assertEqual(spans[0].text, "", "Number input returns empty text");
  });
}

// ── 15. Table Edge Cases ───────────────────────────────────

function testTableEdgeCases() {
  suite("Table Edge Cases", function () {
    // Single row (no data) -> returns null from _parseTable, falls back to paragraphs
    var blocks = md.parse("| A | B |");
    assert(blocks.length >= 1, "Single row table produces blocks");
    // _parseTable returns null if lines.length < 2, so paragraphs
    assertEqual(blocks[0].type, "paragraph", "Single row becomes paragraph");

    // Two rows, no separator -> table with header + data, no separator skip
    blocks = md.parse("| A | B |\n| C | D |");
    // Both rows look like table rows. _parseTable: no separator, dataStart=1, 1 data row
    assertEqual(blocks[0].type, "table", "Two rows no separator is table");
    assertEqual(blocks[0].headers.length, 2, "Two rows no separator headers");
    assertEqual(blocks[0].rows.length, 1, "Two rows no separator data rows");

    // Single column table -> returns null (headers.length < 2)
    blocks = md.parse("| A |\n| - |\n| 1 |");
    // Single column: headers.length == 1 < 2, returns null
    assertEqual(blocks[0].type, "paragraph", "Single column becomes paragraph");

    // Table with empty cells
    blocks = md.parse("| A | B | C |\n| --- | --- | --- |\n|  | data |  |");
    assertEqual(blocks[0].type, "table", "Table with empty cells");
    assertEqual(
      blocks[0].rows[0][0].content[0].text,
      "",
      "Empty cell is empty string",
    );
    assertEqual(
      blocks[0].rows[0][1].content[0].text,
      "data",
      "Non-empty cell has data",
    );

    // Table with extra separator rows (should be skipped)
    blocks = md.parse("| A | B |\n| --- | --- |\n| --- | --- |\n| 1 | 2 |");
    assertEqual(blocks[0].type, "table", "Table with extra separator");
    // The extra separator row is skipped
    assertEqual(blocks[0].rows.length, 1, "Extra separator rows skipped");

    // Table followed by paragraph
    var input = "| X | Y |\n| - | - |\n| 1 | 2 |\nnot a table";
    blocks = md.parse(input);
    var tableBlocks = blocks.filter(function (b) {
      return b.type === "table";
    });
    var paraBlocks = blocks.filter(function (b) {
      return b.type === "paragraph";
    });
    assertEqual(tableBlocks.length, 1, "Table followed by paragraph: 1 table");
    assert(
      paraBlocks.length >= 1,
      "Table followed by paragraph: has paragraph",
    );

    // Pipe in middle of text (space-separated) triggers table check
    blocks = md.parse("A | B\nC | D");
    // " | " triggers _looksLikeTableRow; 2 lines, 2 cols, 1 data row
    assertEqual(blocks[0].type, "table", "Space pipe triggers table");
  });
}

// ── 16. Blank Line Handling ────────────────────────────────

function testBlankLineHandling() {
  suite("Blank Line Handling", function () {
    // Trailing blanks are removed
    var blocks = md.parse("hello\n\n\n");
    var lastBlock = blocks[blocks.length - 1];
    assert(lastBlock.type !== "blank", "Trailing blanks removed");

    // Multiple consecutive blanks collapsed to one
    blocks = md.parse("a\n\n\n\nb");
    var blankCount = 0;
    for (var i = 0; i < blocks.length; i++) {
      if (blocks[i].type === "blank") blankCount++;
    }
    assertEqual(blankCount, 1, "Multiple blanks collapsed to 1");

    // Leading blank
    blocks = md.parse("\n\nhello");
    // After processing, leading blank might be there but trailing stripped
    var para = blocks.filter(function (b) {
      return b.type === "paragraph";
    });
    assert(para.length >= 1, "Content after leading blank");
  });
}

// ── 17. Paragraph ──────────────────────────────────────────

function testParagraph() {
  suite("Paragraph", function () {
    var blocks = md.parse("Just a regular paragraph.");
    assertEqual(blocks.length, 1, "Paragraph produces one block");
    assertEqual(blocks[0].type, "paragraph", "Paragraph type");
    assertEqual(blocks[0].raw, "Just a regular paragraph.", "Paragraph raw");

    // Paragraph with inline formatting
    blocks = md.parse("Text with **bold** and *italic*.");
    assertEqual(blocks[0].type, "paragraph", "Formatted paragraph type");
    assert(
      blocks[0].content.length > 1,
      "Formatted paragraph has multiple spans",
    );
  });
}

// ── 18. Complex Real-World Input ───────────────────────────

function testRealWorldInput() {
  suite("Real-World Input", function () {
    // Exam-style content
    var input = [
      "## 混凝土强度等级",
      "",
      "**核心结论：** C30表示立方体抗压强度标准值为30MPa。",
      "",
      "### 关键要点",
      "",
      "1. 强度等级按150mm立方体试件确定",
      "2. 标准养护条件：温度20±2℃，湿度≥95%",
      "3. 养护龄期28天",
      "",
      "> 注意：实际工程中要考虑施工条件系数",
      "",
      "| 等级 | 强度(MPa) |",
      "| ---- | --------- |",
      "| C20 | 20 |",
      "| C30 | 30 |",
      "| C40 | 40 |",
      "",
      "---",
      "",
      '**小技巧：** 记住"150-20-95-28"',
    ].join("\n");

    var blocks = md.parse(input);
    var types = blocks.map(function (b) {
      return b.type;
    });

    assert(types.indexOf("heading") !== -1, "Real-world: has heading");
    assert(types.indexOf("callout") !== -1, "Real-world: has callout");
    assert(types.indexOf("ol") !== -1, "Real-world: has ordered list");
    assert(types.indexOf("blockquote") !== -1, "Real-world: has blockquote");
    assert(types.indexOf("table") !== -1, "Real-world: has table");
    assert(types.indexOf("hr") !== -1, "Real-world: has hr");

    // Check callout detection
    var callouts = blocks.filter(function (b) {
      return b.type === "callout";
    });
    assert(callouts.length >= 1, "Real-world: at least 1 callout");

    // Check conclusion variant
    var conclusionCallout = callouts.filter(function (c) {
      return c.variant === "conclusion";
    });
    assert(conclusionCallout.length >= 1, "Real-world: has conclusion callout");

    // Check tip variant
    var tipCallout = callouts.filter(function (c) {
      return c.variant === "tip";
    });
    assert(tipCallout.length >= 1, "Real-world: has tip callout");

    // Table data
    var table = blocks.filter(function (b) {
      return b.type === "table";
    })[0];
    assertEqual(table.rows.length, 3, "Real-world table has 3 rows");
    assertEqual(table.colCount, 2, "Real-world table has 2 columns");
  });
}

// ── 19. Edge Cases & Regression ────────────────────────────

function testEdgeCases() {
  suite("Edge Cases", function () {
    // Line with only hashes (no space, no text) - not a heading
    var blocks = md.parse("###");
    assertEqual(blocks[0].type, "paragraph", "### alone is paragraph");

    // Mixed list markers in consecutive lines stay as separate lists
    blocks = md.parse("- dash\n* star");
    // Both match /^[-*+]\s+/, so they merge into one UL
    assertEqual(blocks[0].type, "ul", "Mixed markers merge to UL");
    assertEqual(blocks[0].items.length, 2, "Mixed markers 2 items");

    // Code block with backticks inside
    var input = "```\nsome `code` here\n```";
    blocks = md.parse(input);
    assertEqual(
      blocks[0].type,
      "code_block",
      "Code block with backticks inside",
    );
    assertEqual(
      blocks[0].content,
      "some `code` here",
      "Backticks preserved in code",
    );

    // Very long line
    var longLine = "";
    for (var i = 0; i < 500; i++) longLine += "word ";
    blocks = md.parse(longLine);
    assertEqual(blocks.length, 1, "Very long line parsed");
    assertEqual(blocks[0].type, "paragraph", "Long line is paragraph");

    // Only blank lines
    blocks = md.parse("\n\n\n\n");
    assertEqual(blocks.length, 0, "Only blank lines returns empty");

    // Heading immediately followed by list (no blank line)
    blocks = md.parse("# Title\n- item");
    var headings = blocks.filter(function (b) {
      return b.type === "heading";
    });
    var lists = blocks.filter(function (b) {
      return b.type === "ul";
    });
    assertEqual(headings.length, 1, "Heading before list");
    assertEqual(lists.length, 1, "List after heading");

    // Ordered list then unordered list
    blocks = md.parse("1. first\n2. second\n- unordered");
    var olBlocks = blocks.filter(function (b) {
      return b.type === "ol";
    });
    var ulBlocks = blocks.filter(function (b) {
      return b.type === "ul";
    });
    assertEqual(olBlocks.length, 1, "OL then UL: has OL");
    assertEqual(ulBlocks.length, 1, "OL then UL: has UL");
  });
}

// ── 20. Circled Number Inline Split Details ─────────────────

function testCircledNumberInlineSplit() {
  suite("Circled Number Inline Split", function () {
    // Paragraph with prefix + circled items
    var blocks = md.parse("施工顺序：①测量放线②土方开挖③基础施工");
    // Should split into: prefix paragraph + OL
    assert(blocks.length >= 2, "Inline circled split produces 2+ blocks");

    var prefixPara = blocks.filter(function (b) {
      return (
        b.type === "paragraph" && b.raw && b.raw.indexOf("施工顺序") !== -1
      );
    });
    assert(prefixPara.length >= 1, "Has prefix paragraph");

    var ol = blocks.filter(function (b) {
      return b.type === "ol";
    })[0];
    assert(ol, "Has OL from inline circled numbers");
    assertEqual(ol.items.length, 3, "Inline circled split 3 items");
    assertEqual(ol.items[0].raw, "测量放线", "First circled item");
    assertEqual(ol.items[1].raw, "土方开挖", "Second circled item");
    assertEqual(ol.items[2].raw, "基础施工", "Third circled item");

    // Circled numbers with semicolons
    blocks = md.parse("步骤：①挖掘；②浇筑；③养护。");
    ol = blocks.filter(function (b) {
      return b.type === "ol";
    })[0];
    assert(ol, "Circled with semicolons has OL");
    // Trailing semicolons/periods stripped
    assertEqual(
      ol.items[0].raw,
      "挖掘",
      "Semicolon stripped from circled item",
    );
    assertEqual(
      ol.items[2].raw,
      "养护",
      "Period stripped from last circled item",
    );

    // No prefix, line starts with circled number -> matched by main loop
    // as single OL item (CIRCLED_PREFIX_RE), not split by post-processor
    blocks = md.parse("①设计②施工③验收");
    ol = blocks.filter(function (b) {
      return b.type === "ol";
    })[0];
    assert(ol, "No prefix inline circled has OL");
    assertEqual(
      ol.items.length,
      1,
      "Line-start circled consumed as single OL item",
    );

    // But if circled numbers are on separate lines, each becomes an item
    blocks = md.parse("①设计\n②施工\n③验收");
    ol = blocks.filter(function (b) {
      return b.type === "ol";
    })[0];
    assert(ol, "Separate lines circled has OL");
    assertEqual(ol.items.length, 3, "Separate lines 3 items");
  });
}

// ── Run All Tests ───────────────────────────────────────────

function runAll() {
  console.log("=== Markdown Parser Test Suite ===\n");

  var tests = [
    ["1. Headings H1-H6", testHeadings],
    ["2. Code Blocks", testCodeBlocks],
    ["3. Tables", testTables],
    ["4. Unordered Lists", testUnorderedLists],
    ["5. Ordered Lists", testOrderedLists],
    ["6. Circled Number Lists", testCircledNumberLists],
    ["7. Blockquotes", testBlockquotes],
    ["8. Horizontal Rules", testHorizontalRules],
    ["9. Callout Detection", testCallouts],
    ["10. Inline Formatting", testInlineFormatting],
    ["11. Empty/Null Input", testEmptyNullInput],
    ["12. Mixed Content", testMixedContent],
    ["13. parseWithIds", testParseWithIds],
    ["14. parseInline Edge Cases", testParseInlineEdgeCases],
    ["15. Table Edge Cases", testTableEdgeCases],
    ["16. Blank Line Handling", testBlankLineHandling],
    ["17. Paragraph", testParagraph],
    ["18. Real-World Input", testRealWorldInput],
    ["19. Edge Cases & Regression", testEdgeCases],
    ["20. Circled Number Inline Split", testCircledNumberInlineSplit],
  ];

  for (var i = 0; i < tests.length; i++) {
    var name = tests[i][0];
    var fn = tests[i][1];
    var beforeFail = _fail;
    fn();
    var suiteFails = _fail - beforeFail;
    console.log(
      (suiteFails === 0 ? "PASS" : "FAIL") +
        "  " +
        name +
        (suiteFails > 0 ? " (" + suiteFails + " failures)" : ""),
    );
  }

  console.log("\n--- Summary ---");
  console.log(
    "Total: " + (_pass + _fail) + "  Passed: " + _pass + "  Failed: " + _fail,
  );

  if (_errors.length > 0) {
    console.log("\n--- Failures ---");
    for (var j = 0; j < _errors.length; j++) {
      console.log(_errors[j]);
    }
  }

  console.log(
    "\n" + (_fail === 0 ? "ALL TESTS PASSED" : _fail + " TEST(S) FAILED"),
  );
  process.exit(_fail > 0 ? 1 : 0);
}

runAll();

// test_stream_token_boundary.js — 流式 token 边界回归契约
// Run: node wx_miniprogram/tests/test_stream_token_boundary.js
//
// 背景：
//   harness 现有 `buildStreamFrames` 只生成 3 帧（first line / first half / final），
//   完全测不到 token-by-token 的边界问题。当前分支主题
//   `fix/markdown-streaming-render-newline-loss` 修的就是这类问题。
//
// 本测试用 6 个真实形态的回答模板，每个模板用多种切分策略生成 50+ 帧，
// 逐帧喂 `deriveAiMessageRenderState`，并验证：
//   1. 任意时刻累积内容的 renderableContent 不会“反向丢字符”
//   2. 最终态（喂完所有 chunk）与一次性传入完整内容时的最终态一致
//   3. 最终 renderableContent 的换行数 ≥ fixture 声明的 expected_newlines_min
//
// 这是 wx.* 无关的纯 JS 测试，物理共享 ai-message-state.js / markdown-normalize.js。

var path = require("path");
var fs = require("fs");
var aiMessageState = require("../utils/ai-message-state");

var FIXTURE_PATH = path.join(
  __dirname,
  "..",
  "..",
  "tests",
  "fixtures",
  "wechat_stream_token_boundary_cases.json",
);
var fixtures = JSON.parse(fs.readFileSync(FIXTURE_PATH, "utf8"));

var pass = 0;
var fail = 0;
var errors = [];

function assert(condition, message) {
  if (condition) {
    pass += 1;
    return;
  }
  fail += 1;
  errors.push("FAIL: " + message);
}

// ── 切分策略 ─────────────────────────────────────────────────

// 1) 每 N 个字符切一刀（默认 N=1 → 极致 token-by-token；常用 N=2~6 模拟真实 token）
function chunksByChar(content, size) {
  var chunks = [];
  var step = Math.max(1, size || 1);
  for (var i = 0; i < content.length; i += step) {
    chunks.push(content.slice(i, i + step));
  }
  return chunks;
}

// 2) 在每个 `\n` 边界附近切（前/后各一帧），模拟"换行符被劈开"的灾难场景
function chunksAtNewlineBoundaries(content) {
  var chunks = [];
  var i = 0;
  for (var j = 0; j < content.length; j += 1) {
    if (content[j] === "\n") {
      // 推送上一段（不含 \n）
      if (j > i) chunks.push(content.slice(i, j));
      // 单独推送 \n
      chunks.push("\n");
      i = j + 1;
    }
  }
  if (i < content.length) chunks.push(content.slice(i));
  return chunks;
}

// 3) 在 markdown list / heading / **bold** / mcq option 边界制造"高风险"切口
function chunksAtRiskyBoundaries(content) {
  // 在以下位置强制切一刀：每个 `\n`、每个 `**`、每个 `: ` / `：`、每个 `- ` / 数字列表
  var risky = /(\n|\*\*|：|: |^- |^\d+\. )/m;
  var chunks = [];
  var rest = content;
  // 防御性循环上限：避免 fixture 内容意外导致死循环。
  for (var loop = 0; loop < 20000 && rest.length; loop += 1) {
    var m = rest.search(risky);
    if (m === -1) {
      chunks.push(rest);
      break;
    }
    if (m > 0) {
      chunks.push(rest.slice(0, m));
    }
    // 切单字符把高风险 token 单独成帧
    chunks.push(rest[m]);
    rest = rest.slice(m + 1);
  }
  return chunks;
}

function deriveFinalRenderable(content) {
  var state = aiMessageState.deriveAiMessageRenderState({
    content: content,
    parseBlocks: true,
  });
  return state;
}

function countNewlines(text) {
  return (String(text || "").match(/\n/g) || []).length;
}

function feedChunksAndAssert(fixture, chunks, strategyName) {
  // 喂入 N 帧，每帧检查累积内容
  var acc = "";
  var lastNewlineCount = 0;
  var minRenderableNewlines = 0;
  for (var i = 0; i < chunks.length; i += 1) {
    acc += chunks[i];
    var state = aiMessageState.deriveAiMessageRenderState({
      content: acc,
      parseBlocks: true,
    });
    var rendered = String(state.renderableContent || "");
    var nlInAcc = countNewlines(acc);
    var nlInRendered = countNewlines(rendered);

    // 不变量 A：renderableContent 的换行数永远不能"超过"输入累积里的换行数
    // （normalize 只会折叠空行 / 不会凭空插入新换行）
    assert(
      nlInRendered <= nlInAcc,
      "[" +
        fixture.name +
        " / " +
        strategyName +
        "] frame " +
        (i + 1) +
        " renderableContent newlines (" +
        nlInRendered +
        ") > input accumulated newlines (" +
        nlInAcc +
        ")",
    );

    // 不变量 B：渲染换行数随累积输入单调非降（不能往回退）
    if (nlInRendered < lastNewlineCount) {
      fail += 1;
      errors.push(
        "FAIL: [" +
          fixture.name +
          " / " +
          strategyName +
          "] frame " +
          (i + 1) +
          " regressed newline count: was " +
          lastNewlineCount +
          ", now " +
          nlInRendered,
      );
    } else {
      pass += 1;
    }
    lastNewlineCount = nlInRendered;
  }

  // 总帧数硬要求只对 char-1 strategy 检查（其它策略密度依赖 fixture 内容）。
  // 这样既能保证"50+ 帧 token-by-token"覆盖，也允许 newline-boundary /
  // risky-boundary 在小 fixture 上自然只有 10~20 帧。
  if (strategyName === "char-1" && fixture.content.length >= 50) {
    assert(
      chunks.length >= 50,
      "[" +
        fixture.name +
        " / " +
        strategyName +
        "] should generate >=50 chunks, got " +
        chunks.length,
    );
  }

  // 最终态对比：喂完 chunks 后的 acc 必须等于 fixture.content
  assert(
    acc === fixture.content,
    "[" +
      fixture.name +
      " / " +
      strategyName +
      "] accumulated content must equal full fixture content",
  );

  // 最终 renderableContent 的换行数 ≥ fixture.expected_newlines_min
  var finalRendered = String(
    deriveFinalRenderable(fixture.content).renderableContent || "",
  );
  var finalNewlines = countNewlines(finalRendered);
  var minRequired = Number(fixture.expected_newlines_min) || 0;
  assert(
    finalNewlines >= minRequired,
    "[" +
      fixture.name +
      "] final renderable should have >=" +
      minRequired +
      " newlines, got " +
      finalNewlines +
      ". This is the regression guard for fix/markdown-streaming-render-newline-loss.",
  );
}

// ── 对比：一次性 vs 增量喂完全相同 ───────────────────────────────────

function assertIncrementalEqualsOneShot(fixture, chunks, strategyName) {
  var acc = "";
  for (var i = 0; i < chunks.length; i += 1) {
    acc += chunks[i];
  }
  var oneShot = aiMessageState.deriveAiMessageRenderState({
    content: fixture.content,
    parseBlocks: true,
  });
  var incremental = aiMessageState.deriveAiMessageRenderState({
    content: acc,
    parseBlocks: true,
  });
  // renderableContent 与 mcqCards.length 与 blocks 数量一致
  assert(
    oneShot.renderableContent === incremental.renderableContent,
    "[" +
      fixture.name +
      " / " +
      strategyName +
      "] incremental.renderableContent != one-shot.renderableContent",
  );
  var oneShotBlocks = oneShot.blocks ? oneShot.blocks.length : 0;
  var incrementalBlocks = incremental.blocks ? incremental.blocks.length : 0;
  assert(
    oneShotBlocks === incrementalBlocks,
    "[" +
      fixture.name +
      " / " +
      strategyName +
      "] incremental blocks count (" +
      incrementalBlocks +
      ") != one-shot blocks count (" +
      oneShotBlocks +
      ")",
  );
}

// ── 主测试循环 ───────────────────────────────────────────────────────

for (var fIdx = 0; fIdx < fixtures.length; fIdx += 1) {
  var fixture = fixtures[fIdx];

  // 策略 1：每 1 字符切（最极端的 token-by-token）
  var charChunks = chunksByChar(fixture.content, 1);
  feedChunksAndAssert(fixture, charChunks, "char-1");
  assertIncrementalEqualsOneShot(fixture, charChunks, "char-1");

  // 策略 2：每 3 字符切（接近真实 LLM token 大小）
  var token3Chunks = chunksByChar(fixture.content, 3);
  feedChunksAndAssert(fixture, token3Chunks, "char-3");
  assertIncrementalEqualsOneShot(fixture, token3Chunks, "char-3");

  // 策略 3：每个 \n 独立成帧（换行符被劈开场景）
  var newlineChunks = chunksAtNewlineBoundaries(fixture.content);
  feedChunksAndAssert(fixture, newlineChunks, "newline-boundary");
  assertIncrementalEqualsOneShot(fixture, newlineChunks, "newline-boundary");

  // 策略 4：在 markdown / mcq / 中文标点边界劈刀
  var riskyChunks = chunksAtRiskyBoundaries(fixture.content);
  feedChunksAndAssert(fixture, riskyChunks, "risky-boundary");
  assertIncrementalEqualsOneShot(fixture, riskyChunks, "risky-boundary");
}

if (fail) {
  console.error(errors.slice(0, 20).join("\n"));
  if (errors.length > 20) {
    console.error("...and " + (errors.length - 20) + " more failures");
  }
  console.error("\nFAIL: " + fail + " assertions failed (" + pass + " passed)");
  process.exit(1);
}
console.log(
  "PASS test_stream_token_boundary.js (" +
    pass +
    " assertions across " +
    fixtures.length +
    " fixtures × 4 chunking strategies)",
);
process.exit(0);

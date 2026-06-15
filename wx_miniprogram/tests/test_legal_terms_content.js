// test_legal_terms_content.js — legal terms should cover core AI, account, privacy, and billing risks.
// Run: node wx_miniprogram/tests/test_legal_terms_content.js

var fs = require("fs");
var path = require("path");
var vm = require("vm");

function assert(condition, message) {
  if (!condition) {
    console.error("FAIL: " + message);
    process.exit(1);
  }
}

function loadTermsPage(filePath, filename) {
  var source = fs.readFileSync(filePath, "utf8");
  var pageDef = null;
  var sandbox = {
    console: console,
    require: function (request) {
      if (request === "../../utils/helpers") {
        return {
          getWindowInfo: function () {
            return { statusBarHeight: 20 };
          },
          isDark: function () {
            return true;
          },
        };
      }
      if (request === "../../utils/route") {
        return {
          profile: function () {
            return "/packageDeeptutor/pages/profile/profile";
          },
        };
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      navigateBack: function () {},
      reLaunch: function () {},
      switchTab: function () {},
    },
    Page: function (def) {
      pageDef = def;
    },
  };

  vm.runInNewContext(source, sandbox, { filename: filename });
  return pageDef && pageDef.data;
}

var wxData = loadTermsPage(
  path.join(__dirname, "../pages/legal/terms.js"),
  "wx_miniprogram/pages/legal/terms.js",
);
var packageData = loadTermsPage(
  path.join(
    __dirname,
    "../../yousenwebview/packageDeeptutor/pages/legal/terms.js",
  ),
  "yousenwebview/packageDeeptutor/pages/legal/terms.js",
);
var wxWxml = fs.readFileSync(
  path.join(__dirname, "../pages/legal/terms.wxml"),
  "utf8",
);
var packageWxml = fs.readFileSync(
  path.join(
    __dirname,
    "../../yousenwebview/packageDeeptutor/pages/legal/terms.wxml",
  ),
  "utf8",
);

assert(wxData, "wx terms page should register data");
assert(packageData, "package terms page should register data");
assert(wxData.updatedAt === "2026-06-15", "wx terms updated date should be current");
assert(
  packageData.updatedAt === wxData.updatedAt,
  "package terms updated date should match wx terms",
);
assert(
  JSON.stringify(packageData.sections) === JSON.stringify(wxData.sections),
  "package terms content should match wx terms content",
);

var expectedTitles = [
  "1. 服务范围与定位",
  "2. 账号、资格与未成年人",
  "3. 合规使用要求",
  "4. AI 内容与学习建议边界",
  "5. 题目、资料与第三方来源",
  "6. 用户内容与知识产权",
  "7. 数据与隐私",
  "8. 会员、积分、付费与退款",
  "9. 服务变更、中断与处置",
  "10. 责任限制、投诉与争议",
];

assert(
  wxData.sections.length === expectedTitles.length,
  "terms should keep the expected section count",
);
expectedTitles.forEach(function (title, index) {
  assert(
    wxData.sections[index].title === title,
    "terms section " + index + " should be " + title,
  );
  assert(
    wxData.sections[index].paragraphs.length === 2,
    "terms section " + title + " should keep two readable paragraphs",
  );
});

var allText = wxData.sections
  .map(function (section) {
    return section.title + "\n" + section.paragraphs.join("\n");
  })
  .join("\n");
[
  "工程安全决策依据",
  "未成年人",
  "自动化异常请求",
  "AI 生成内容具有概率性",
  "第三方知识产权",
  "必要范围内处理相关内容",
  "撤回授权",
  "退款规则",
  "终止账号服务",
  "消费者权益",
].forEach(function (keyword) {
  assert(allText.indexOf(keyword) >= 0, "terms should include " + keyword);
});

assert(
  wxWxml.indexOf("无法准确理解相关内容") >= 0,
  "wx footer should tell users to stop if they do not understand the terms",
);
assert(
  packageWxml.indexOf("无法准确理解相关内容") >= 0,
  "package footer should tell users to stop if they do not understand the terms",
);

console.log("PASS test_legal_terms_content.js");

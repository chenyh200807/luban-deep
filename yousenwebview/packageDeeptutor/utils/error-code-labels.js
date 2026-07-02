// 错因码 → 中文展示名（owner 2026-07-02 拍板方案 A：直接用 registry 名，10 类标签作废）。
// 本文件是 deeptutor/contracts/error_codes.py ERROR_CODE_REGISTRY 的只读镜像——
// 唯一权威在后端 registry；CI 测试 test_error_code_labels_mirror.py 钉死两边一致（漂移即红）。
// 前端禁止在此之外自造/改写错因名（禁第二套错因分类）。
var ERROR_CODE_LABELS = {
  E01: "知识点缺失",
  E02: "采分点遗漏",
  E03: "关键词缺失",
  E04: "口号化表达",
  E05: "审题错误",
  E06: "程序顺序错误",
  E07: "概念混淆",
  E08: "背景信息提取失败",
  E09: "计算错误",
  E10: "规范适用错误",
  E11: "迁移失败",
  E12: "表达冗余",
  M01: "知识点不熟",
  M02: "关键词误读",
  M03: "概念混淆",
  M04: "选项陷阱",
  M05: "审题方向错误",
  M06: "多选漏选",
  M07: "多选错选",
  M08: "规范数字混淆",
  M09: "题干条件提取不完整",
  M10: "用常识替代规范判断",
};

function labelFor(code) {
  return ERROR_CODE_LABELS[String(code || "").trim()] || String(code || "");
}

module.exports = { ERROR_CODE_LABELS: ERROR_CODE_LABELS, labelFor: labelFor };

// pack-short-names.js — 学习/路线卡显示层短名 + 副标题(纯前端展示 curation)
//
// 单一权威边界:
// - 这是**显示层**短名/副标题,不是签发内容、不是后端权威、不参与判分/掌握。
// - 站卡副标题真源 = 后端签发考点卡首卡 front(lessons[].summary);本文件的
//   SUBTITLE_MAP 只是**后端缺 summary 时的兜底**,绝不覆盖后端值。
// - 短名 SHORT_MAP 只是把长 title 显示成清爽 3-4 字;title 全名不变(下一站卡/详情用)。
//   未登记简称的站 → 回退调用方给的 fallback(旧 6 字截断),不造词。
//
// 说明:本文件为显示层 curation,原快照未纳入版本管理(untracked)而丢失,现按
// 学习页 UI 定稿 + 测试断言重建;新增站点在此登记简称即可,零后端依赖。

// pack_id(大写) -> 显示短名(3-4 字,竖排书法卡清爽)
var SHORT_MAP = {
  A01: "检验批",
  A02: "隐蔽验收",
  A03: "四级验收",
  B02: "基坑支护",
  B08: "基坑支护",
  C01: "混凝土",
  C02: "钢筋",
  D11: "砌体",
  D13: "抹灰",
  F02: "卷材防水",
  F03: "地下防水",
  F04: "屋面构造",
  F05: "渗漏治理",
  F16: "屋面防水",
  N01: "关键线路",
  N02: "网络计划",
  Q01: "质量事故",
  Q02: "质量验收",
  Q03: "质量通病",
  S02: "工期索赔",
  S05: "临时用电",
  S06: "施工安全",
  S07: "安全事故",
  J01: "见证取样",
};

// pack_id(大写) -> 副标题兜底(仅当后端 lessons[].summary 缺失时用;后端值优先)
var SUBTITLE_MAP = {
  A01: "四级验收层级",
  A02: "复验见证取样",
  B02: "支护选型降水",
  B08: "支护选型降水",
  F02: "顺水搭接方向",
  F05: "渗漏诊断处置",
  F16: "起鼓割补工序",
  N01: "关键工作判定",
  S05: "临时用电三大系统",
  S07: "事故等级上报",
};

function _up(id) {
  return String(id == null ? "" : id).trim().toUpperCase();
}

// 显示短名:登记的用简称;未登记回退调用方 fallback(旧截断),不造词。
function shortName(packId, fallback) {
  var up = _up(packId);
  return SHORT_MAP[up] || String(fallback == null ? "" : fallback);
}

// 副标题:后端 summary 优先(真源),否则前端兜底 map,都无则真留空(fail-closed,不造词)。
function subtitle(packId, backendSummary) {
  var s = String(backendSummary == null ? "" : backendSummary).trim();
  if (s) return s;
  return SUBTITLE_MAP[_up(packId)] || "";
}

module.exports = {
  shortName: shortName,
  subtitle: subtitle,
  SHORT_MAP: SHORT_MAP,
  SUBTITLE_MAP: SUBTITLE_MAP,
};

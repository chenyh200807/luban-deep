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
  B02: "基坑支护",
  C01: "施工缝",
  C02: "进度计量",
  C04: "模板拆除",
  C05: "钢筋连接",
  C06: "砌体构造",
  C07: "钢构连接",
  D11: "抹灰质量",
  D12: "饰面空鼓",
  D13: "幕墙封堵",
  D14: "装饰综合",
  E05: "挣值分析",
  F02: "卷材防水",
  F03: "防水层次",
  F04: "防水节点",
  F05: "渗漏治理",
  F16: "起鼓割补",
  G01: "开挖降水",
  G02: "土方回填",
  G03: "桩基质量",
  G04: "地基验槽",
  J01: "专家论证",
  K01: "索赔计算",
  N01: "关键线路",
  N02: "工期优化",
  N03: "流水施工",
  Q01: "养护裂缝",
  Q02: "大体积温控",
  Q03: "通病防治",
  R01: "消防动火",
  S01: "支架验收",
  S02: "起重吊装",
  S05: "临时用电",
  S06: "高处防护",
  S07: "事故上报",
  X01: "平面布置",
  X02: "临设堆场",
  X03: "绿色施工",
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

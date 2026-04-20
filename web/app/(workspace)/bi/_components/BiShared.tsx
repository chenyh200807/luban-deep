export const BI_PRIMARY_TABS = [
  {
    key: "overview",
    label: "Overview",
    summary: "当前先保留现有全量内容，作为 Command Deck 的总览入口。",
  },
  {
    key: "quality",
    label: "Quality",
    summary: "质量主线会在后续任务中拆成独立分区与指标面板。",
  },
  {
    key: "member-ops",
    label: "Member Ops",
    summary: "会员运营分区会在后续任务中独立收口，不在本次 shell 内展开。",
  },
  {
    key: "tutorbot",
    label: "TutorBot",
    summary: "TutorBot 主线会在后续任务中拆成独立视图与操作面板。",
  },
] as const;

export type BiPrimaryTab = (typeof BI_PRIMARY_TABS)[number]["key"];

export function normalizeBiPrimaryTab(value: string | null | undefined): BiPrimaryTab {
  if (value === "quality" || value === "member-ops" || value === "tutorbot") {
    return value;
  }
  return "overview";
}

export function getBiPrimaryTabHref(tab: BiPrimaryTab) {
  return tab === "overview" ? "/bi" : `/bi?tab=${tab}`;
}

/* eslint-disable i18n/no-literal-ui-text */
"use client";

import type {
  BiBossWorkbench,
  BiMemberData,
  BiRetentionData,
  BiTrendData,
  BiWorkbenchData,
  BiWorkbenchModuleIssues,
} from "@/lib/bi-api";
import { BiBossHomeTab } from "./BiBossHomeTab";

type BiOverviewTabProps = {
  loading: boolean;
  days: 7 | 30 | 90;
  boss: BiBossWorkbench;
  overview?: BiWorkbenchData["overview"];
  trend: BiTrendData;
  retention: BiRetentionData;
  members: BiMemberData;
  moduleIssues: BiWorkbenchModuleIssues;
  onNavigateFromBossQueue: (source?: BiBossWorkbench["actionQueue"][number]["source"]) => void;
  onOpenLearnerDetail: (sample: { user_id: string; display_name: string }) => void;
};

export function BiOverviewTab({
  loading,
  days,
  boss,
  overview,
  trend,
  retention,
  members,
  moduleIssues,
  onNavigateFromBossQueue,
  onOpenLearnerDetail,
}: BiOverviewTabProps) {
  return (
    <BiBossHomeTab
      loading={loading}
      days={days}
      boss={boss}
      overview={overview}
      trend={trend}
      retention={retention}
      members={members}
      moduleIssues={moduleIssues}
      onNavigateFromBossQueue={onNavigateFromBossQueue}
      onOpenLearnerDetail={onOpenLearnerDetail}
    />
  );
}

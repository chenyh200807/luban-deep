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
import { BiBossActionQueue } from "./BiBossActionQueue";
import { BiBossKpis } from "./BiBossKpis";
import { BiBossMemberWatchlist } from "./BiBossMemberWatchlist";
import { BiBossSnapshotGrid } from "./BiBossSnapshotGrid";
import { BiBossTrendPanel } from "./BiBossTrendPanel";

type BiBossHomeTabProps = {
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

export function BiBossHomeTab({
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
}: BiBossHomeTabProps) {
  return (
    <div className="space-y-6">
      <BiBossKpis
        loading={loading}
        kpis={boss.kpis}
        issue={moduleIssues.overview || moduleIssues.members || moduleIssues.cost}
      />

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.28fr)_minmax(340px,0.72fr)]">
        <BiBossTrendPanel
          loading={loading}
          days={days}
          trend={trend}
          overview={overview}
          issue={moduleIssues.trend}
        />
        <BiBossActionQueue
          heroIssue={boss.heroIssue}
          actionQueue={boss.actionQueue}
          onNavigate={onNavigateFromBossQueue}
        />
      </section>

      <BiBossSnapshotGrid
        overview={overview}
        retention={retention}
        members={members}
        overviewIssue={moduleIssues.overview}
        retentionIssue={moduleIssues.retention}
        memberIssue={moduleIssues.members}
      />

      <BiBossMemberWatchlist members={members} onOpenLearnerDetail={onOpenLearnerDetail} />
    </div>
  );
}

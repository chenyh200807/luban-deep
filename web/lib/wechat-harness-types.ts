export type HarnessSurface =
  | "chat"
  | "practice"
  | "billing"
  | "profile"
  | "system";

export type HarnessMode = "stream" | "final" | "history";

export interface HarnessRenderState {
  schemaVersion: number;
  renderableContent: string;
  blocks: Array<Record<string, unknown>> | null;
  mcqCards: Array<Record<string, unknown>> | null;
  mcqHint: string;
  mcqReceipt: string;
  mcqInteractiveReady: boolean;
  originalContent: string;
  originalCollapsed: boolean;
  visibleBlocks: Array<Record<string, unknown>>;
  plainTextFallback: string;
  hasStructuredContent: boolean;
  streamPhase: "idle" | "streaming" | "complete";
}

export interface HarnessStreamFrame {
  id: string;
  label: string;
  state: HarnessRenderState;
}

export interface HarnessExpectation {
  blockTypes: string[];
  visibleBlockTypes: string[];
  mcqCount: number;
  historyParity: boolean;
}

export interface WechatHarnessCase {
  id: string;
  name: string;
  title: string;
  surface: HarnessSurface;
  sourcePath: string;
  description: string;
  content: string;
  tags: string[];
  manualFocus: string[];
  expectations: HarnessExpectation;
  streamFrames: HarnessStreamFrame[];
  finalState: HarnessRenderState;
  historyState: HarnessRenderState;
  parityWarnings: string[];
}


import React from "react";
import {
  AbsoluteFill,
  Easing,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

type Action = {
  kind: string;
  target?: string;
  verb?: string;
  start: number;
  end: number;
};

type PrimitiveStepPlan = {
  id: string;
  kind: string;
  domain_object?: string;
  domain_objects?: string[];
  start?: number;
  end?: number;
};

type VisualNode = {
  id: string;
  kind: string;
  tone?: string;
  x?: number;
  y?: number;
  w?: number;
  h?: number;
  x1?: number;
  x2?: number;
  base_y?: number;
  text?: string;
  subtext?: string;
  labels?: string[];
  badges?: string[];
  value?: number;
  mode?: string;
  visual_signature?: string;
  second_device?: string;
  rule_title?: string;
  rule_main?: string;
  rule_sub?: string;
  axes?: Array<{
    name?: string;
    bands?: string[];
    probe?: string;
    hit_index?: number;
  }>;
  result?: { label?: string };
  primitive_steps?: PrimitiveStepPlan[];
};

type VisualScene = {
  board?: string;
  nodes?: VisualNode[];
};

type Scene = {
  id: string;
  label: string;
  start_sec: number;
  end_sec: number;
  focus: string;
  keycard: string;
  caption?: string;
  coach: string;
  camera: { verb: string; target: string; duration_sec: number };
  visible_nodes: string[];
  actions?: Action[];
};

type TimingSegment = {
  startSec: number;
  durSec: number;
  text: string;
  speaker?: string;
};

export type AnimationIr = {
  card_id: string;
  display?: {
    kicker?: string;
    title?: string;
  };
  main_exam_action: string;
  render_contract: {
    max_visible_nodes: number;
    caption_mode?: string;
    max_caption_chars?: number;
    layout_mode?: string;
  };
  scenes: Scene[];
  visual_library: Record<string, VisualScene>;
};

type AnimationTiming = {
  totalSec?: number;
  segments?: TimingSegment[];
};

export type AnimationIrRendererProps = {
  ir: AnimationIr;
  timing?: AnimationTiming;
  title?: string;
  kicker?: string;
};

const colors = {
  bg: "#0d1723",
  panel: "#fffdf7",
  grid: "#f0e7d8",
  line: "#eadfcb",
  text: "#172033",
  muted: "#637083",
  teal: "#10b981",
  blue: "#60a5fa",
  amber: "#ffd27f",
  red: "#ef4444",
};

const tones = {
  danger: { fill: "#fff7ed", stroke: "#f97316", text: "#9a3412" },
  success: { fill: "#ecfdf5", stroke: "#10b981", text: "#047857" },
  blue: { fill: "#eff6ff", stroke: "#60a5fa", text: "#1d4ed8" },
  amber: { fill: "#fffbeb", stroke: "#f59e0b", text: "#b45309" },
  neutral: { fill: "#f8fafc", stroke: "#cbd5e1", text: "#334155" },
};

const clamp = (value: number) => Math.max(0, Math.min(1, value));
const ease = (value: number) =>
  interpolate(clamp(value), [0, 1], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

const toneOf = (tone?: string) =>
  tones[(tone || "neutral") as keyof typeof tones] || tones.neutral;

const activeSceneAt = (scenes: Scene[], second: number) =>
  scenes.find((scene) => second >= scene.start_sec && second < scene.end_sec) ||
  scenes[scenes.length - 1];

const activeSegmentAt = (
  segments: TimingSegment[] | undefined,
  second: number,
) =>
  (segments || []).find(
    (segment) =>
      second >= segment.startSec - 0.12 &&
      second < segment.startSec + segment.durSec + 0.12,
  );

const nodeReveal = (
  node: VisualNode,
  scene: Scene,
  progress: number,
  index: number,
) => {
  const reveal = (scene.actions || []).find(
    (action) => action.kind === "reveal" && action.target === node.id,
  ) || {
    start: 0.04 + index * 0.14,
    end: 0.22 + index * 0.14,
  };
  return ease(
    (progress - reveal.start) / Math.max(0.04, reveal.end - reveal.start),
  );
};

const nodeHighlighted = (node: VisualNode, scene: Scene, progress: number) => {
  if (node.id === scene.focus || node.id.includes(scene.focus)) return true;
  return (scene.actions || []).some(
    (action) =>
      action.kind === "highlight" &&
      action.target &&
      (action.target === node.id || node.id.includes(action.target)) &&
      progress >= action.start &&
      progress <= action.end,
  );
};

const TextLines: React.FC<{
  text?: string;
  x: number;
  y: number;
  size?: number;
  fill?: string;
  weight?: number;
  anchor?: "start" | "middle" | "end";
}> = ({
  text,
  x,
  y,
  size = 15,
  fill = colors.text,
  weight = 900,
  anchor = "middle",
}) => {
  const lines = String(text || "").split("\n");
  return (
    <>
      {lines.map((line, index) => (
        <text
          key={`${line}-${index}`}
          x={x}
          y={y + index * (size + 14)}
          textAnchor={anchor}
          fontSize={size}
          fontWeight={weight}
          fill={fill}
        >
          {line}
        </text>
      ))}
    </>
  );
};

const fitFontSize = (
  text: string | undefined,
  width: number,
  base: number,
  minimum = 10,
) => {
  const longest = Math.max(
    0,
    ...String(text || "")
      .split("\n")
      .map((line) => line.length),
  );
  if (!longest) return base;
  const estimated = Math.floor(
    (Math.max(width - 20, 24) / Math.max(longest, 1)) * 1.08,
  );
  return Math.max(minimum, Math.min(base, estimated));
};

const labelsWithDefaults = (
  node: VisualNode,
  defaults: string[],
  limit: number,
) =>
  [
    ...(node.labels || []).filter((label): label is string => label != null),
    ...defaults,
  ].slice(0, limit);

const visualSignature = (node: VisualNode) =>
  String(
    node.visual_signature || `${node.kind || "node"}:${node.mode || "default"}`,
  );

const compactCaption = (text: string | undefined, maxChars: number) => {
  const normalized = String(text || "")
    .replace(/\s+/g, " ")
    .trim();
  if (normalized.length <= maxChars) return normalized;
  return `${normalized.slice(0, Math.max(1, maxChars - 1))}…`;
};

const LabelBadge: React.FC<{
  text?: string;
  cx: number;
  cy: number;
  tone: ReturnType<typeof toneOf>;
  width?: number;
  size?: number;
}> = ({ text, cx, cy, tone, width, size = 12 }) => {
  const label = String(text || "");
  if (!label) return null;
  const badgeW =
    width ?? Math.max(54, Math.min(116, label.length * size * 0.92 + 22));
  const badgeH = size + 13;
  return (
    <>
      <rect
        x={cx - badgeW / 2}
        y={cy - badgeH / 2}
        width={badgeW}
        height={badgeH}
        rx={8}
        fill={tone.fill}
        stroke={tone.stroke}
        strokeWidth={1.6}
      />
      <TextLines
        text={label}
        x={cx}
        y={cy + size * 0.34}
        size={size}
        fill={tone.text}
      />
    </>
  );
};

const PrimitiveStepContext = React.createContext<{
  nodeId: string;
  steps: PrimitiveStepPlan[];
  actions: Action[];
} | null>(null);

const ANIMATED_PRIMITIVE_KINDS = new Set([
  "roof_section",
  "scaffold_frame",
  "process_flow",
  "layer_stack",
  "pit_threshold_board",
  "network_graph",
  "formula_chain",
  "power_distribution_tree",
  "decision_tree",
  "contrast_pair",
  "inspection_blueprint_board",
  "lifting_threshold_board",
  "grade_threshold_board",
  "answer_scan",
]);

const PrimitiveStep: React.FC<{
  index: number;
  progress: number;
  trace?: boolean;
  stepId?: string;
  children: React.ReactNode;
}> = ({ index, progress, trace = false, stepId, children }) => {
  const context = React.useContext(PrimitiveStepContext);
  const step = stepId
    ? context?.steps?.find((candidate) => candidate.id === stepId)
    : context?.steps?.[index];
  const target =
    context && step?.id ? `${context.nodeId}.${step.id}` : undefined;
  const stepAction = target
    ? context?.actions.find(
        (action) =>
          action.kind === "primitive_step" && action.target === target,
      )
    : undefined;
  const p = stepAction
    ? ease(
        (progress - stepAction.start) /
          Math.max(0.03, stepAction.end - stepAction.start),
      )
    : ease((progress - index * 0.16) / 0.24);
  const domainObject = step?.domain_object || step?.domain_objects?.join(",");
  return (
    <g
      data-primitive-step={index}
      data-primitive-step-id={step?.id}
      data-step-kind={step?.kind}
      data-domain-object={domainObject}
      data-step-target={target}
      data-step-consumed={stepAction ? "1" : step ? "fallback" : undefined}
      style={{
        opacity: p,
        transform: trace
          ? `scaleX(${p})`
          : `translateY(${interpolate(p, [0, 1], [7, 0])}px) scale(${interpolate(p, [0, 1], [0.97, 1])})`,
        transformBox: "fill-box",
        transformOrigin: trace ? "left center" : "center",
      }}
    >
      {children}
    </g>
  );
};

const Primitive: React.FC<{
  node: VisualNode;
  opacity: number;
  highlighted: boolean;
}> = ({ node, opacity, highlighted }) => {
  const t = toneOf(node.tone);
  const x = node.x ?? 0;
  const y = node.y ?? 0;
  const w = node.w ?? 180;
  const h =
    node.h ??
    (node.kind === "pill"
      ? 54
      : node.kind === "dialogue_box"
        ? 42
        : node.kind === "answer_box"
          ? 38
          : 42);
  const transform = `translate(0 ${interpolate(opacity, [0, 1], [10, 0])}) scale(${interpolate(opacity, [0, 1], [0.97, highlighted ? 1.025 : 1])})`;
  const filter = highlighted
    ? "drop-shadow(0px 0px 8px rgba(255, 210, 127, 0.7))"
    : undefined;
  const hasInternalSteps = ANIMATED_PRIMITIVE_KINDS.has(node.kind);
  const common = {
    opacity: hasInternalSteps ? (opacity > 0.01 ? 1 : 0) : opacity,
    transform,
    transformBox: "fill-box" as const,
    transformOrigin: "center",
    filter,
  };

  if (node.kind === "pill") {
    const titleSize = fitFontSize(node.text, w, 16, 11);
    const subSize = fitFontSize(node.subtext, w, 12, 10);
    const titleY = y + (node.subtext ? h * 0.42 : h / 2 + titleSize * 0.36);
    return (
      <g style={common}>
        <rect
          x={x}
          y={y}
          width={w}
          height={h}
          rx={14}
          fill={t.fill}
          stroke={t.stroke}
          strokeWidth={3}
        />
        <TextLines
          text={node.text}
          x={x + w / 2}
          y={titleY}
          size={titleSize}
          fill={t.text}
        />
        {node.subtext ? (
          <TextLines
            text={node.subtext}
            x={x + w / 2}
            y={y + h * 0.76}
            size={subSize}
            fill={t.text}
            weight={850}
          />
        ) : null}
      </g>
    );
  }
  if (node.kind === "roof_section") {
    const baseH = node.h ?? 58;
    return (
      <g style={common}>
        <PrimitiveStep index={0} progress={opacity}>
          <rect
            x={x}
            y={y + 28}
            width={w}
            height={baseH}
            rx={4}
            fill="#87919d"
          />
          <text
            x={x + 12}
            y={y + 45}
            fontSize={10}
            fontWeight={900}
            fill="#f8fafc"
          >
            基层
          </text>
        </PrimitiveStep>
        <PrimitiveStep index={1} progress={opacity}>
          <rect x={x} y={y + 12} width={w} height={16} fill="#c5b78f" />
        </PrimitiveStep>
        <PrimitiveStep index={2} progress={opacity}>
          <rect x={x} y={y} width={w} height={12} fill="#34465b" />
          <text
            x={x + 12}
            y={y + 9}
            fontSize={10}
            fontWeight={900}
            fill="#e2edf7"
          >
            卷材
          </text>
        </PrimitiveStep>
      </g>
    );
  }
  if (node.kind === "scaffold_frame") {
    const labels = labelsWithDefaults(
      node,
      ["荷载先落架体", "立杆传到底座", "扫地杆锁底部", "连墙件防侧倒"],
      4,
    );
    const postX = [x + w * 0.18, x + w * 0.38, x + w * 0.62, x + w * 0.82];
    const topY = y + h * 0.22;
    const midY = y + h * 0.48;
    const lowY = y + h * 0.72;
    const baseY = y + h * 0.88;
    const bracePath = `M${postX[0]} ${baseY} L${postX[1]} ${topY} M${postX[1]} ${baseY} L${postX[2]} ${topY} M${postX[2]} ${baseY} L${postX[3]} ${topY}`;
    return (
      <g style={common}>
        <PrimitiveStep index={0} progress={opacity}>
          <TextLines
            text={node.text || "临时支撑系统"}
            x={x + w / 2}
            y={y + 10}
            size={16}
            fill="#176b7a"
          />
        </PrimitiveStep>
        <PrimitiveStep index={1} progress={opacity}>
          <rect
            x={x + 18}
            y={topY - 18}
            width={w - 36}
            height={14}
            rx={5}
            fill="#94a3b8"
          />
          <path
            d={`M${x + 14} ${baseY + 8} H${x + w - 14}`}
            stroke="#8b8172"
            strokeWidth={7}
            strokeLinecap="round"
          />
        </PrimitiveStep>
        <PrimitiveStep index={2} progress={opacity} trace>
          {postX.map((px) => (
            <path
              key={px}
              d={`M${px} ${topY - 16} V${baseY}`}
              stroke="#334155"
              strokeWidth={5}
              strokeLinecap="round"
            />
          ))}
        </PrimitiveStep>
        <PrimitiveStep index={3} progress={opacity} trace>
          {[topY, midY, lowY].map((yy) => (
            <path
              key={yy}
              d={`M${postX[0] - 22} ${yy} H${postX[postX.length - 1] + 22}`}
              stroke="#64748b"
              strokeWidth={4}
              strokeLinecap="round"
            />
          ))}
        </PrimitiveStep>
        <PrimitiveStep index={4} progress={opacity} trace>
          <path
            d={bracePath}
            stroke="#f59e0b"
            strokeWidth={4}
            strokeLinecap="round"
            opacity={0.92}
          />
          <path
            d={`M${postX[postX.length - 1] + 8} ${midY} H${x + w + 10}`}
            stroke={colors.blue}
            strokeWidth={4}
            strokeLinecap="round"
            strokeDasharray="8 6"
          />
        </PrimitiveStep>
        <PrimitiveStep index={5} progress={opacity}>
          <LabelBadge
            text={labels[0]}
            cx={x + w / 2}
            cy={topY - 34}
            tone={toneOf("blue")}
            width={122}
            size={11}
          />
        </PrimitiveStep>
        <PrimitiveStep index={6} progress={opacity}>
          <LabelBadge
            text={labels[1]}
            cx={x + 68}
            cy={midY + 30}
            tone={toneOf("success")}
            width={116}
            size={10}
          />
        </PrimitiveStep>
        <PrimitiveStep index={7} progress={opacity}>
          <LabelBadge
            text={labels[2]}
            cx={x + w - 70}
            cy={midY - 26}
            tone={toneOf("amber")}
            width={122}
            size={10}
          />
        </PrimitiveStep>
        <PrimitiveStep index={8} progress={opacity}>
          <LabelBadge
            text={labels[3]}
            cx={x + w - 76}
            cy={topY + 30}
            tone={toneOf("blue")}
            width={116}
            size={10}
          />
        </PrimitiveStep>
      </g>
    );
  }
  if (node.kind === "power_distribution_tree") {
    const labels = labelsWithDefaults(
      node,
      ["总配电箱", "分配电箱", "开关箱", "用电设备"],
      4,
    );
    const badges = [
      ...(node.badges || []),
      "TN-S PE线",
      "漏保一级",
      "漏保二级",
    ].slice(0, 3);
    const cy = y + h * 0.55;
    const left = x + 34;
    const boxW = 62;
    const boxH = 42;
    const gap = (w - 68 - boxW * 4) / 3;
    const centers = [0, 1, 2, 3].map((i) => left + boxW / 2 + i * (boxW + gap));
    const renderBox = (
      cx: number,
      cyValue: number,
      label: string,
      toneName: string,
      extraProps: Record<string, string> = {},
    ) => {
      const boxTone = toneOf(toneName);
      return (
        <>
          <rect
            x={cx - boxW / 2}
            y={cyValue - boxH / 2}
            width={boxW}
            height={boxH}
            rx={12}
            fill={boxTone.fill}
            stroke={boxTone.stroke}
            strokeWidth={3}
            {...extraProps}
          />
          <TextLines
            text={label}
            x={cx}
            y={cyValue + 5}
            size={fitFontSize(label, boxW, 12, 10)}
            fill={boxTone.text}
          />
        </>
      );
    };
    if (node.mode === "shared_switch") {
      const sharedCenters = [x + 48, x + 112, x + 178];
      const branchX = sharedCenters[2];
      const deviceX = x + w - 34;
      const devA: [number, number] = [deviceX, cy - 38];
      const devB: [number, number] = [deviceX, cy + 38];
      const startX = branchX + boxW / 2 + 8;
      const endX = deviceX - boxW / 2 - 6;
      return (
        <g style={common}>
          <PrimitiveStep index={0} progress={opacity}>
            <TextLines
              text={node.text || "三级配电树"}
              x={x + w / 2}
              y={y + 18}
              size={16}
              fill="#176b7a"
            />
          </PrimitiveStep>
          <PrimitiveStep index={1} progress={opacity} trace>
            <path
              d={`M${sharedCenters[0] + boxW / 2} ${cy} H${branchX - boxW / 2}`}
              stroke="#94a3b8"
              strokeWidth={5}
              strokeLinecap="round"
            />
          </PrimitiveStep>
          <PrimitiveStep index={2} progress={opacity}>
            {renderBox(sharedCenters[0], cy, labels[0], "blue")}
          </PrimitiveStep>
          <PrimitiveStep index={3} progress={opacity}>
            {renderBox(sharedCenters[1], cy, labels[1], "neutral")}
          </PrimitiveStep>
          <PrimitiveStep index={4} progress={opacity}>
            {renderBox(branchX, cy, labels[2], "danger")}
          </PrimitiveStep>
          <PrimitiveStep index={5} progress={opacity} trace>
            <g data-shared-switch="1">
              <circle cx={startX} cy={cy} r={4.5} fill={colors.red} />
              <path
                data-shared-switch-branch="1"
                d={`M${startX} ${cy} L${endX} ${devA[1]}`}
                stroke={colors.red}
                strokeWidth={5}
                strokeLinecap="round"
                fill="none"
              />
              <polygon
                points={`${endX},${devA[1]} ${endX - 10},${devA[1] - 7} ${endX - 10},${devA[1] + 7}`}
                fill={colors.red}
              />
              <path
                data-shared-switch-branch="1"
                d={`M${startX} ${cy} L${endX} ${devB[1]}`}
                stroke={colors.red}
                strokeWidth={5}
                strokeLinecap="round"
                fill="none"
              />
              <polygon
                points={`${endX},${devB[1]} ${endX - 10},${devB[1] - 7} ${endX - 10},${devB[1] + 7}`}
                fill={colors.red}
              />
            </g>
          </PrimitiveStep>
          <PrimitiveStep index={5} progress={opacity}>
            <g data-shared-switch="1">
              {renderBox(devA[0], devA[1], labels[3], "danger", {
                "data-shared-switch-device": "1",
              })}
              {renderBox(
                devB[0],
                devB[1],
                node.second_device || "另一设备",
                "danger",
                { "data-shared-switch-device": "1" },
              )}
            </g>
          </PrimitiveStep>
          <PrimitiveStep index={6} progress={opacity}>
            <LabelBadge
              text="错误：一箱分两机"
              cx={x + w / 2}
              cy={y + h - 10}
              tone={toneOf("danger")}
              width={142}
              size={11}
            />
          </PrimitiveStep>
        </g>
      );
    }
    if (node.mode === "dedicated_switches") {
      const distributionX = x + 58;
      const switchX = x + 180;
      const deviceX = x + w - 38;
      const topY = cy - 38;
      const bottomY = cy + 38;
      return (
        <g style={common}>
          <PrimitiveStep index={0} progress={opacity}>
            <TextLines
              text={node.text || "三级配电树"}
              x={x + w / 2}
              y={y + 18}
              size={16}
              fill="#176b7a"
            />
          </PrimitiveStep>
          <PrimitiveStep index={1} progress={opacity} trace>
            <path
              d={`M${distributionX + boxW / 2 + 5} ${cy} L${switchX - boxW / 2 - 6} ${topY}`}
              stroke="#16a34a"
              strokeWidth={4}
              strokeLinecap="round"
              fill="none"
            />
            <path
              d={`M${distributionX + boxW / 2 + 5} ${cy} L${switchX - boxW / 2 - 6} ${bottomY}`}
              stroke="#16a34a"
              strokeWidth={4}
              strokeLinecap="round"
              fill="none"
            />
          </PrimitiveStep>
          <PrimitiveStep index={2} progress={opacity}>
            {renderBox(distributionX, cy, labels[0], "neutral")}
          </PrimitiveStep>
          <PrimitiveStep index={3} progress={opacity}>
            {renderBox(switchX, topY, labels[1], "success")}
          </PrimitiveStep>
          <PrimitiveStep index={4} progress={opacity}>
            {renderBox(switchX, bottomY, labels[2], "success")}
          </PrimitiveStep>
          <PrimitiveStep index={5} progress={opacity} trace>
            <path
              d={`M${switchX + boxW / 2 + 5} ${topY} H${deviceX - boxW / 2 - 6}`}
              stroke="#16a34a"
              strokeWidth={4}
              strokeLinecap="round"
              fill="none"
            />
            <path
              d={`M${switchX + boxW / 2 + 5} ${bottomY} H${deviceX - boxW / 2 - 6}`}
              stroke="#16a34a"
              strokeWidth={4}
              strokeLinecap="round"
              fill="none"
            />
          </PrimitiveStep>
          <PrimitiveStep index={5} progress={opacity}>
            {renderBox(deviceX, topY, labels[3], "amber")}
            {renderBox(
              deviceX,
              bottomY,
              node.second_device || "另一设备",
              "amber",
            )}
          </PrimitiveStep>
          <PrimitiveStep index={6} progress={opacity}>
            <LabelBadge
              text="正确：一机一箱"
              cx={x + w / 2}
              cy={y + h - 10}
              tone={toneOf("success")}
              width={132}
              size={11}
            />
          </PrimitiveStep>
        </g>
      );
    }
    return (
      <g style={common}>
        <PrimitiveStep index={0} progress={opacity}>
          <TextLines
            text={node.text || "三级配电树"}
            x={x + w / 2}
            y={y + 18}
            size={16}
            fill="#176b7a"
          />
        </PrimitiveStep>
        <PrimitiveStep index={1} progress={opacity} trace>
          <path
            d={`M${centers[0] + boxW / 2} ${cy} H${centers[centers.length - 1] - boxW / 2}`}
            stroke="#94a3b8"
            strokeWidth={6}
            strokeLinecap="round"
          />
        </PrimitiveStep>
        <PrimitiveStep index={2} progress={opacity}>
          {renderBox(centers[0], cy, labels[0], "blue")}
        </PrimitiveStep>
        <PrimitiveStep index={3} progress={opacity}>
          {renderBox(centers[1], cy, labels[1], "neutral")}
        </PrimitiveStep>
        <PrimitiveStep index={4} progress={opacity}>
          {renderBox(centers[2], cy, labels[2], "success")}
        </PrimitiveStep>
        <PrimitiveStep index={5} progress={opacity}>
          {renderBox(centers[3], cy, labels[3], "amber")}
        </PrimitiveStep>
        <PrimitiveStep index={6} progress={opacity} trace>
          <path
            d={`M${x + 42} ${y + h - 34} H${x + w - 42}`}
            stroke="#16a34a"
            strokeWidth={5}
            strokeLinecap="round"
            strokeDasharray="10 7"
          />
        </PrimitiveStep>
        <PrimitiveStep index={7} progress={opacity}>
          <LabelBadge
            text={badges[0]}
            cx={x + w / 2}
            cy={y + h - 34}
            tone={toneOf("success")}
            width={118}
            size={11}
          />
        </PrimitiveStep>
        <PrimitiveStep index={8} progress={opacity}>
          <LabelBadge
            text={badges[1]}
            cx={centers[0]}
            cy={cy - 42}
            tone={toneOf("amber")}
            width={88}
            size={10}
          />
        </PrimitiveStep>
        <PrimitiveStep index={9} progress={opacity}>
          <LabelBadge
            text={badges[2]}
            cx={centers[2]}
            cy={cy - 42}
            tone={toneOf("amber")}
            width={88}
            size={10}
          />
        </PrimitiveStep>
      </g>
    );
  }
  if (node.kind === "bulge") {
    const cx = x;
    const by = node.base_y ?? 150;
    return (
      <g style={common}>
        <path
          d={`M${cx - 34} ${by} Q${cx} ${by - 58} ${cx + 34} ${by} Z`}
          fill="#34465b"
          stroke={colors.blue}
          strokeWidth={4}
        />
        <TextLines
          text={node.text}
          x={cx}
          y={by - 76}
          size={15}
          fill="#1d4ed8"
        />
      </g>
    );
  }
  if (node.kind === "up_arrows") {
    return (
      <g style={common}>
        <path
          d={`M${x - 16} ${y} V${y - 32} M${x} ${y} V${y - 42} M${x + 16} ${y} V${y - 32}`}
          stroke="#f59e0b"
          strokeWidth={4}
          strokeLinecap="round"
        />
        <path
          d={`M${x - 22} ${y - 26} l6 -8 l6 8 M${x - 6} ${y - 36} l6 -8 l6 8 M${x + 10} ${y - 26} l6 -8 l6 8`}
          fill="none"
          stroke="#f59e0b"
          strokeWidth={3}
        />
      </g>
    );
  }
  if (node.kind === "up_arrow") {
    const hh = node.h ?? 90;
    return (
      <g style={common}>
        <path
          d={`M${x} ${y} V${y - hh}`}
          stroke={colors.red}
          strokeWidth={4}
          strokeLinecap="round"
        />
        <path
          d={`M${x - 9} ${y - hh + 12} l9 -13 l9 13`}
          fill="none"
          stroke={colors.red}
          strokeWidth={4}
          strokeLinecap="round"
        />
      </g>
    );
  }
  if (node.kind === "cut_cross") {
    return (
      <g style={common}>
        <path
          d={`M${x - 18} ${y + 18} L${x + 18} ${y - 18} M${x - 18} ${y - 18} L${x + 18} ${y + 18}`}
          stroke={colors.red}
          strokeWidth={8}
          strokeLinecap="round"
        />
        <TextLines text={node.text} x={x} y={y - 42} size={16} fill="#b91c1c" />
      </g>
    );
  }
  if (node.kind === "dry_zone") {
    return (
      <g style={common}>
        <rect
          x={x}
          y={y}
          width={w}
          height={h}
          rx={9}
          fill="none"
          stroke={colors.blue}
          strokeWidth={5}
          strokeDasharray="9 7"
        />
        <TextLines
          text={node.text}
          x={x + w / 2}
          y={y - 18}
          size={16}
          fill="#1d4ed8"
        />
      </g>
    );
  }
  if (node.kind === "sweep_line") {
    return (
      <g style={common}>
        <path
          d={`M${x} ${y} H${x + w}`}
          stroke="#f59e0b"
          strokeWidth={5}
          strokeLinecap="round"
        />
        <TextLines
          text={node.text}
          x={x + w / 2}
          y={y + 24}
          size={13}
          fill="#b45309"
        />
      </g>
    );
  }
  if (node.kind === "membrane_strip") {
    return (
      <g style={common}>
        <rect x={x} y={y} width={w} height={14} rx={5} fill={t.stroke} />
        <TextLines
          text={node.text}
          x={x + w / 2}
          y={y - 18}
          size={16}
          fill={t.text}
        />
      </g>
    );
  }
  if (node.kind === "coverage_bracket") {
    const x1 = node.x1 ?? x;
    const x2 = node.x2 ?? x + w;
    return (
      <g style={common}>
        <path
          d={`M${x1} ${y - 12} v22 M${x2} ${y - 12} v22 M${x1} ${y} H${x2}`}
          stroke={colors.teal}
          strokeWidth={4}
          fill="none"
        />
        <TextLines
          text={node.text}
          x={(x1 + x2) / 2}
          y={y + 32}
          size={13}
          fill="#047857"
        />
      </g>
    );
  }
  if (node.kind === "lap_curve") {
    const x1 = node.x1 ?? x;
    const x2 = node.x2 ?? x + w;
    return (
      <g style={common}>
        <path
          d={`M${x1} ${y} C${x1 + 40} ${y + 26} ${x2 - 40} ${y + 26} ${x2} ${y}`}
          stroke={colors.blue}
          strokeWidth={4}
          fill="none"
          strokeDasharray="10 7"
        />
      </g>
    );
  }
  if (node.kind === "water_layer") {
    return (
      <g style={common}>
        <rect
          x={x}
          y={y}
          width={w}
          height={24}
          rx={7}
          fill={colors.blue}
          opacity={0.72}
        />
        <TextLines
          text={node.text}
          x={x + w / 2}
          y={y - 16}
          size={16}
          fill="#1d4ed8"
        />
      </g>
    );
  }
  if (node.kind === "check_badge") {
    return (
      <g style={common}>
        <circle
          cx={x}
          cy={y}
          r={24}
          fill="#ecfdf5"
          stroke={colors.teal}
          strokeWidth={4}
        />
        <text
          x={x}
          y={y + 9}
          textAnchor="middle"
          fontSize={28}
          fontWeight={900}
          fill="#047857"
        >
          ✓
        </text>
      </g>
    );
  }
  if (node.kind === "process_flow" && node.mode === "hidden_sample_objects") {
    const labels = labelsWithDefaults(
      node,
      ["合格证", "材料样品", "复验闸", "见证章", "隐蔽剖面"],
      5,
    );
    const yy = y + 92;
    const entryX = x + w * 0.18;
    const gateX = x + w * 0.43;
    const stampX = x + w * 0.64;
    const hiddenX = x + w * 0.84;
    return (
      <g style={common}>
        <PrimitiveStep index={0} progress={opacity}>
          <TextLines
            text={node.text || "材料样品与隐蔽剖面"}
            x={x + w / 2}
            y={y + 28}
            size={15}
            fill={t.text}
          />
        </PrimitiveStep>
        <PrimitiveStep index={1} progress={opacity} trace>
          <path
            d={`M${x + 42} ${yy + 42} H${x + w - 42}`}
            stroke="#cbd5e1"
            strokeWidth={6}
            strokeLinecap="round"
          />
        </PrimitiveStep>
        <PrimitiveStep index={2} progress={opacity}>
          <g data-layout-item="hidden.entry">
            <g data-layout-shape="hidden.entry">
              <rect
                x={entryX - 40}
                y={yy - 30}
                width={80}
                height={58}
                rx={17}
                fill="#ecfdf5"
                stroke="#10b981"
                strokeWidth={3.4}
              />
              <path
                d={`M${entryX - 23} ${yy - 12} H${entryX - 4} M${entryX - 23} ${yy + 1} H${entryX - 7}`}
                stroke="#2563eb"
                strokeWidth={3.2}
                strokeLinecap="round"
              />
              <circle
                cx={entryX - 21}
                cy={yy + 15}
                r={7}
                fill="#93c5fd"
                stroke="#1d4ed8"
                strokeWidth={2.5}
              />
              <circle
                cx={entryX + 23}
                cy={yy - 12}
                r={11}
                fill="#d1fae5"
                stroke="#047857"
                strokeWidth={2.8}
              />
              <rect
                x={entryX + 5}
                y={yy + 3}
                width={27}
                height={9}
                rx={4}
                fill="#a7f3d0"
              />
              <path
                d={`M${entryX - 26} ${yy + 32} H${entryX + 30}`}
                stroke="#047857"
                strokeWidth={4.2}
                strokeLinecap="round"
              />
            </g>
            <g data-layout-label="hidden.entry">
              <rect
                x={entryX - 35}
                y={y + 145}
                width={70}
                height={23}
                rx={8}
                fill="#eff6ff"
                stroke="#60a5fa"
                strokeWidth={1.6}
              />
              <TextLines
                text="材料进场"
                x={entryX}
                y={y + 160}
                size={10}
                fill="#1d4ed8"
              />
            </g>
          </g>
        </PrimitiveStep>
        <PrimitiveStep index={3} progress={opacity}>
          <g data-layout-item="hidden.gate">
            <g data-layout-shape="hidden.gate">
              <path
                d={`M${gateX - 22} ${yy + 30} V${yy - 29} M${gateX + 22} ${yy + 30} V${yy - 29}`}
                stroke="#f59e0b"
                strokeWidth={5.4}
                strokeLinecap="round"
              />
              <rect
                x={gateX - 20}
                y={yy - 20}
                width={40}
                height={44}
                rx={10}
                fill="#fff7ed"
                stroke="#f59e0b"
                strokeWidth={3.2}
              />
              <path
                d={`M${gateX - 8} ${yy - 5} H${gateX + 10} M${gateX - 8} ${yy + 8} H${gateX + 7}`}
                stroke="#f97316"
                strokeWidth={3.2}
                strokeLinecap="round"
              />
              <circle cx={gateX - 14} cy={yy - 5} r={3.7} fill="#10b981" />
              <circle cx={gateX - 14} cy={yy + 8} r={3.7} fill="#10b981" />
            </g>
            <g data-layout-label="hidden.gate">
              <rect
                x={gateX - 31}
                y={y + 145}
                width={62}
                height={23}
                rx={8}
                fill="#fffbeb"
                stroke="#f59e0b"
                strokeWidth={1.6}
              />
              <TextLines
                text={labels[2]}
                x={gateX}
                y={y + 160}
                size={10}
                fill="#b45309"
              />
            </g>
          </g>
        </PrimitiveStep>
        <PrimitiveStep index={4} progress={opacity}>
          <g data-layout-item="hidden.stamp">
            <g data-layout-shape="hidden.stamp">
              <rect
                x={stampX - 20}
                y={yy - 28}
                width={40}
                height={51}
                rx={12}
                fill="#fff7ed"
                stroke="#f97316"
                strokeWidth={3.2}
              />
              <path
                d={`M${stampX - 9} ${yy - 2} H${stampX + 9} M${stampX - 14} ${yy + 14} H${stampX + 14}`}
                stroke="#9a3412"
                strokeWidth={4.2}
                strokeLinecap="round"
              />
              <circle
                cx={stampX}
                cy={yy - 13}
                r={8.5}
                fill="#fed7aa"
                stroke="#f97316"
                strokeWidth={2.6}
              />
            </g>
            <g data-layout-label="hidden.stamp">
              <rect
                x={stampX - 28}
                y={y + 145}
                width={56}
                height={23}
                rx={8}
                fill="#fff7ed"
                stroke="#f97316"
                strokeWidth={1.6}
              />
              <TextLines
                text={labels[3]}
                x={stampX}
                y={y + 160}
                size={10}
                fill="#9a3412"
              />
            </g>
          </g>
        </PrimitiveStep>
        <PrimitiveStep index={5} progress={opacity}>
          <g data-layout-item="hidden.cut">
            <g data-layout-shape="hidden.cut">
              <rect
                x={hiddenX - 25}
                y={yy - 32}
                width={50}
                height={62}
                rx={11}
                fill="#f8fafc"
                stroke="#94a3b8"
                strokeWidth={3.2}
              />
              <rect
                x={hiddenX - 18}
                y={yy - 22}
                width={36}
                height={9}
                rx={4}
                fill="#cbd5e1"
              />
              <rect
                x={hiddenX - 18}
                y={yy - 8}
                width={36}
                height={9}
                rx={4}
                fill="#a7f3d0"
              />
              <rect
                x={hiddenX - 18}
                y={yy + 6}
                width={36}
                height={9}
                rx={4}
                fill="#fde68a"
              />
              <path
                d={`M${hiddenX - 25} ${yy - 43} H${hiddenX + 25}`}
                stroke="#ef4444"
                strokeWidth={4.6}
                strokeLinecap="round"
                strokeDasharray="7 6"
              />
              <circle
                cx={hiddenX + 22}
                cy={yy + 23}
                r={8.5}
                fill="#10b981"
                stroke="#047857"
                strokeWidth={2.6}
              />
            </g>
            <g data-layout-label="hidden.cut">
              <rect
                x={hiddenX - 31}
                y={y + 145}
                width={62}
                height={23}
                rx={8}
                fill="#f8fafc"
                stroke="#cbd5e1"
                strokeWidth={1.6}
              />
              <TextLines
                text={labels[4]}
                x={hiddenX}
                y={y + 160}
                size={10}
                fill="#334155"
              />
            </g>
          </g>
        </PrimitiveStep>
      </g>
    );
  }
  if (node.kind === "process_flow" && node.mode === "acceptance_objects") {
    const labels = labelsWithDefaults(
      node,
      ["报验单", "检验批车", "验收闸", "记录表"],
      4,
    );
    const docX = x + 46;
    const cartX = x + 126;
    const gateX = x + 208;
    const recX = x + 286;
    const yy = y + 88;
    return (
      <g style={common}>
        <PrimitiveStep index={0} progress={opacity}>
          <TextLines
            text={node.text || "现场对象流转"}
            x={x + w / 2}
            y={y + 28}
            size={15}
            fill={t.text}
          />
        </PrimitiveStep>
        <PrimitiveStep index={1} progress={opacity} trace>
          <path
            d={`M${x + 38} ${y + 118} H${x + w - 30}`}
            stroke="#cbd5e1"
            strokeWidth={7}
            strokeLinecap="round"
          />
        </PrimitiveStep>
        <PrimitiveStep index={2} progress={opacity}>
          <rect
            x={docX - 26}
            y={yy - 34}
            width={52}
            height={66}
            rx={8}
            fill="#eff6ff"
            stroke="#60a5fa"
            strokeWidth={4}
          />
          <path
            d={`M${docX + 8} ${yy - 34} L${docX + 26} ${yy - 16} H${docX + 8} Z`}
            fill="#dbeafe"
            stroke="#60a5fa"
            strokeWidth={3}
          />
          <path
            d={`M${docX - 14} ${yy - 8} H${docX + 14} M${docX - 14} ${yy + 6} H${docX + 10}`}
            stroke="#2563eb"
            strokeWidth={4}
            strokeLinecap="round"
          />
          <TextLines
            text={labels[0]}
            x={docX}
            y={y + 154}
            size={fitFontSize(labels[0], 74, 12, 9)}
            fill="#1d4ed8"
          />
        </PrimitiveStep>
        <PrimitiveStep index={3} progress={opacity}>
          <rect
            x={cartX - 34}
            y={yy - 17}
            width={68}
            height={36}
            rx={11}
            fill="#ecfdf5"
            stroke="#10b981"
            strokeWidth={4}
          />
          <path
            d={`M${cartX - 23} ${yy - 20} H${cartX + 22}`}
            stroke="#047857"
            strokeWidth={5}
            strokeLinecap="round"
          />
          <circle cx={cartX - 20} cy={yy + 28} r={8} fill="#047857" />
          <circle cx={cartX + 22} cy={yy + 28} r={8} fill="#047857" />
          <TextLines
            text={labels[1]}
            x={cartX}
            y={y + 154}
            size={fitFontSize(labels[1], 78, 12, 9)}
            fill="#047857"
          />
        </PrimitiveStep>
        <PrimitiveStep index={4} progress={opacity}>
          <path
            d={`M${gateX - 30} ${yy + 30} V${yy - 32} M${gateX + 30} ${yy + 30} V${yy - 32}`}
            stroke="#f59e0b"
            strokeWidth={7}
            strokeLinecap="round"
          />
          <rect
            x={gateX - 35}
            y={yy - 20}
            width={70}
            height={24}
            rx={10}
            fill="#fff7ed"
            stroke="#f59e0b"
            strokeWidth={4}
          />
          <path
            d={`M${gateX - 20} ${yy - 8} H${gateX + 20}`}
            stroke="#f97316"
            strokeWidth={5}
            strokeLinecap="round"
          />
          <TextLines
            text={labels[2]}
            x={gateX}
            y={y + 154}
            size={fitFontSize(labels[2], 78, 12, 9)}
            fill="#b45309"
          />
        </PrimitiveStep>
        <PrimitiveStep index={5} progress={opacity}>
          <rect
            x={recX - 28}
            y={yy - 35}
            width={56}
            height={66}
            rx={9}
            fill="#fffdf7"
            stroke="#e0cfae"
            strokeWidth={4}
          />
          <rect
            x={recX - 14}
            y={yy - 43}
            width={28}
            height={13}
            rx={6}
            fill="#ffd27f"
            stroke="#e0a83d"
            strokeWidth={3}
          />
          <path
            d={`M${recX - 16} ${yy - 8} H${recX + 16} M${recX - 16} ${yy + 7} H${recX + 12}`}
            stroke="#8b5e1f"
            strokeWidth={4}
            strokeLinecap="round"
          />
          <rect
            x={recX - 32}
            y={yy + 32}
            width={64}
            height={11}
            rx={4}
            fill="#cbd5e1"
          />
          <rect
            x={recX - 24}
            y={yy + 45}
            width={48}
            height={10}
            rx={4}
            fill="#94a3b8"
          />
          <TextLines
            text={labels[3]}
            x={recX}
            y={y + 154}
            size={fitFontSize(labels[3], 78, 12, 9)}
            fill="#6b4e16"
          />
        </PrimitiveStep>
      </g>
    );
  }
  if (node.kind === "process_flow") {
    const labels = labelsWithDefaults(
      node,
      ["先判", "再做", "复核", "写分"],
      4,
    );
    const stepGap = w / Math.max(labels.length, 1);
    return (
      <g style={common}>
        <PrimitiveStep index={0} progress={opacity}>
          <TextLines
            text={node.text || "按顺序 reveal"}
            x={x + w / 2}
            y={y + 30}
            size={15}
            fill={t.text}
          />
        </PrimitiveStep>
        <PrimitiveStep index={1} progress={opacity} trace>
          <path
            d={`M${x + 34} ${y + 88} H${x + w - 34}`}
            stroke="#cbd5e1"
            strokeWidth={8}
            strokeLinecap="round"
          />
        </PrimitiveStep>
        {labels.map((label, index) => {
          const cx = x + stepGap * index + stepGap / 2;
          const circleTone = toneOf(
            ["blue", "success", "amber", "neutral"][index % 4],
          );
          const size = fitFontSize(label, 68, 13, 10);
          return (
            <PrimitiveStep
              key={`${label}-${index}`}
              index={index + 2}
              progress={opacity}
            >
              <circle
                cx={cx}
                cy={y + 88}
                r={31}
                fill={circleTone.fill}
                stroke={circleTone.stroke}
                strokeWidth={4}
              />
              <TextLines
                text={label}
                x={cx}
                y={y + 93}
                size={size}
                fill={circleTone.text}
              />
              <TextLines
                text={`第${index + 1}步`}
                x={cx}
                y={y + 142}
                size={12}
                fill="#64748b"
              />
            </PrimitiveStep>
          );
        })}
      </g>
    );
  }
  if (node.kind === "layer_stack") {
    const labels = labelsWithDefaults(
      node,
      ["面层", "防水层", "找平层", "基层"],
      4,
    );
    const fills = ["#60a5fa", "#10b981", "#c5b78f", "#87919d"];
    const startY = y + 70;
    const layerH = 28;
    return (
      <g style={common}>
        <PrimitiveStep index={0} progress={opacity}>
          <TextLines
            text={node.text || "剖面分层"}
            x={x + w / 2}
            y={y + 36}
            size={16}
            fill={t.text}
          />
        </PrimitiveStep>
        <PrimitiveStep index={1} progress={opacity}>
          <rect
            x={x + 28}
            y={startY - 12}
            width={w - 56}
            height={labels.length * layerH + 8}
            rx={18}
            fill="none"
            stroke="#eadfcb"
            strokeWidth={3}
          />
        </PrimitiveStep>
        {labels.map((label, index) => {
          const yy = startY + index * layerH;
          return (
            <PrimitiveStep
              key={`${label}-${index}`}
              index={index + 2}
              progress={opacity}
            >
              <rect
                x={x + 38}
                y={yy}
                width={w - 76}
                height={layerH - 4}
                rx={6}
                fill={fills[index % fills.length]}
                opacity={0.88}
              />
              <TextLines
                text={label}
                x={x + 18}
                y={yy + 18}
                size={12}
                fill="#334155"
                anchor="start"
              />
            </PrimitiveStep>
          );
        })}
      </g>
    );
  }
  if (node.kind === "pit_threshold_board") {
    const mode = node.mode || "method";
    const groundY = y + 54;
    const pitLeft = x + w * 0.22;
    const pitRight = x + w * 0.58;
    const pitBottom = y + h * 0.62;
    const pitMid = (pitLeft + pitRight) / 2;
    const axisX = x + w * 0.13;
    const rightX = x + w * 0.76;
    const ruleY = y + h - 47;
    const ruleTitle = node.rule_title || "判据";
    const ruleMain = node.rule_main || "题干对象先入图";
    const ruleSub = node.rule_sub || "再扫成采分句";
    const mainSize = fitFontSize(ruleMain, w - 126, 18, 11);
    const subSize = fitFontSize(ruleSub, w - 126, 12, 9);
    const compact = mode === "score";
    const sparseLabels = mode === "problem" || mode === "score";
    const showElimination = ["problem", "method", "scan", "score"].includes(
      mode,
    );
    const showInrush = ["inrush", "score"].includes(mode);
    const showLayer = ["layer", "score"].includes(mode);
    const showScan = mode === "scan";
    const stepIds = new Set(
      (node.primitive_steps || []).map((step) => step.id),
    );
    const thresholdStepId = stepIds.has("scan_depth_axis")
      ? "scan_depth_axis"
      : "drop_thresholds";
    const objectStepId =
      mode === "inrush"
        ? "route_recharge"
        : mode === "layer"
          ? "mark_five_meter"
          : mode === "score"
            ? "collect_score_lines"
            : mode === "scan"
              ? "trace_to_sentence"
              : "eliminate_pipe";
    const ruleStepId =
      mode === "scan"
        ? "write_answer_atom"
        : mode === "score"
          ? "compress_labels"
          : "attach_light_well";
    return (
      <g style={common}>
        <PrimitiveStep
          index={0}
          progress={opacity}
          stepId={stepIds.has("draw_section") ? "draw_section" : undefined}
        >
          <rect
            data-engineering-object="pit-blueprint-board"
            data-visual-signature-part="board-frame"
            x={x}
            y={y}
            width={w}
            height={h}
            rx={18}
            fill="#061f2d"
            stroke="#245f7b"
            strokeWidth={2.4}
            opacity={0.98}
          />
          <TextLines
            text={node.text || "基坑降水剖面"}
            x={x + w / 2}
            y={y + 18}
            size={17}
            fill="#eaf8ff"
          />
          <g
            data-engineering-object="soil-layers"
            data-visual-signature-part="section-layers"
          >
            <rect
              x={pitLeft}
              y={groundY}
              width={pitRight - pitLeft}
              height={pitBottom - groundY}
              fill="#0b2e3f"
              opacity={0.52}
            />
            <path
              d={`M${pitLeft} ${groundY + 18} H${pitRight}`}
              stroke="#5fb5d8"
              strokeWidth={1.4}
              strokeDasharray="5 5"
              opacity={0.82}
            />
            <path
              d={`M${pitLeft} ${groundY + 49} H${pitRight}`}
              stroke="#e2c995"
              strokeWidth={6}
              opacity={0.62}
            />
            <rect
              x={pitLeft}
              y={pitBottom - 17}
              width={pitRight - pitLeft}
              height={17}
              fill="#12344a"
              opacity={0.85}
            />
            <path
              d={`M${pitLeft + 7} ${groundY + 10} l-15 16 M${pitLeft + 28} ${groundY + 10} l-36 36 M${pitRight - 28} ${pitBottom - 16} l-22 22 M${pitRight - 8} ${pitBottom - 16} l-22 22`}
              stroke="#2e6a85"
              strokeWidth={1.2}
              opacity={0.6}
            />
          </g>
          <g
            data-engineering-object="pit-section"
            data-visual-signature-part="pit-section"
          >
            <path
              d={`M${x + 24} ${groundY} H${x + w - 26}`}
              stroke="#c8f0ff"
              strokeWidth={3.2}
              strokeLinecap="round"
            />
            <path
              d={`M${pitLeft} ${groundY} V${pitBottom} H${pitRight} V${groundY}`}
              stroke="#e8f8ff"
              strokeWidth={3.4}
              fill="none"
              strokeLinejoin="round"
            />
            <path
              d={`M${axisX} ${groundY - 10} V${pitBottom}`}
              stroke="#6bc9f5"
              strokeWidth={2.4}
            />
            <path
              d={`M${axisX - 7} ${groundY - 2} l7 -14 l7 14 M${axisX - 7} ${pitBottom - 14} l7 14 l7 -14`}
              stroke="#6bc9f5"
              strokeWidth={2.4}
              fill="none"
              strokeLinecap="round"
            />
            <text
              transform={`translate(${axisX - 17} ${(groundY + pitBottom) / 2}) rotate(-90)`}
              textAnchor="middle"
              fontSize={12}
              fontWeight={900}
              fill="#86d9ff"
            >
              开挖深度 H
            </text>
            <text
              x={x + 30}
              y={groundY - 8}
              fontSize={12}
              fontWeight={900}
              fill="#beeaff"
            >
              地面 ±0.000
            </text>
          </g>
        </PrimitiveStep>
        <PrimitiveStep
          index={1}
          progress={opacity}
          trace
          stepId={thresholdStepId}
        >
          <g
            data-engineering-object="3m-threshold"
            data-visual-signature-part="threshold-line"
          >
            <circle cx={axisX} cy={groundY + 45} r={4.8} fill="#f5a623" />
            <path
              data-threshold-line="3m"
              d={`M${axisX} ${groundY + 45} H${x + w - 38}`}
              stroke="#f5a623"
              strokeWidth={3}
              strokeDasharray="7 7"
            />
            {sparseLabels ? null : (
              <text
                x={x + w - 34}
                y={groundY + 50}
                textAnchor="end"
                fontSize={13}
                fontWeight={900}
                fill="#ffb832"
              >
                {">3m 井点"}
              </text>
            )}
          </g>
          <g
            data-engineering-object="case-depth-threshold"
            data-visual-signature-part="danger-line"
          >
            <circle cx={axisX} cy={pitBottom} r={4.8} fill="#ff5b61" />
            <path
              data-threshold-line="case-depth"
              d={`M${axisX} ${pitBottom} H${x + w - 38}`}
              stroke="#ff5b61"
              strokeWidth={3}
              strokeDasharray="7 7"
            />
            {sparseLabels ? null : (
              <text
                x={x + w - 34}
                y={pitBottom + 5}
                textAnchor="end"
                fontSize={13}
                fontWeight={900}
                fill="#ff6b70"
              >
                {mode === "layer" ? "5m超限" : "本题 6m"}
              </text>
            )}
          </g>
        </PrimitiveStep>
        <PrimitiveStep index={2} progress={opacity} stepId={objectStepId}>
          <g
            data-engineering-object="pipe-well"
            data-visual-signature-part="pipe-well"
          >
            <path
              d={`M${rightX} ${groundY - 2} V${pitBottom - 8}`}
              stroke="#ffb184"
              strokeWidth={5}
              strokeLinecap="round"
              opacity={0.95}
            />
            <circle
              cx={rightX}
              cy={groundY - 6}
              r={9}
              fill="#092435"
              stroke="#ffb184"
              strokeWidth={3}
            />
            {sparseLabels ? null : (
              <text
                x={rightX}
                y={groundY - 21}
                textAnchor="middle"
                fontSize={12}
                fontWeight={900}
                fill="#ffcfb5"
              >
                管井
              </text>
            )}
          </g>
          {showElimination ? (
            <g
              data-engineering-object="pipe-well-eliminated"
              data-visual-signature-part="elimination-and-light-well"
            >
              <path
                d={`M${rightX - 18} ${groundY + 18} L${rightX + 18} ${pitBottom - 12} M${rightX + 18} ${groundY + 18} L${rightX - 18} ${pitBottom - 12}`}
                stroke={colors.red}
                strokeWidth={5}
                strokeLinecap="round"
              />
              <path
                d={`M${pitLeft - 12} ${groundY + 8} V${pitBottom - 14} M${pitLeft + 8} ${groundY + 8} V${pitBottom - 20} M${pitRight - 8} ${groundY + 8} V${pitBottom - 20} M${pitRight + 12} ${groundY + 8} V${pitBottom - 14}`}
                stroke="#65d4ff"
                strokeWidth={3.4}
                strokeLinecap="round"
              />
              <path
                d={`M${pitLeft - 18} ${groundY + 19} H${pitLeft + 14} M${pitRight - 14} ${groundY + 19} H${pitRight + 18}`}
                stroke="#65d4ff"
                strokeWidth={2.2}
                strokeDasharray="5 4"
              />
              {sparseLabels ? null : (
                <text
                  x={pitMid}
                  y={groundY - 20}
                  textAnchor="middle"
                  fontSize={12}
                  fontWeight={900}
                  fill="#9ee8ff"
                >
                  轻型井点
                </text>
              )}
            </g>
          ) : null}
          {showScan ? (
            <g
              data-engineering-object="object-to-score-trace"
              data-visual-signature-part="answer-trace"
            >
              <path
                d={`M${pitLeft + 12} ${groundY + 10} C${x + 120} ${y + 25} ${x + 210} ${y + 28} ${x + w - 58} ${y + 40}`}
                stroke="#65d4ff"
                strokeWidth={3}
                fill="none"
                strokeDasharray="7 5"
              />
              <text
                x={x + w - 96}
                y={y + 33}
                fontSize={11}
                fontWeight={900}
                fill="#9ee8ff"
              >
                对象→采分句
              </text>
            </g>
          ) : null}
          {showLayer ? (
            <g
              data-engineering-object="layer-depth-control"
              data-visual-signature-part="layer-depth-control"
            >
              <path
                data-threshold-line="5m-overlimit"
                d={`M${pitRight + 30} ${groundY + 32} V${pitBottom}`}
                stroke="#ff5b61"
                strokeWidth={4}
                strokeDasharray="6 5"
              />
              <path
                data-threshold-line="3m-control"
                d={`M${pitRight + 46} ${groundY + 32} V${groundY + 77}`}
                stroke="#19c37d"
                strokeWidth={4}
              />
              {compact ? null : (
                <>
                  <text
                    x={pitRight + 53}
                    y={groundY + 58}
                    fontSize={12}
                    fontWeight={900}
                    fill="#19d58c"
                  >
                    ≤3m
                  </text>
                  <text
                    x={pitRight + 36}
                    y={pitBottom + 14}
                    fontSize={12}
                    fontWeight={900}
                    fill="#ff6b70"
                  >
                    5m
                  </text>
                </>
              )}
            </g>
          ) : null}
          {showInrush ? (
            <g
              data-engineering-object="recharge-and-inrush-routes"
              data-visual-signature-part="recharge-inrush-relief"
            >
              <path
                d={`M${x + w - 62} ${groundY - 2} V${pitBottom - 26}`}
                stroke="#ffc75f"
                strokeWidth={4.2}
                strokeLinecap="round"
              />
              <circle
                cx={x + w - 62}
                cy={groundY - 7}
                r={8}
                fill="#092435"
                stroke="#ffc75f"
                strokeWidth={3}
              />
              <path
                d={`M${x + w - 62} ${groundY + 34} C${x + w - 88} ${groundY + 26} ${x + w - 116} ${groundY + 28} ${pitRight + 10} ${groundY + 42}`}
                stroke="#ffc75f"
                strokeWidth={3.5}
                fill="none"
                strokeDasharray="7 5"
              />
              {compact ? null : (
                <>
                  <text
                    x={x + w - 82}
                    y={groundY + 19}
                    textAnchor="middle"
                    fontSize={11}
                    fontWeight={900}
                    fill="#ffd98a"
                  >
                    回灌
                  </text>
                  <text
                    x={pitRight + 18}
                    y={groundY + 35}
                    fontSize={11}
                    fontWeight={900}
                    fill="#ffd98a"
                  >
                    防沉降
                  </text>
                </>
              )}
              <path
                d={`M${pitMid - 30} ${pitBottom + 1} V${pitBottom - 35} M${pitMid} ${pitBottom + 1} V${pitBottom - 43} M${pitMid + 30} ${pitBottom + 1} V${pitBottom - 35}`}
                stroke="#ff5b61"
                strokeWidth={4}
                strokeLinecap="round"
              />
              <path
                d={`M${pitMid - 37} ${pitBottom - 27} l7 -10 l7 10 M${pitMid - 7} ${pitBottom - 35} l7 -10 l7 10 M${pitMid + 23} ${pitBottom - 27} l7 -10 l7 10`}
                stroke="#ff5b61"
                strokeWidth={3}
                fill="none"
                strokeLinecap="round"
              />
              <path
                data-threshold-line="relief-boundary"
                d={`M${pitRight + 18} ${pitBottom - 52} H${x + w - 38}`}
                stroke="#65d4ff"
                strokeWidth={3}
                strokeDasharray="6 5"
              />
              {compact ? null : (
                <>
                  <text
                    x={pitMid}
                    y={pitBottom - 50}
                    textAnchor="middle"
                    fontSize={12}
                    fontWeight={900}
                    fill="#ff7a80"
                  >
                    承压水突涌口
                  </text>
                  <text
                    x={pitRight + 22}
                    y={pitBottom - 62}
                    fontSize={11}
                    fontWeight={900}
                    fill="#9ee8ff"
                  >
                    减压 / 封底隔渗
                  </text>
                </>
              )}
            </g>
          ) : null}
        </PrimitiveStep>
        <PrimitiveStep index={3} progress={opacity} stepId={ruleStepId}>
          <g
            data-rule-card="blueprint"
            data-engineering-object="bottom-rule-card"
            data-visual-signature-part="rule-card"
          >
            <rect
              x={x + 16}
              y={ruleY}
              width={w - 32}
              height={45}
              rx={12}
              fill="#061b28"
              stroke="#1f526b"
              strokeWidth={2.2}
            />
            <rect
              x={x + 28}
              y={ruleY + 10}
              width={58}
              height={22}
              rx={11}
              fill="#2a2e26"
              stroke="#f5a623"
              strokeWidth={1.2}
            />
            <TextLines
              text={ruleTitle}
              x={x + 57}
              y={ruleY + 26}
              size={13}
              fill="#ffb832"
            />
            <TextLines
              text={ruleMain}
              x={x + 99}
              y={ruleY + 22}
              size={mainSize}
              fill="#eaf8ff"
              anchor="start"
            />
            <TextLines
              text={ruleSub}
              x={x + 99}
              y={ruleY + 38}
              size={subSize}
              fill="#b9e7f8"
              weight={850}
              anchor="start"
            />
          </g>
        </PrimitiveStep>
      </g>
    );
  }
  if (node.kind === "inspection_blueprint_board") {
    const mode = node.mode || "overview";
    const poster = h >= 420;
    const narrow = w < 500;
    const labels = labelsWithDefaults(
      node,
      ["材料样品", "复验闸", "见证章", "隐蔽剖面", "覆盖板", "验收记录"],
      6,
    );
    const topY = y + (poster ? h * 0.13 : 42);
    const flowY = y + (poster ? h * 0.37 : 118);
    const groundY = y + (poster ? h * 0.63 : 172);
    const dividerX = x + w * 0.5;
    const materialX = x + w * 0.135;
    const gateX = x + w * 0.27;
    const labX = x + w * 0.395;
    const hiddenX = x + w * 0.7;
    const sectionW = w * (poster ? 0.4 : 0.355);
    const sectionH = h * (poster ? 0.5 : 0.494);
    const sectionX = hiddenX - sectionW / 2;
    const sectionY = y + (poster ? h * 0.215 : 53);
    const laneMaterialX = narrow ? x + 56 : materialX;
    const laneGateX = narrow ? x + 138 : gateX;
    const laneLabX = narrow ? x + 208 : labX;
    const sampleW = narrow ? 70 : 84;
    const sampleH = narrow ? 58 : 70;
    const gateBarGap = narrow ? 21 : 25;
    const gateW = narrow ? 54 : 66;
    const gateH = narrow ? 44 : 48;
    const labW = narrow ? 58 : 76;
    const labH = narrow ? 58 : 70;
    const laneLabelSize = narrow ? 11 : 12;
    const coverLineY = sectionY + (poster ? 20 : 12);
    const midLineY = sectionY + sectionH * 0.51;
    const sectionGroundY = sectionY + sectionH;
    const ruleY = y + h - (poster ? 98 : 55);
    const ruleTitle = node.rule_title || "采分";
    const ruleMain = node.rule_main || "先复验，再覆盖";
    const ruleSub = node.rule_sub || "样品、见证、记录都在覆盖前闭合";
    const mainSize = fitFontSize(ruleMain, w - 132, 19, 12);
    const subSize = fitFontSize(ruleSub, w - 132, 12, 9);
    const wrong = mode === "branch" || mode === "qa";
    const showMaterial = [
      "overview",
      "material",
      "witness",
      "score",
      "branch",
      "closing",
    ].includes(mode);
    const showRecord = [
      "overview",
      "witness",
      "hidden",
      "score",
      "branch",
      "closing",
    ].includes(mode);
    const showHidden = [
      "overview",
      "material",
      "retest",
      "witness",
      "hidden",
      "branch",
      "score",
      "qa",
      "closing",
    ].includes(mode);
    const showMaterialSplit = false;
    const showRetestMatrix = mode === "retest";
    const showWitnessRoute = mode === "witness";
    const showHiddenShutter = mode === "hidden";
    const showAnswerSheet = mode === "score";
    const showLaneLab = mode !== "material";
    return (
      <g style={common}>
        <PrimitiveStep index={0} progress={opacity}>
          <TextLines
            text={node.text || "材料复验 + 隐蔽验收"}
            x={x + w / 2}
            y={y + 20}
            size={17}
            fill="#eaf8ff"
          />
          <path
            d={`M${x + 18} ${topY + 18} H${x + w - 18} M${x + 18} ${groundY} H${x + w - 18}`}
            stroke="#c8f0ff"
            strokeWidth={2.6}
            strokeLinecap="round"
          />
          <path
            d={`M${dividerX} ${topY} V${groundY + 3}`}
            stroke="#235270"
            strokeWidth={2.2}
            strokeDasharray="8 8"
          />
          <TextLines
            text="材料进场链"
            x={x + 106}
            y={topY + 1}
            size={12}
            fill="#9ee8ff"
          />
          <TextLines
            text="覆盖前工程剖面"
            x={hiddenX}
            y={topY + 1}
            size={12}
            fill="#9ee8ff"
          />
          <path
            d={`M${x + 24} ${coverLineY} H${x + w - 26}`}
            stroke="#ff5b61"
            strokeWidth={3.2}
            strokeDasharray="8 7"
          />
          <circle cx={x + 24} cy={coverLineY} r={5} fill="#ff5b61" />
          <text
            x={x + w - 28}
            y={coverLineY - 6}
            textAnchor="end"
            fontSize={12}
            fontWeight={950}
            fill="#ff6b70"
          >
            禁盖线
          </text>
        </PrimitiveStep>
        {showMaterial ? (
          <PrimitiveStep index={1} progress={opacity} trace>
            <g data-visual-signature-part="material_retest_lane">
              <path
                d={`M${x + 34} ${flowY} H${sectionX - 14}`}
                stroke="#f5a623"
                strokeWidth={3.8}
                strokeDasharray="9 7"
              />
              <rect
                x={x + 40}
                y={flowY - 58}
                width={sectionX - x - 92}
                height={116}
                rx={16}
                fill="#061b28"
                stroke="#1f526b"
                strokeWidth={2.6}
                opacity={0.92}
              />
              <rect
                data-layout-item="material.sample"
                x={laneMaterialX - sampleW / 2}
                y={flowY - sampleH / 2}
                width={sampleW}
                height={sampleH}
                rx={13}
                fill="#092435"
                stroke="#65d4ff"
                strokeWidth={3.2}
              />
              <path
                d={`M${laneMaterialX - sampleW * 0.28} ${flowY - 12} H${laneMaterialX + sampleW * 0.26} M${laneMaterialX - sampleW * 0.28} ${flowY + 6} H${laneMaterialX + sampleW * 0.18}`}
                stroke="#9ee8ff"
                strokeWidth={3.4}
                strokeLinecap="round"
              />
              <circle
                cx={laneMaterialX + sampleW * 0.3}
                cy={flowY + sampleH * 0.26}
                r={7}
                fill="#19c37d"
              />
              <path
                d={`M${laneGateX - gateBarGap} ${flowY - 46} V${flowY + 46} M${laneGateX + gateBarGap} ${flowY - 46} V${flowY + 46}`}
                stroke="#f5a623"
                strokeWidth={5.6}
                strokeLinecap="round"
              />
              <rect
                data-layout-item="material.retest-gate"
                x={laneGateX - gateW / 2}
                y={flowY - gateH / 2}
                width={gateW}
                height={gateH}
                rx={12}
                fill="#291f12"
                stroke="#f5a623"
                strokeWidth={3}
              />
              <TextLines
                text={labels[1]}
                x={laneGateX}
                y={flowY + 5}
                size={narrow ? 13 : 14}
                fill="#ffb832"
              />
              {showLaneLab ? (
                <>
                  <rect
                    data-layout-item="material.witness-stamp"
                    x={laneLabX - labW / 2}
                    y={flowY - labH / 2}
                    width={labW}
                    height={labH}
                    rx={13}
                    fill="#092435"
                    stroke="#ffb184"
                    strokeWidth={3.2}
                  />
                  <circle
                    cx={laneLabX}
                    cy={flowY - labH * 0.18}
                    r={narrow ? 10 : 12}
                    fill="#331b12"
                    stroke="#ffb184"
                    strokeWidth={2.6}
                  />
                  <path
                    d={`M${laneLabX - labW * 0.26} ${flowY + labH * 0.18} H${laneLabX + labW * 0.26}`}
                    stroke="#ffb184"
                    strokeWidth={4.2}
                    strokeLinecap="round"
                  />
                  <TextLines
                    text={labels[2]}
                    x={laneLabX}
                    y={flowY + labH / 2 + 16}
                    size={laneLabelSize}
                    fill="#ffcfb5"
                  />
                </>
              ) : null}
              <TextLines
                text={labels[0]}
                x={laneMaterialX}
                y={flowY + sampleH / 2 + 16}
                size={laneLabelSize}
                fill="#9ee8ff"
              />
            </g>
          </PrimitiveStep>
        ) : null}
        {showMaterialSplit ? (
          <PrimitiveStep index={1} progress={opacity}>
            <g data-visual-signature-part="material_certificate_split">
              {narrow ? (
                <>
                  <rect
                    x={x + 40}
                    y={flowY - 54}
                    width={w - 80}
                    height={130}
                    rx={18}
                    fill="#061b28"
                    stroke="#1f526b"
                    strokeWidth={2.8}
                    opacity={0.94}
                  />
                  <path
                    d={`M${x + 74} ${flowY} H${x + w - 72}`}
                    stroke="#f5a623"
                    strokeWidth={4.2}
                    strokeDasharray="10 8"
                  />
                  <rect
                    x={x + 62}
                    y={flowY - 46}
                    width={76}
                    height={70}
                    rx={14}
                    fill="#092435"
                    stroke="#65d4ff"
                    strokeWidth={3.4}
                  />
                  <TextLines
                    text="合格证"
                    x={x + 100}
                    y={flowY - 18}
                    size={13}
                    fill="#9ee8ff"
                  />
                  <path
                    d={`M${x + 80} ${flowY + 4} H${x + 122} M${x + 80} ${flowY + 20} H${x + 116}`}
                    stroke="#9ee8ff"
                    strokeWidth={3.4}
                    strokeLinecap="round"
                  />
                  <path
                    d={`M${x + 150} ${flowY - 34} L${x + 174} ${flowY + 34} M${x + 174} ${flowY - 34} L${x + 150} ${flowY + 34}`}
                    stroke="#ff5b61"
                    strokeWidth={5.2}
                    strokeLinecap="round"
                  />
                  <rect
                    x={x + 192}
                    y={flowY - 42}
                    width={78}
                    height={72}
                    rx={15}
                    fill="#291f12"
                    stroke="#f5a623"
                    strokeWidth={3.6}
                  />
                  <TextLines
                    text="样品"
                    x={x + 231}
                    y={flowY - 13}
                    size={14}
                    fill="#ffb832"
                  />
                  <path
                    d={`M${x + 211} ${flowY + 12} H${x + 251}`}
                    stroke="#f5a623"
                    strokeWidth={4.6}
                    strokeLinecap="round"
                  />
                  <path
                    d={`M${x + 278} ${flowY} H${x + 292}`}
                    stroke="#19c37d"
                    strokeWidth={4.4}
                    strokeLinecap="round"
                  />
                  <rect
                    x={x + 300}
                    y={flowY - 42}
                    width={68}
                    height={76}
                    rx={14}
                    fill="#0c2c22"
                    stroke="#19c37d"
                    strokeWidth={3.4}
                  />
                  <TextLines
                    text="复验合格"
                    x={x + 334}
                    y={flowY + 4}
                    size={12}
                    fill="#9bf3c8"
                  />
                  <TextLines
                    text="有证 ≠ 直接使用"
                    x={x + w / 2}
                    y={flowY + 58}
                    size={13}
                    fill="#ff6b70"
                  />
                </>
              ) : (
                <>
                  <rect
                    x={x + 34}
                    y={y + 68}
                    width={sectionX - x - 78}
                    height={groundY - y - 88}
                    rx={18}
                    fill="#061b28"
                    stroke="#1f526b"
                    strokeWidth={2.8}
                    opacity={0.94}
                  />
                  <rect
                    x={x + 62}
                    y={flowY - 46}
                    width={92}
                    height={86}
                    rx={14}
                    fill="#092435"
                    stroke="#65d4ff"
                    strokeWidth={3.4}
                  />
                  <TextLines
                    text="合格证"
                    x={x + 108}
                    y={flowY - 20}
                    size={13}
                    fill="#9ee8ff"
                  />
                  <path
                    d={`M${x + 82} ${flowY + 2} H${x + 136} M${x + 82} ${flowY + 20} H${x + 126}`}
                    stroke="#9ee8ff"
                    strokeWidth={3.6}
                    strokeLinecap="round"
                  />
                  <rect
                    x={x + 204}
                    y={flowY - 42}
                    width={90}
                    height={76}
                    rx={15}
                    fill="#291f12"
                    stroke="#f5a623"
                    strokeWidth={3.6}
                  />
                  <TextLines
                    text="样品"
                    x={x + 249}
                    y={flowY - 14}
                    size={14}
                    fill="#ffb832"
                  />
                  <path
                    d={`M${x + 164} ${flowY - 30} L${x + 188} ${flowY + 34} M${x + 188} ${flowY - 30} L${x + 164} ${flowY + 34}`}
                    stroke="#ff5b61"
                    strokeWidth={5.4}
                    strokeLinecap="round"
                  />
                  <path
                    d={`M${x + 302} ${flowY} H${sectionX - 86}`}
                    stroke="#19c37d"
                    strokeWidth={4.6}
                    strokeLinecap="round"
                  />
                  <rect
                    x={sectionX - 78}
                    y={flowY - 36}
                    width={62}
                    height={72}
                    rx={14}
                    fill="#0c2c22"
                    stroke="#19c37d"
                    strokeWidth={3.4}
                  />
                  <TextLines
                    text="复验合格"
                    x={sectionX - 47}
                    y={flowY + 4}
                    size={12}
                    fill="#9bf3c8"
                  />
                  <TextLines
                    text="有证 ≠ 直接使用"
                    x={x + 176}
                    y={flowY + 58}
                    size={13}
                    fill="#ff6b70"
                  />
                </>
              )}
            </g>
          </PrimitiveStep>
        ) : null}
        {showRetestMatrix ? (
          <PrimitiveStep index={1} progress={opacity}>
            <g data-visual-signature-part="retest_matrix">
              <rect
                x={x + 42}
                y={flowY - 76}
                width={176}
                height={90}
                rx={10}
                fill="#061b28"
                stroke="#1f526b"
                strokeWidth={2.5}
              />
              <TextLines
                text="材料对象复验格"
                x={x + 130}
                y={flowY - 52}
                size={12}
                fill="#eaf8ff"
              />
              {["钢筋", "水泥", "保温"].map((label, row) => (
                <g key={label}>
                  <path
                    d={`M${x + 54} ${flowY - 36 + row * 20} H${x + 205}`}
                    stroke="#1f526b"
                    strokeWidth={1.8}
                  />
                  <TextLines
                    text={label}
                    x={x + 72}
                    y={flowY - 22 + row * 20}
                    size={10}
                    fill="#9ee8ff"
                  />
                  <TextLines
                    text={
                      row === 0
                        ? "强度/伸长/重量"
                        : row === 1
                          ? "强度/安定性"
                          : "导热/密度/燃烧"
                    }
                    x={x + 148}
                    y={flowY - 22 + row * 20}
                    size={9}
                    fill="#ffcfb5"
                  />
                </g>
              ))}
            </g>
          </PrimitiveStep>
        ) : null}
        {showRecord ? (
          <PrimitiveStep index={2} progress={opacity} trace>
            <g data-visual-signature-part="witness_record_chain">
              <path
                d={`M${labX + 31} ${flowY - 8} C${labX + 58} ${flowY - 34} ${hiddenX - 80} ${flowY - 38} ${hiddenX - 55} ${flowY - 8}`}
                stroke="#65d4ff"
                strokeWidth={3}
                fill="none"
                strokeDasharray="7 6"
              />
              <rect
                x={x + w - 74}
                y={groundY - 78}
                width={54}
                height={66}
                rx={8}
                fill="#092435"
                stroke="#65d4ff"
                strokeWidth={2.8}
              />
              <path
                d={`M${x + w - 63} ${groundY - 57} H${x + w - 32} M${x + w - 63} ${groundY - 42} H${x + w - 38} M${x + w - 63} ${groundY - 27} H${x + w - 31}`}
                stroke="#9ee8ff"
                strokeWidth={3}
                strokeLinecap="round"
              />
              <TextLines
                text={labels[5]}
                x={x + w - 47}
                y={groundY + 5}
                size={11}
                fill="#9ee8ff"
              />
            </g>
          </PrimitiveStep>
        ) : null}
        {showWitnessRoute ? (
          <PrimitiveStep index={2} progress={opacity} trace>
            <g data-visual-signature-part="witness_route_map">
              {[
                [x + 60, flowY + 43, "现场取样"],
                [x + 147, flowY + 12, "见证人"],
                [x + 232, flowY + 42, "检测机构"],
              ].map(([cx, cy, label]) => (
                <g key={String(label)}>
                  <circle
                    cx={Number(cx)}
                    cy={Number(cy)}
                    r={22}
                    fill="#092435"
                    stroke="#65d4ff"
                    strokeWidth={3}
                  />
                  <TextLines
                    text={String(label)}
                    x={Number(cx)}
                    y={Number(cy) + 5}
                    size={9}
                    fill="#9ee8ff"
                  />
                </g>
              ))}
              <path
                d={`M${x + 82} ${flowY + 36} L${x + 128} ${flowY + 20} L${x + 210} ${flowY + 36}`}
                stroke="#65d4ff"
                strokeWidth={3}
                fill="none"
                strokeDasharray="7 6"
              />
              <TextLines
                text="送检前通知，记录由见证人填写"
                x={x + 152}
                y={flowY + 74}
                size={11}
                fill="#ffcfb5"
              />
            </g>
          </PrimitiveStep>
        ) : null}
        {showHidden ? (
          <PrimitiveStep index={3} progress={opacity}>
            <g data-visual-signature-part="hidden_work_section">
              <rect
                x={sectionX}
                y={sectionY}
                width={sectionW}
                height={sectionH}
                rx={3}
                fill="#0b2e3f"
                opacity={0.82}
              />
              <path
                d={`M${sectionX} ${midLineY} H${sectionX + sectionW}`}
                stroke="#5fb5d8"
                strokeWidth={1.6}
                strokeDasharray="5 5"
              />
              <path
                d={`M${sectionX} ${midLineY + 31} H${sectionX + sectionW}`}
                stroke="#e2c995"
                strokeWidth={5.5}
                opacity={0.75}
              />
              <path
                d={`M${sectionX} ${sectionY} V${sectionGroundY} H${sectionX + sectionW} V${sectionY}`}
                stroke="#e8f8ff"
                strokeWidth={3.6}
                fill="none"
              />
              <path
                d={`M${sectionX - 12} ${coverLineY} H${sectionX + sectionW + 12}`}
                stroke="#ff5b61"
                strokeWidth={3.5}
                strokeDasharray="8 7"
              />
              <circle cx={sectionX - 12} cy={coverLineY} r={5} fill="#ff5b61" />
              <rect
                x={sectionX + 20}
                y={sectionY - 23}
                width={sectionW - 40}
                height={16}
                rx={4}
                fill="#092435"
                stroke="#c8f0ff"
                strokeWidth={2.4}
              />
            </g>
            {showHiddenShutter ? (
              <g data-visual-signature-part="hidden_shutter_scan">
                <path
                  d={`M${hiddenX - 62} ${groundY - 72} H${hiddenX + 62}`}
                  stroke="#f5a623"
                  strokeWidth={4}
                  strokeLinecap="round"
                />
                <path
                  d={`M${hiddenX - 42} ${groundY - 92} H${hiddenX + 42} M${hiddenX - 42} ${groundY - 50} H${hiddenX + 42}`}
                  stroke="#19c37d"
                  strokeWidth={3}
                  strokeDasharray="7 5"
                />
                <TextLines
                  text="覆盖前扫描"
                  x={hiddenX}
                  y={groundY - 104}
                  size={11}
                  fill="#ffb832"
                />
              </g>
            ) : null}
          </PrimitiveStep>
        ) : null}
        {showAnswerSheet ? (
          <PrimitiveStep index={4} progress={opacity}>
            <g data-visual-signature-part="answer_scan_sheet">
              <rect
                x={x + 44}
                y={y + (poster ? 148 : 58)}
                width={180}
                height={poster ? 116 : 102}
                rx={12}
                fill="#061b28"
                stroke="#65d4ff"
                strokeWidth={2.5}
              />
              {["定环节", "复验见证", "覆盖前隐检", "合格后使用/覆盖"].map(
                (label, row) => (
                  <g key={label}>
                    <path
                      d={`M${x + 62} ${y + (poster ? 181 : 86) + row * (poster ? 23 : 19)} H${x + 204}`}
                      stroke={row < 3 ? "#65d4ff" : "#19c37d"}
                      strokeWidth={3}
                      strokeLinecap="round"
                      opacity={0.9}
                    />
                    <TextLines
                      text={label}
                      x={x + 72}
                      y={y + (poster ? 176 : 82) + row * (poster ? 23 : 19)}
                      size={poster ? 10 : 9}
                      fill="#eaf8ff"
                      anchor="start"
                    />
                  </g>
                ),
              )}
            </g>
          </PrimitiveStep>
        ) : null}
        {wrong ? (
          <PrimitiveStep index={4} progress={opacity} trace>
            <path
              d={`M${materialX} ${flowY + 45} H${hiddenX - 70}`}
              stroke="#ff5b61"
              strokeWidth={4}
              strokeDasharray="8 7"
            />
            <path
              d={`M${hiddenX - 98} ${flowY + 27} L${hiddenX - 70} ${flowY + 59} M${hiddenX - 70} ${flowY + 27} L${hiddenX - 98} ${flowY + 59}`}
              stroke="#ff5b61"
              strokeWidth={5}
              strokeLinecap="round"
            />
            <text
              x={hiddenX - 142}
              y={flowY + 69}
              fontSize={12}
              fontWeight={900}
              fill="#ff6b70"
            >
              有证即用 / 盖后补验
            </text>
          </PrimitiveStep>
        ) : null}
        <PrimitiveStep index={5} progress={opacity}>
          <rect
            x={x + 18}
            y={ruleY}
            width={w - 36}
            height={52}
            rx={14}
            fill="#061b28"
            stroke="#1f526b"
            strokeWidth={2.4}
          />
          <rect
            x={x + 30}
            y={ruleY + 11}
            width={62}
            height={24}
            rx={12}
            fill="#2a2e26"
            stroke="#f5a623"
            strokeWidth={1.4}
          />
          <TextLines
            text={ruleTitle}
            x={x + 61}
            y={ruleY + 28}
            size={13}
            fill="#ffb832"
          />
          <TextLines
            text={ruleMain}
            x={x + 106}
            y={ruleY + 24}
            size={mainSize}
            fill="#eaf8ff"
            anchor="start"
          />
          <TextLines
            text={ruleSub}
            x={x + 106}
            y={ruleY + 43}
            size={subSize}
            fill="#b9e7f8"
            weight={850}
            anchor="start"
          />
        </PrimitiveStep>
      </g>
    );
  }
  if (node.kind === "lifting_threshold_board") {
    const mode = node.mode || "overview";
    const poster = h >= 420;
    const narrow = w < 500;
    const baseY = y + (poster ? 380 : 170);
    const towerX = x + (poster ? 128 : 102);
    const jibY = y + (poster ? 116 : 58);
    const hookX = x + (poster ? 282 : 248);
    const loadY = y + (poster ? 284 : 130);
    const axisX = x + 34;
    const loadW = poster ? 96 : 76;
    const loadH = poster ? 56 : 46;
    const ruleY = y + h - (poster ? 100 : 55);
    const ruleTitle = node.rule_title || "判定";
    const ruleMain = node.rule_main || "先过门，再起吊";
    const ruleSub = node.rule_sub || "危大、条件、试吊、限位合格后放行";
    const mainSize = fitFontSize(ruleMain, w - 132, 19, 12);
    const subSize = fitFontSize(ruleSub, w - 132, 12, 9);
    const showDanger = [
      "overview",
      "gate_map",
      "danger",
      "score",
      "closing",
    ].includes(mode);
    const showCondition = ["gate_map", "precheck", "score", "closing"].includes(
      mode,
    );
    const showTrial = ["trial", "score", "closing"].includes(mode);
    const showLimit = ["limit", "qa", "score", "closing"].includes(mode);
    const wrong = mode === "limit" || mode === "qa";
    const showDangerCompare = mode === "danger";
    const showFourGateMap = mode === "gate_map";
    const showConditionGrid = mode === "precheck";
    const showTrialBand = mode === "trial";
    const showLimitFault = mode === "limit";
    const showLiftingAnswer = mode === "score";
    return (
      <g style={common}>
        <PrimitiveStep index={0} progress={opacity}>
          <TextLines
            text={node.text || "正式起吊前四道门"}
            x={x + w / 2}
            y={y + 20}
            size={17}
            fill="#eaf8ff"
          />
          <g data-visual-signature-part="crane_load">
            <path
              d={`M${x + 28} ${baseY} H${x + w - 22}`}
              stroke="#c8f0ff"
              strokeWidth={3}
              strokeLinecap="round"
            />
            <path
              d={`M${towerX - 52} ${baseY} H${towerX + 72} M${towerX - 42} ${baseY + 11} H${towerX - 6} M${towerX + 22} ${baseY + 11} H${towerX + 60}`}
              stroke="#c8f0ff"
              strokeWidth={4.4}
              strokeLinecap="round"
            />
            <rect
              x={towerX - 34}
              y={baseY - 22}
              width={68}
              height={22}
              rx={5}
              fill="#092435"
              stroke="#c8f0ff"
              strokeWidth={2.6}
            />
            <path
              d={`M${towerX} ${baseY} V${jibY} H${hookX + 92}`}
              stroke="#e8f8ff"
              strokeWidth={4.6}
              fill="none"
              strokeLinecap="round"
            />
            <path
              d={`M${towerX + 12} ${jibY + 26} L${towerX + 78} ${jibY} M${towerX + 38} ${baseY} L${towerX + 112} ${jibY}`}
              stroke="#65d4ff"
              strokeWidth={3}
              strokeDasharray="8 6"
            />
            <path
              d={`M${towerX + 20} ${jibY + 54} L${hookX - 10} ${jibY} M${towerX + 54} ${jibY + 98} L${hookX + 62} ${jibY}`}
              stroke="#235270"
              strokeWidth={2}
              strokeDasharray="8 7"
            />
            <path
              d={`M${hookX} ${jibY} V${loadY - 27}`}
              stroke="#9ee8ff"
              strokeWidth={3}
            />
            <path
              d={`M${hookX - 12} ${loadY - 27} h24 l-6 16 h-12 z`}
              fill="#092435"
              stroke="#9ee8ff"
              strokeWidth={2.4}
            />
            <path
              d={`M${hookX - 20} ${loadY - 10} L${hookX - loadW / 2} ${loadY + 12} M${hookX + 20} ${loadY - 10} L${hookX + loadW / 2} ${loadY + 12}`}
              stroke="#9ee8ff"
              strokeWidth={2.8}
              strokeLinecap="round"
            />
            <rect
              x={hookX - loadW / 2}
              y={loadY - 10}
              width={loadW}
              height={loadH}
              rx={9}
              fill="#0b2e3f"
              stroke="#ffb184"
              strokeWidth={3.4}
            />
            <path
              d={`M${hookX - loadW / 2 + 10} ${loadY + loadH - 1} H${hookX + loadW / 2 - 10}`}
              stroke="#ffcfb5"
              strokeWidth={3}
              strokeLinecap="round"
            />
            <TextLines
              text="12kN"
              x={hookX}
              y={loadY + 20}
              size={18}
              fill="#ffcfb5"
            />
          </g>
        </PrimitiveStep>
        {showDanger ? (
          <PrimitiveStep index={1} progress={opacity} trace>
            <g data-visual-signature-part="lifting_thresholds">
              <path
                d={`M${axisX} ${baseY - 103} V${baseY - 16}`}
                stroke="#6bc9f5"
                strokeWidth={2.4}
              />
              <path
                d={`M${axisX - 7} ${baseY - 95} l7 -14 l7 14 M${axisX - 7} ${baseY - 29} l7 14 l7 -14`}
                stroke="#6bc9f5"
                strokeWidth={2.4}
                fill="none"
                strokeLinecap="round"
              />
              <circle cx={axisX} cy={baseY - 73} r={5} fill="#f5a623" />
              <path
                d={`M${axisX} ${baseY - 73} H${x + w - 38}`}
                stroke="#f5a623"
                strokeWidth={3}
                strokeDasharray="8 7"
              />
              <text
                x={x + w - 34}
                y={baseY - 69}
                textAnchor="end"
                fontSize={13}
                fontWeight={950}
                fill="#ffb832"
              >
                {narrow ? "≥10kN" : "危大 ≥10kN"}
              </text>
              <circle cx={axisX} cy={baseY - 28} r={5} fill="#ff5b61" />
              <path
                d={`M${axisX} ${baseY - 28} H${x + w - 38}`}
                stroke="#ff5b61"
                strokeWidth={3}
                strokeDasharray="8 7"
              />
              <text
                x={x + w - 34}
                y={baseY - 24}
                textAnchor="end"
                fontSize={13}
                fontWeight={950}
                fill="#ff6b70"
              >
                {narrow ? "论证" : "论证另判"}
              </text>
            </g>
          </PrimitiveStep>
        ) : null}
        {showDangerCompare ? (
          <PrimitiveStep index={1} progress={opacity}>
            <g data-visual-signature-part="danger_threshold_compare">
              <rect
                x={hookX - loadW / 2 - 8}
                y={loadY - 18}
                width={loadW + 16}
                height={loadH + 16}
                rx={14}
                fill="none"
                stroke="#f5a623"
                strokeWidth={3.4}
                strokeDasharray="8 6"
              />
              <path
                d={`M${hookX + loadW / 2 + 12} ${loadY + 6} H${x + w - 170}`}
                stroke="#f5a623"
                strokeWidth={3.2}
                strokeDasharray="8 7"
              />
              <circle
                cx={hookX + loadW / 2 + 20}
                cy={loadY + 6}
                r={5}
                fill="#f5a623"
              />
            </g>
          </PrimitiveStep>
        ) : null}
        {showFourGateMap ? (
          <PrimitiveStep index={2} progress={opacity}>
            <g data-visual-signature-part="four_gate_map">
              {["危大线", "作业条件", "90%试吊", "限位装置"].map(
                (label, row) => (
                  <g key={label}>
                    <rect
                      x={x + 46 + row * 80}
                      y={y + 90}
                      width={68}
                      height={46}
                      rx={12}
                      fill="#061b28"
                      stroke={row === 0 ? "#f5a623" : "#65d4ff"}
                      strokeWidth={2.5}
                    />
                    <TextLines
                      text={label}
                      x={x + 80 + row * 80}
                      y={y + 118}
                      size={10}
                      fill={row === 0 ? "#ffb832" : "#9ee8ff"}
                    />
                  </g>
                ),
              )}
              <path
                d={`M${x + 114} ${y + 113} H${x + 286}`}
                stroke="#65d4ff"
                strokeWidth={3}
                strokeDasharray="7 6"
              />
            </g>
          </PrimitiveStep>
        ) : null}
        {showCondition ? (
          <PrimitiveStep index={2} progress={opacity}>
            <g data-visual-signature-part="site_condition_panel">
              <rect
                x={x + 244}
                y={y + 50}
                width={118}
                height={68}
                rx={12}
                fill="#061b28"
                stroke="#1f526b"
                strokeWidth={2.2}
              />
              <path
                d={`M${x + 260} ${y + 78} h72`}
                stroke="#65d4ff"
                strokeWidth={3}
                strokeLinecap="round"
              />
              <path
                d={`M${x + 296} ${y + 78} c12 -16 28 -16 40 0`}
                stroke="#f5a623"
                strokeWidth={3}
                fill="none"
              />
              <TextLines
                text="风 / 基础 / 警戒"
                x={x + 303}
                y={y + 106}
                size={12}
                fill="#9ee8ff"
              />
            </g>
          </PrimitiveStep>
        ) : null}
        {showConditionGrid ? (
          <PrimitiveStep index={2} progress={opacity}>
            <g data-visual-signature-part="site_condition_scan_grid">
              <rect
                x={x + 44}
                y={y + 70}
                width={170}
                height={82}
                rx={12}
                fill="#061b28"
                stroke="#1f526b"
                strokeWidth={2.5}
              />
              {["风", "地基", "警戒", "信号"].map((label, row) => (
                <g key={label}>
                  <circle
                    cx={x + 68 + (row % 2) * 78}
                    cy={y + 96 + Math.floor(row / 2) * 32}
                    r={10}
                    fill="#092435"
                    stroke={row < 3 ? "#19c37d" : "#f5a623"}
                    strokeWidth={2.5}
                  />
                  <TextLines
                    text={label}
                    x={x + 91 + (row % 2) * 78}
                    y={y + 101 + Math.floor(row / 2) * 32}
                    size={10}
                    fill="#eaf8ff"
                  />
                </g>
              ))}
            </g>
          </PrimitiveStep>
        ) : null}
        {showTrial ? (
          <PrimitiveStep index={3} progress={opacity} trace>
            <g data-visual-signature-part="trial_lift_axis">
              <path
                d={`M${hookX + 62} ${loadY + 34} V${loadY - 8}`}
                stroke="#6bc9f5"
                strokeWidth={2.4}
              />
              <path
                d={`M${hookX + 56} ${loadY + 26} l6 12 l6 -12 M${hookX + 56} ${loadY + 4} l6 -12 l6 12`}
                stroke="#6bc9f5"
                strokeWidth={2.4}
                fill="none"
              />
              <text
                x={poster ? hookX + 48 : hookX + 70}
                y={poster ? loadY - 18 : loadY + 16}
                fontSize={poster ? 11 : 12}
                fontWeight={950}
                fill="#9ee8ff"
              >
                200-500mm
              </text>
              <path
                d={`M${x + 176} ${baseY - 3} H${x + 302}`}
                stroke="#19c37d"
                strokeWidth={4}
                strokeDasharray="8 7"
              />
              <TextLines
                text="离地四查"
                x={x + 236}
                y={baseY + 17}
                size={12}
                fill="#19d58c"
              />
            </g>
          </PrimitiveStep>
        ) : null}
        {showTrialBand ? (
          <PrimitiveStep index={3} progress={opacity}>
            <g data-visual-signature-part="trial_lift_measure_band">
              <rect
                x={x + 210}
                y={loadY - 2}
                width={98}
                height={34}
                rx={17}
                fill="#093522"
                stroke="#19c37d"
                strokeWidth={3}
              />
              <TextLines
                text="先离地四查"
                x={x + 259}
                y={loadY + 20}
                size={11}
                fill="#9bf3c8"
              />
              <path
                d={`M${x + 270} ${baseY - 7} H${x + 318}`}
                stroke="#19c37d"
                strokeWidth={5}
                strokeDasharray="8 7"
              />
            </g>
          </PrimitiveStep>
        ) : null}
        {showLimit ? (
          <PrimitiveStep index={4} progress={opacity}>
            <g data-visual-signature-part="limit_stop_release">
              <rect
                x={x + 254}
                y={y + 124}
                width={110}
                height={48}
                rx={12}
                fill="#092435"
                stroke={wrong ? "#ff5b61" : "#19c37d"}
                strokeWidth={2.8}
              />
              <TextLines
                text={wrong ? "限位故障" : "合格放行"}
                x={x + 309}
                y={y + 154}
                size={12}
                fill={wrong ? "#ff6b70" : "#9bf3c8"}
              />
              {wrong ? (
                <path
                  d={`M${x + 268} ${y + 132} L${x + 350} ${y + 166} M${x + 350} ${y + 132} L${x + 268} ${y + 166}`}
                  stroke="#ff5b61"
                  strokeWidth={4}
                  strokeLinecap="round"
                />
              ) : (
                <>
                  <circle cx={x + 270} cy={y + 148} r={9} fill="#19c37d" />
                  <path
                    d={`M${x + 265} ${y + 148} l4 5 l9 -12`}
                    stroke="#061b28"
                    strokeWidth={3}
                    fill="none"
                    strokeLinecap="round"
                  />
                </>
              )}
            </g>
            {showLimitFault ? (
              <g data-visual-signature-part="limit_fault_lockout">
                <rect
                  x={x + 76}
                  y={y + 72}
                  width={126}
                  height={48}
                  rx={14}
                  fill="#2b0f18"
                  stroke="#ff5b61"
                  strokeWidth={3}
                />
                <TextLines
                  text="限位失灵，禁吊"
                  x={x + 139}
                  y={y + 101}
                  size={12}
                  fill="#ff9aa0"
                />
              </g>
            ) : null}
          </PrimitiveStep>
        ) : null}
        {showLiftingAnswer ? (
          <PrimitiveStep index={4} progress={opacity}>
            <g data-visual-signature-part="lifting_answer_chain">
              <rect
                x={x + 42}
                y={y + 62}
                width={180}
                height={92}
                rx={12}
                fill="#061b28"
                stroke="#65d4ff"
                strokeWidth={2.5}
              />
              {["危大成立", "条件合格", "90%试吊四查", "限位正常"].map(
                (label, row) => (
                  <g key={label}>
                    <path
                      d={`M${x + 60} ${y + 88 + row * 18} H${x + 202}`}
                      stroke={row === 0 ? "#f5a623" : "#19c37d"}
                      strokeWidth={3}
                      strokeLinecap="round"
                    />
                    <TextLines
                      text={label}
                      x={x + 70}
                      y={y + 84 + row * 18}
                      size={9}
                      fill="#eaf8ff"
                      anchor="start"
                    />
                  </g>
                ),
              )}
            </g>
          </PrimitiveStep>
        ) : null}
        <PrimitiveStep index={5} progress={opacity}>
          <rect
            x={x + 18}
            y={ruleY}
            width={w - 36}
            height={52}
            rx={14}
            fill="#061b28"
            stroke="#1f526b"
            strokeWidth={2.4}
          />
          <rect
            x={x + 30}
            y={ruleY + 11}
            width={62}
            height={24}
            rx={12}
            fill="#2a2e26"
            stroke="#f5a623"
            strokeWidth={1.4}
          />
          <TextLines
            text={ruleTitle}
            x={x + 61}
            y={ruleY + 28}
            size={13}
            fill="#ffb832"
          />
          <TextLines
            text={ruleMain}
            x={x + 106}
            y={ruleY + 24}
            size={mainSize}
            fill="#eaf8ff"
            anchor="start"
          />
          <TextLines
            text={ruleSub}
            x={x + 106}
            y={ruleY + 43}
            size={subSize}
            fill="#b9e7f8"
            weight={850}
            anchor="start"
          />
        </PrimitiveStep>
      </g>
    );
  }
  if (node.kind === "grade_threshold_board") {
    // Generic graded-axis classification board. Mirrors the Python
    // _grade_threshold_board: title -> one graded axis per `axes` entry with a
    // probe marker at hit_index band -> result light. Nothing domain-specific
    // is hardcoded; all text comes from node data.
    // primitive_steps DOM ordering (must match Python):
    //   index 0      -> title reveal
    //   index 1..n   -> probe-slide for axis i (i=0..n-1), trace sweep
    //   index n+1    -> take-highest / result-light reveal (final)
    const title = node.text || "量尺取档";
    const ruleMain = node.rule_main || "任一达高级即按高级";
    const rawAxes =
      Array.isArray(node.axes) && node.axes.length ? node.axes : [];
    const axes = (
      rawAxes.length
        ? rawAxes
        : labelsWithDefaults(node, ["指标一", "指标二", "指标三"], 3).map(
            (name) => ({
              name,
              bands: ["一般", "较大", "重大", "特别重大"],
              probe: "—",
              hit_index: 0,
            }),
          )
    ).slice(0, 4);
    const resultLabel = node.result?.label || "—";
    const titleSize = fitFontSize(title, w - 24, 16, 12);
    const ruleY = y + h - 38;
    const axesTop = y + 36;
    const axesBottom = ruleY - 8;
    const rowGap = (axesBottom - axesTop) / Math.max(axes.length, 1);
    const nameW = w * 0.26;
    const trackX = x + 14 + nameW;
    const trackW = w * 0.62;
    const trackRight = trackX + trackW;
    return (
      <g style={common}>
        <PrimitiveStep index={0} progress={opacity}>
          <rect
            data-visual-signature-part="board-frame"
            x={x}
            y={y}
            width={w}
            height={h}
            rx={16}
            fill={tones.neutral.fill}
            stroke={tones.neutral.stroke}
            strokeWidth={2.2}
          />
          <TextLines
            text={title}
            x={x + w / 2}
            y={y + 20}
            size={titleSize}
            fill={tones.neutral.text}
          />
        </PrimitiveStep>
        {axes.map((axis, i) => {
          const name = axis?.name || `指标${i + 1}`;
          const bands = (
            (axis?.bands || []).filter((b): b is string => b != null).length
              ? (axis?.bands as string[])
              : ["一般", "较大", "重大", "特别重大"]
          ).slice(0, 5);
          const probe = axis?.probe || "—";
          const hitIndex = Math.max(
            0,
            Math.min(Number(axis?.hit_index ?? 0) || 0, bands.length - 1),
          );
          const rowCy = axesTop + rowGap * i + rowGap / 2;
          const trackY = rowCy - 8;
          const cellW = trackW / bands.length;
          const nameSize = fitFontSize(name, nameW + 2, 13, 11);
          const probeCx = trackX + cellW * hitIndex + cellW / 2;
          const probeTone =
            probe && probe !== "—" ? tones.success : tones.amber;
          const probeSize = fitFontSize(probe, cellW + 24, 11, 11);
          return (
            <g key={`axis-${i}`}>
              <g data-visual-signature-part="grade-axis">
                <TextLines
                  text={name}
                  x={x + 12}
                  y={rowCy + 4}
                  size={nameSize}
                  fill={tones.neutral.text}
                  anchor="start"
                />
                {bands.map((band, bIdx) => {
                  const cx = trackX + cellW * bIdx;
                  const hit = bIdx === hitIndex;
                  const cellTone = hit ? tones.success : tones.neutral;
                  return (
                    <g key={`band-${i}-${bIdx}`}>
                      <rect
                        x={cx}
                        y={trackY}
                        width={cellW}
                        height={16}
                        fill={cellTone.fill}
                        stroke={cellTone.stroke}
                        strokeWidth={hit ? 2 : 1}
                      />
                      <TextLines
                        text={band}
                        x={cx + cellW / 2}
                        y={trackY + 12}
                        size={fitFontSize(band, cellW + 4, 11, 11)}
                        fill={cellTone.text}
                        weight={800}
                      />
                    </g>
                  );
                })}
              </g>
              <PrimitiveStep index={i + 1} progress={opacity} trace>
                <path
                  d={`M${trackX} ${trackY - 9} H${probeCx}`}
                  stroke={probeTone.stroke}
                  strokeWidth={2.4}
                  strokeDasharray="5 4"
                />
                <path
                  d={`M${probeCx} ${trackY - 12} l-5 -8 h10 z`}
                  fill={probeTone.stroke}
                />
                <LabelBadge
                  text={probe}
                  cx={probeCx}
                  cy={trackY - 18}
                  tone={probeTone}
                  size={probeSize}
                />
              </PrimitiveStep>
            </g>
          );
        })}
        <PrimitiveStep index={axes.length + 1} progress={opacity}>
          <g data-visual-signature-part="result-light">
            <rect
              x={x + 14}
              y={ruleY}
              width={w - 28}
              height={30}
              rx={11}
              fill={tones.danger.fill}
              stroke={tones.danger.stroke}
              strokeWidth={2}
            />
            <TextLines
              text={ruleMain}
              x={x + 18}
              y={ruleY + 19}
              size={fitFontSize(ruleMain, (w - 28) * 0.58, 12, 11)}
              fill={tones.danger.text}
              weight={850}
              anchor="start"
            />
            <LabelBadge
              text={resultLabel}
              cx={trackRight - 4}
              cy={ruleY + 15}
              tone={tones.danger}
              size={12}
            />
          </g>
        </PrimitiveStep>
      </g>
    );
  }
  if (node.kind === "network_graph") {
    const labels = labelsWithDefaults(node, ["A", "B", "C", "D"], 4);
    const coords: Array<[number, number]> = [
      [x + 36, y + 118],
      [x + 112, y + 72],
      [x + 112, y + 164],
      [x + 206, y + 118],
      [x + 282, y + 118],
    ];
    const nodeLabels = ["始", labels[0], labels[1], labels[2], "终"];
    return (
      <g style={common}>
        <PrimitiveStep index={0} progress={opacity}>
          <TextLines
            text={node.text || "图上推演"}
            x={x + w / 2}
            y={y + 32}
            size={16}
            fill={t.text}
          />
        </PrimitiveStep>
        <PrimitiveStep index={1} progress={opacity} trace>
          <path
            d={`M${coords[0][0] + 24} ${coords[0][1]} C${x + 78} ${y + 116} ${x + 72} ${y + 76} ${coords[1][0] - 24} ${coords[1][1]}`}
            stroke="#94a3b8"
            strokeWidth={5}
            fill="none"
          />
        </PrimitiveStep>
        <PrimitiveStep index={2} progress={opacity} trace>
          <path
            d={`M${coords[0][0] + 24} ${coords[0][1]} C${x + 78} ${y + 120} ${x + 72} ${y + 164} ${coords[2][0] - 24} ${coords[2][1]}`}
            stroke="#cbd5e1"
            strokeWidth={5}
            fill="none"
          />
        </PrimitiveStep>
        <PrimitiveStep index={3} progress={opacity} trace>
          <path
            d={`M${coords[1][0] + 24} ${coords[1][1]} H${coords[3][0] - 24} M${coords[2][0] + 24} ${coords[2][1]} C${x + 164} ${y + 164} ${x + 166} ${y + 122} ${coords[3][0] - 24} ${coords[3][1]}`}
            stroke={colors.blue}
            strokeWidth={5}
            fill="none"
          />
        </PrimitiveStep>
        <PrimitiveStep index={4} progress={opacity} trace>
          <path
            d={`M${coords[3][0] + 24} ${coords[3][1]} H${coords[4][0] - 24}`}
            stroke={colors.teal}
            strokeWidth={5}
            fill="none"
          />
        </PrimitiveStep>
        {coords.map(([cx, cy], index) => (
          <PrimitiveStep key={index} index={index + 5} progress={opacity}>
            <rect
              x={cx - 25}
              y={cy - 20}
              width={50}
              height={40}
              rx={12}
              fill={index === 0 || index === 4 ? "#fff7ed" : "#eff6ff"}
              stroke={index === 0 || index === 4 ? "#f97316" : colors.blue}
              strokeWidth={3}
            />
            <TextLines
              text={nodeLabels[index]}
              x={cx}
              y={cy + 5}
              size={13}
              fill="#172033"
            />
          </PrimitiveStep>
        ))}
      </g>
    );
  }
  if (node.kind === "formula_chain") {
    const labels = labelsWithDefaults(
      node,
      ["口径", "数量", "单价", "扣减"],
      4,
    );
    const startX = x + 34;
    const boxW = Math.max(48, (w - 92) / Math.max(labels.length, 1));
    return (
      <g style={common}>
        <PrimitiveStep index={0} progress={opacity}>
          <TextLines
            text={node.text || "计算口径"}
            x={x + w / 2}
            y={y + 44}
            size={16}
            fill={t.text}
          />
        </PrimitiveStep>
        {labels.map((label, index) => {
          const bx = startX + index * (boxW + 12);
          return (
            <PrimitiveStep
              key={`${label}-${index}`}
              index={index + 1}
              progress={opacity}
              trace={index < labels.length - 1}
            >
              <rect
                x={bx}
                y={y + 82}
                width={boxW}
                height={48}
                rx={14}
                fill="#fff7ed"
                stroke="#f59e0b"
                strokeWidth={3}
              />
              <TextLines
                text={label}
                x={bx + boxW / 2}
                y={y + 112}
                size={fitFontSize(label, boxW, 13, 10)}
                fill="#b45309"
              />
              {index < labels.length - 1 ? (
                <path
                  d={`M${bx + boxW + 3} ${y + 106} H${bx + boxW + 13}`}
                  stroke="#f97316"
                  strokeWidth={4}
                  strokeLinecap="round"
                />
              ) : null}
            </PrimitiveStep>
          );
        })}
        <PrimitiveStep index={labels.length + 1} progress={opacity} trace>
          <path
            d={`M${x + 56} ${y + 170} H${x + w - 56}`}
            stroke="#f97316"
            strokeWidth={6}
            strokeLinecap="round"
          />
        </PrimitiveStep>
      </g>
    );
  }
  if (node.kind === "decision_tree") {
    const labels = labelsWithDefaults(
      node,
      ["对象", "条件", "阈值", "结论"],
      4,
    );
    const gateY = y + 100;
    return (
      <g style={common}>
        <PrimitiveStep index={0} progress={opacity}>
          <TextLines
            text={node.text || "判断树"}
            x={x + w / 2}
            y={y + 20}
            size={16}
            fill={t.text}
          />
        </PrimitiveStep>
        <PrimitiveStep index={1} progress={opacity}>
          <rect
            x={x + 66}
            y={y + 30}
            width={w - 132}
            height={38}
            rx={13}
            fill="#ecfdf5"
            stroke={colors.teal}
            strokeWidth={3}
          />
          <TextLines
            text={labels[0]}
            x={x + w / 2}
            y={y + 55}
            size={13}
            fill="#047857"
          />
        </PrimitiveStep>
        {labels.slice(1, 4).map((label, index) => {
          const cx = x + 50 + index * ((w - 100) / 2);
          return (
            <PrimitiveStep
              key={`${label}-${index}`}
              index={index + 2}
              progress={opacity}
              trace
            >
              <path
                d={`M${x + w / 2} ${y + 68} V${gateY - 16} H${cx}`}
                stroke="#94a3b8"
                strokeWidth={3}
                fill="none"
              />
              <rect
                x={cx - 38}
                y={gateY}
                width={76}
                height={42}
                rx={12}
                fill="#f8fafc"
                stroke="#cbd5e1"
                strokeWidth={3}
              />
              <TextLines
                text={label}
                x={cx}
                y={gateY + 27}
                size={fitFontSize(label, 76, 12, 10)}
                fill="#334155"
              />
            </PrimitiveStep>
          );
        })}
      </g>
    );
  }
  if (node.kind === "contrast_pair") {
    const labels = labelsWithDefaults(
      node,
      ["错误做法", "正确做法", "错因", "采分"],
      4,
    );
    const left = labels[0] || "错误做法";
    const right = labels[1] || "正确做法";
    return (
      <g style={common}>
        <PrimitiveStep index={0} progress={opacity}>
          <TextLines
            text={node.text || "左右对照"}
            x={x + w / 2}
            y={y + 28}
            size={16}
            fill={t.text}
          />
        </PrimitiveStep>
        <PrimitiveStep index={1} progress={opacity}>
          <rect
            x={x + 20}
            y={y + 62}
            width={w / 2 - 30}
            height={102}
            rx={16}
            fill="#fff7ed"
            stroke="#f97316"
            strokeWidth={4}
          />
          <TextLines text="错" x={x + 42} y={y + 88} size={18} fill="#9a3412" />
          <TextLines
            text={left}
            x={x + 20 + (w / 2 - 30) / 2}
            y={y + 125}
            size={fitFontSize(left, w / 2 - 46, 14, 10)}
            fill="#9a3412"
          />
        </PrimitiveStep>
        <PrimitiveStep index={2} progress={opacity}>
          <rect
            x={x + w / 2 + 10}
            y={y + 62}
            width={w / 2 - 30}
            height={102}
            rx={16}
            fill="#ecfdf5"
            stroke={colors.teal}
            strokeWidth={4}
          />
          <TextLines
            text="对"
            x={x + w / 2 + 32}
            y={y + 88}
            size={18}
            fill="#047857"
          />
          <TextLines
            text={right}
            x={x + w / 2 + 10 + (w / 2 - 30) / 2}
            y={y + 125}
            size={fitFontSize(right, w / 2 - 46, 14, 10)}
            fill="#047857"
          />
        </PrimitiveStep>
        <PrimitiveStep index={3} progress={opacity} trace>
          <path
            d={`M${x + 32} ${y + 188} H${x + w - 32}`}
            stroke={colors.blue}
            strokeWidth={5}
            strokeLinecap="round"
            strokeDasharray="10 7"
          />
          <LabelBadge
            text={labels[3]}
            cx={x + w / 2}
            cy={y + 188}
            tone={toneOf("blue")}
            width={132}
            size={11}
          />
        </PrimitiveStep>
      </g>
    );
  }
  if (node.kind === "answer_scan") {
    const labels = labelsWithDefaults(
      node,
      ["对象", "条件", "依据", "采分句"],
      4,
    );
    const states = [
      ["#ecfdf5", colors.teal, "命中"],
      ["#fffbeb", "#f59e0b", "半中"],
      ["#fef2f2", colors.red, "漏"],
      ["#eff6ff", colors.blue, "补"],
    ];
    const rowTop = y + 62;
    const rowH = 28;
    const boardBottom = 240;
    const rowGap = Math.min(
      38,
      Math.max(
        28,
        (boardBottom - rowTop - rowH) / Math.max(labels.length - 1, 1),
      ),
    );
    return (
      <g style={common}>
        <PrimitiveStep index={0} progress={opacity}>
          <TextLines
            text={node.text || "答案逐句扫描"}
            x={x + w / 2}
            y={y + 34}
            size={16}
            fill={t.text}
          />
        </PrimitiveStep>
        {labels.map((label, index) => {
          const yy = rowTop + index * rowGap;
          const [fill, stroke, tag] = states[index % states.length];
          return (
            <PrimitiveStep
              key={`${label}-${index}`}
              index={index + 1}
              progress={opacity}
            >
              <rect
                x={x + 30}
                y={yy}
                width={w - 60}
                height={28}
                rx={9}
                fill={fill}
                stroke={stroke}
                strokeWidth={2}
              />
              <TextLines
                text={label}
                x={x + 44}
                y={yy + 19}
                size={12}
                fill="#172033"
                anchor="start"
              />
              <TextLines
                text={tag}
                x={x + w - 46}
                y={yy + 19}
                size={11}
                fill="#64748b"
              />
            </PrimitiveStep>
          );
        })}
      </g>
    );
  }
  if (node.kind === "memory_table") {
    const labels = labelsWithDefaults(
      node,
      ["数值", "条件", "例外", "记忆钩子"],
      4,
    );
    return (
      <g style={common}>
        <TextLines
          text={node.text || "参数辨析"}
          x={x + w / 2}
          y={y + 32}
          size={16}
          fill={t.text}
        />
        {labels.map((label, index) => {
          const yy = y + 58 + index * 36;
          return (
            <g key={`${label}-${index}`}>
              <rect
                x={x + 38}
                y={yy}
                width={w - 76}
                height={28}
                rx={8}
                fill="#f8fafc"
                stroke="#cbd5e1"
                strokeWidth={2}
              />
              <TextLines
                text={label}
                x={x + 56}
                y={yy + 19}
                size={12}
                fill="#334155"
                anchor="start"
              />
            </g>
          );
        })}
      </g>
    );
  }
  if (
    node.kind === "answer_box" ||
    node.kind === "dialogue_box" ||
    node.kind === "note"
  ) {
    const rx = node.kind === "note" ? 10 : 11;
    return (
      <g style={common}>
        <rect
          x={x}
          y={y}
          width={w}
          height={h}
          rx={rx}
          fill={t.fill}
          stroke={t.stroke}
          strokeWidth={2}
        />
        <TextLines
          text={node.text}
          x={x + w / 2}
          y={y + h / 2 + 5}
          size={13}
          fill={t.text}
        />
      </g>
    );
  }
  if (node.kind === "closing_text") {
    return (
      <g style={common}>
        <TextLines text={node.text} x={180} y={90} size={18} fill="#047857" />
        <TextLines
          text={node.subtext}
          x={180}
          y={132}
          size={19}
          fill={colors.text}
        />
      </g>
    );
  }
  if (node.kind === "challenge_button") {
    return (
      <g style={common}>
        <rect
          x={90}
          y={166}
          width={180}
          height={44}
          rx={22}
          fill={colors.amber}
        />
        <TextLines text={node.text} x={180} y={194} size={17} fill="#0f1722" />
      </g>
    );
  }
  if (node.kind === "flow_arrow") {
    const x1 = node.x1 ?? x;
    const x2 = node.x2 ?? x + w;
    const label = String(node.text || "");
    const badgeW = Math.max(54, Math.min(116, label.length * 12 * 0.92 + 22));
    let lineStart = label ? x1 + badgeW + 12 : x1;
    if (lineStart > x2 - 30) lineStart = x1;
    return (
      <g style={common}>
        <PrimitiveStep index={0} progress={opacity} trace>
          <path
            d={`M${lineStart} ${y} H${x2}`}
            stroke={t.stroke}
            strokeWidth={5}
            strokeLinecap="round"
          />
          <path
            d={`M${x2 - 12} ${y - 8} L${x2} ${y} L${x2 - 12} ${y + 8}`}
            fill="none"
            stroke={t.stroke}
            strokeWidth={5}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <LabelBadge
            text={label}
            cx={x1 + badgeW / 2}
            cy={y}
            tone={t}
            width={badgeW}
            size={12}
          />
        </PrimitiveStep>
      </g>
    );
  }
  if (node.kind === "threshold_meter") {
    const value = Math.max(0, Math.min(1, node.value ?? 0.62));
    const marker = x + w * value;
    const labelY = y + 52 > 244 ? y - 12 : y + 48;
    const labelSize = fitFontSize(node.text, w, 13, 10);
    return (
      <g style={common}>
        <PrimitiveStep index={0} progress={opacity} trace>
          <rect x={x} y={y} width={w} height={18} rx={9} fill="#e2e8f0" />
          <rect
            x={x}
            y={y}
            width={w * value}
            height={18}
            rx={9}
            fill={t.stroke}
            opacity={0.85}
          />
          <path
            d={`M${marker} ${y - 8} V${y + 30}`}
            stroke="#f97316"
            strokeWidth={4}
            strokeLinecap="round"
          />
          <TextLines
            text={node.text}
            x={x + w / 2}
            y={labelY}
            size={labelSize}
            fill={t.text}
          />
        </PrimitiveStep>
      </g>
    );
  }
  return null;
};

const Board: React.FC<{
  visual: VisualScene;
  scene: Scene;
  progress: number;
  layoutMode?: string;
}> = ({ visual, scene, progress, layoutMode }) => {
  const nodes = visual.nodes || [];
  const board = visual.board || "warm_grid";
  const isPaper = board === "paper";
  const isClosing = board === "closing";
  const isBlueprint = board === "blueprint";
  const isPoster =
    board === "blueprint_poster" || layoutMode === "blueprint_poster";
  const blueprintW = 420;
  const blueprintH = isPoster ? 640 : 300;
  const posterBadgeText = compactCaption(scene.keycard, 9);
  const posterBadgeW = Math.max(
    118,
    Math.min(170, posterBadgeText.length * 12 + 36),
  );
  return (
    <svg
      viewBox={
        isBlueprint || isPoster
          ? `0 0 ${blueprintW} ${blueprintH}`
          : "0 0 360 270"
      }
      style={{ width: "100%", height: "100%", display: "block" }}
    >
      {isPaper ? (
        <>
          <rect
            x="28"
            y="30"
            width="304"
            height="210"
            rx="18"
            fill="#fffdf7"
            stroke="#eadfcb"
            strokeWidth="4"
          />
          <TextLines
            text="答题纸这样写"
            x={54}
            y={72}
            size={15}
            fill="#176b7a"
            anchor="start"
          />
        </>
      ) : isBlueprint || isPoster ? (
        <>
          <rect
            x="0"
            y="0"
            width={blueprintW}
            height={blueprintH}
            fill="#092434"
          />
          <path
            d={
              isPoster
                ? "M0 44 H420 M0 104 H420 M0 164 H420 M0 224 H420 M0 284 H420 M0 344 H420 M0 404 H420 M0 464 H420 M0 524 H420 M0 584 H420 M52 0 V640 M132 0 V640 M212 0 V640 M292 0 V640 M372 0 V640"
                : "M0 40 H420 M0 100 H420 M0 160 H420 M0 220 H420 M52 0 V300 M132 0 V300 M212 0 V300 M292 0 V300 M372 0 V300"
            }
            stroke="#123447"
            strokeWidth={1.1}
            opacity={0.72}
          />
          <rect
            x="10"
            y={isPoster ? 16 : 14}
            width="400"
            height={isPoster ? 608 : 272}
            rx="24"
            fill="none"
            stroke="#235270"
            strokeWidth={2}
          />
          {isPoster ? (
            <>
              <rect
                x="28"
                y="36"
                width={posterBadgeW}
                height="30"
                rx="15"
                fill="#2a2e26"
                stroke="#f5a623"
                strokeWidth={1.6}
              />
              <TextLines
                text={posterBadgeText}
                x={28 + posterBadgeW / 2}
                y={56}
                size={fitFontSize(posterBadgeText, posterBadgeW, 12, 10)}
                fill="#ffb832"
              />
              <TextLines
                text={scene.label}
                x={Math.max(210, 28 + posterBadgeW + 36)}
                y={60}
                size={22}
                fill="#eaf8ff"
              />
            </>
          ) : null}
        </>
      ) : isClosing ? (
        <rect
          x="24"
          y="34"
          width="312"
          height="198"
          rx="22"
          fill="#ecfdf5"
          stroke={colors.teal}
          strokeWidth="3"
        />
      ) : (
        <>
          <rect
            x="12"
            y="18"
            width="336"
            height="234"
            rx="22"
            fill={colors.panel}
            stroke={colors.line}
            strokeWidth="3"
          />
          <path
            d="M44 66 H316 M44 120 H316 M44 174 H316 M88 40 V230 M180 40 V230 M272 40 V230"
            stroke={colors.grid}
            strokeWidth="1.2"
          />
        </>
      )}
      <g>
        {nodes.map((node, index) => (
          <PrimitiveStepContext.Provider
            key={node.id}
            value={{
              nodeId: node.id,
              steps: node.primitive_steps || [],
              actions: scene.actions || [],
            }}
          >
            <g
              data-visible-node={node.id}
              data-visual-node-id={node.id}
              data-visual-kind={node.kind}
              data-visual-mode={node.mode || "default"}
              data-visual-signature={visualSignature(node)}
            >
              <Primitive
                node={node}
                opacity={nodeReveal(node, scene, progress, index)}
                highlighted={nodeHighlighted(node, scene, progress)}
              />
            </g>
          </PrimitiveStepContext.Provider>
        ))}
      </g>
    </svg>
  );
};

export const animationIrDurationFrames = (ir: AnimationIr, fps: number) =>
  Math.ceil(ir.scenes[ir.scenes.length - 1].end_sec * fps);

export const AnimationIrRenderer: React.FC<AnimationIrRendererProps> = ({
  ir,
  timing,
  title,
  kicker,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const second = frame / fps;
  const scene = activeSceneAt(ir.scenes, second);
  const duration = Math.max(0.001, scene.end_sec - scene.start_sec);
  const progress = clamp((second - scene.start_sec) / duration);
  const visual = ir.visual_library?.[scene.id] || { nodes: [] };
  const segment = activeSegmentAt(timing?.segments, second);
  const displayTitle = title || ir.display?.title || ir.card_id;
  const displayKicker = kicker || ir.display?.kicker || "鲁班深母题";
  const visualBrief = ir.render_contract?.caption_mode === "visual_brief";
  const layoutMode = ir.render_contract?.layout_mode;
  const blueprintPoster = visualBrief && layoutMode === "blueprint_poster";
  const cameraAction = (scene.actions || []).find(
    (action) => action.kind === "camera",
  );
  const cameraProgress = ease(
    (progress - (cameraAction?.start || 0)) /
      Math.max(0.04, (cameraAction?.end || 0.32) - (cameraAction?.start || 0)),
  );
  const cameraVerb = cameraAction?.verb || scene.camera?.verb || "spotlight";
  const scaleTarget = blueprintPoster
    ? 1
    : cameraVerb === "pull-back"
      ? 0.98
      : cameraVerb === "freeze-frame"
        ? 1.04
        : 1.03;
  const boardScale = blueprintPoster
    ? 1
    : interpolate(cameraProgress, [0, 1], [0.985, scaleTarget], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      });
  const maxCaptionChars = Number(ir.render_contract?.max_caption_chars || 42);
  const briefCoach = compactCaption(
    visualBrief ? scene.caption || scene.keycard : scene.coach,
    Number.isFinite(maxCaptionChars) ? maxCaptionChars : 42,
  );
  const segmentText = visualBrief ? "" : segment?.text;

  if (blueprintPoster) {
    return (
      <AbsoluteFill
        style={{
          backgroundColor: colors.bg,
          color: "#eef3f8",
          fontFamily: "PingFang SC, Microsoft YaHei, Arial",
          backgroundImage:
            "linear-gradient(rgba(35,82,112,.22) 1px, transparent 1px), linear-gradient(90deg, rgba(35,82,112,.22) 1px, transparent 1px)",
          backgroundSize: "82px 82px",
        }}
      >
        <div
          style={{
            padding: "30px 46px 28px",
            height: "100%",
            display: "grid",
            gridTemplateRows: "auto minmax(0, 1fr) auto",
            gap: 18,
          }}
        >
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr auto",
              alignItems: "end",
              columnGap: 24,
            }}
          >
            <div style={{ minWidth: 0 }}>
              <div
                style={{ color: colors.amber, fontSize: 20, fontWeight: 950 }}
              >
                {displayKicker}
              </div>
              <div
                style={{
                  fontSize: 37,
                  fontWeight: 950,
                  lineHeight: 1.06,
                  marginTop: 4,
                }}
              >
                {displayTitle}
              </div>
            </div>
            <div
              style={{
                border: "2px solid #235270",
                borderRadius: 16,
                padding: "9px 14px",
                color: "#9ee8ff",
                fontSize: 18,
                fontWeight: 900,
                maxWidth: 285,
                lineHeight: 1.2,
                textAlign: "right",
              }}
            >
              {briefCoach}
            </div>
          </div>
          <div
            style={{
              borderRadius: 30,
              background: "#092434",
              border: "4px solid #235270",
              overflow: "hidden",
              display: "grid",
              placeItems: "stretch",
              minHeight: 0,
              transform: `scale(${boardScale})`,
              boxShadow: "0 22px 64px rgba(0,0,0,.28)",
            }}
          >
            <Board
              visual={visual}
              scene={scene}
              progress={progress}
              layoutMode={layoutMode}
            />
          </div>
          <div style={{ display: "flex", gap: 10, height: 18 }}>
            {ir.scenes.map((item) => (
              <div
                key={item.id}
                style={{
                  flex: 1,
                  borderRadius: 16,
                  background: item.id === scene.id ? colors.amber : "#223147",
                }}
              />
            ))}
          </div>
        </div>
      </AbsoluteFill>
    );
  }

  return (
    <AbsoluteFill
      style={{
        backgroundColor: colors.bg,
        color: "#eef3f8",
        fontFamily: "PingFang SC, Microsoft YaHei, Arial",
      }}
    >
      <div
        style={{
          padding: visualBrief ? "44px 58px 38px" : 72,
          height: "100%",
          display: "grid",
          gridTemplateRows: "auto 1fr auto auto",
          gap: visualBrief ? 18 : 30,
        }}
      >
        <div>
          <div
            style={{
              color: colors.amber,
              fontSize: visualBrief ? 24 : 30,
              fontWeight: 900,
            }}
          >
            {displayKicker}
          </div>
          <div
            style={{
              fontSize: visualBrief ? 50 : 70,
              fontWeight: 950,
              lineHeight: 1.04,
              marginTop: visualBrief ? 8 : 14,
            }}
          >
            {displayTitle}
          </div>
          {visualBrief ? null : (
            <div
              style={{
                color: "#9fb0c2",
                fontSize: 31,
                fontWeight: 850,
                lineHeight: 1.45,
                marginTop: 20,
              }}
            >
              {ir.main_exam_action}
            </div>
          )}
        </div>
        <div
          style={{
            borderRadius: visualBrief ? 34 : 44,
            background: "#111d2a",
            border: "3px solid #26384d",
            overflow: "hidden",
            display: "grid",
            placeItems: "center",
            alignSelf: visualBrief ? "center" : "center",
            width: "100%",
            height: visualBrief ? 1160 : undefined,
            aspectRatio: visualBrief ? undefined : "420 / 300",
            transform: `scale(${boardScale})`,
          }}
        >
          <Board
            visual={visual}
            scene={scene}
            progress={progress}
            layoutMode={layoutMode}
          />
        </div>
        <div
          style={{
            borderLeft: `13px solid ${colors.amber}`,
            background: "#172434",
            borderRadius: 30,
            padding: "26px 32px",
            boxShadow: "0 28px 70px rgba(0,0,0,.28)",
          }}
        >
          {visualBrief ? (
            <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
              <div
                style={{
                  color: colors.amber,
                  border: `3px solid ${colors.amber}`,
                  borderRadius: 999,
                  padding: "10px 18px",
                  minWidth: 150,
                  textAlign: "center",
                  fontSize: 23,
                  fontWeight: 950,
                  lineHeight: 1.12,
                }}
              >
                {compactCaption(scene.keycard, 10)}
              </div>
              <div style={{ fontSize: 30, fontWeight: 950, lineHeight: 1.2 }}>
                {briefCoach}
              </div>
            </div>
          ) : (
            <>
              <div
                style={{ color: colors.amber, fontSize: 29, fontWeight: 900 }}
              >
                {scene.keycard}
              </div>
              <div
                style={{
                  fontSize: 34,
                  fontWeight: 900,
                  lineHeight: 1.42,
                  marginTop: 10,
                }}
              >
                {scene.coach}
              </div>
            </>
          )}
          {segmentText ? (
            <div
              style={{
                marginTop: 18,
                color: segment?.speaker === "S" ? "#d7e9ff" : "#f8fafc",
                fontSize: 29,
                fontWeight: 900,
                lineHeight: 1.38,
              }}
            >
              {segmentText}
            </div>
          ) : null}
        </div>
        <div style={{ display: "flex", gap: 13 }}>
          {ir.scenes.map((item) => (
            <div
              key={item.id}
              style={{
                flex: 1,
                height: 28,
                borderRadius: 18,
                background: item.id === scene.id ? colors.amber : "#223147",
              }}
            />
          ))}
        </div>
      </div>
    </AbsoluteFill>
  );
};

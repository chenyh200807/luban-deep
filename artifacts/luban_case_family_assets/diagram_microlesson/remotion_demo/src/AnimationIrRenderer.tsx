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
  value?: number;
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
  render_contract: { max_visible_nodes: number };
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
const ease = (value: number) => interpolate(clamp(value), [0, 1], [0, 1], {
  easing: Easing.bezier(0.16, 1, 0.3, 1),
  extrapolateLeft: "clamp",
  extrapolateRight: "clamp",
});

const toneOf = (tone?: string) => tones[(tone || "neutral") as keyof typeof tones] || tones.neutral;

const activeSceneAt = (scenes: Scene[], second: number) =>
  scenes.find((scene) => second >= scene.start_sec && second < scene.end_sec) ||
  scenes[scenes.length - 1];

const activeSegmentAt = (segments: TimingSegment[] | undefined, second: number) =>
  (segments || []).find((segment) => second >= segment.startSec - 0.12 && second < segment.startSec + segment.durSec + 0.12);

const nodeReveal = (node: VisualNode, scene: Scene, progress: number, index: number) => {
  const reveal = (scene.actions || []).find((action) => action.kind === "reveal" && action.target === node.id) || {
    start: 0.04 + index * 0.14,
    end: 0.22 + index * 0.14,
  };
  return ease((progress - reveal.start) / Math.max(0.04, reveal.end - reveal.start));
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
}> = ({ text, x, y, size = 15, fill = colors.text, weight = 900, anchor = "middle" }) => {
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

const fitFontSize = (text: string | undefined, width: number, base: number, minimum = 10) => {
  const longest = Math.max(0, ...String(text || "").split("\n").map((line) => line.length));
  if (!longest) return base;
  const estimated = Math.floor((Math.max(width - 20, 24) / Math.max(longest, 1)) * 1.08);
  return Math.max(minimum, Math.min(base, estimated));
};

const labelsWithDefaults = (node: VisualNode, defaults: string[], limit: number) =>
  [...(node.labels || []).filter((label): label is string => label != null), ...defaults].slice(0, limit);

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
  const badgeW = width ?? Math.max(54, Math.min(116, label.length * size * 0.92 + 22));
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
      <TextLines text={label} x={cx} y={cy + size * 0.34} size={size} fill={tone.text} />
    </>
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
  const h = node.h ?? (node.kind === "pill" ? 54 : node.kind === "dialogue_box" ? 42 : node.kind === "answer_box" ? 38 : 42);
  const transform = `translate(0 ${interpolate(opacity, [0, 1], [10, 0])}) scale(${interpolate(opacity, [0, 1], [0.97, highlighted ? 1.025 : 1])})`;
  const filter = highlighted ? "drop-shadow(0px 0px 8px rgba(255, 210, 127, 0.7))" : undefined;
  const common = { opacity, transform, transformBox: "fill-box" as const, transformOrigin: "center", filter };

  if (node.kind === "pill") {
    const titleSize = fitFontSize(node.text, w, 16, 11);
    const subSize = fitFontSize(node.subtext, w, 12, 10);
    const titleY = y + (node.subtext ? h * 0.42 : h / 2 + titleSize * 0.36);
    return (
      <g style={common}>
        <rect x={x} y={y} width={w} height={h} rx={14} fill={t.fill} stroke={t.stroke} strokeWidth={3} />
        <TextLines text={node.text} x={x + w / 2} y={titleY} size={titleSize} fill={t.text} />
        {node.subtext ? <TextLines text={node.subtext} x={x + w / 2} y={y + h * 0.76} size={subSize} fill={t.text} weight={850} /> : null}
      </g>
    );
  }
  if (node.kind === "roof_section") {
    const baseH = node.h ?? 58;
    return (
      <g style={common}>
        <rect x={x} y={y + 28} width={w} height={baseH} rx={4} fill="#87919d" />
        <rect x={x} y={y + 12} width={w} height={16} fill="#c5b78f" />
        <rect x={x} y={y} width={w} height={12} fill="#34465b" />
        <text x={x + 12} y={y + 9} fontSize={10} fontWeight={900} fill="#e2edf7">卷材</text>
        <text x={x + 12} y={y + 45} fontSize={10} fontWeight={900} fill="#f8fafc">基层</text>
      </g>
    );
  }
  if (node.kind === "bulge") {
    const cx = x;
    const by = node.base_y ?? 150;
    return (
      <g style={common}>
        <path d={`M${cx - 34} ${by} Q${cx} ${by - 58} ${cx + 34} ${by} Z`} fill="#34465b" stroke={colors.blue} strokeWidth={4} />
        <TextLines text={node.text} x={cx} y={by - 76} size={15} fill="#1d4ed8" />
      </g>
    );
  }
  if (node.kind === "up_arrows") {
    return (
      <g style={common}>
        <path d={`M${x - 16} ${y} V${y - 32} M${x} ${y} V${y - 42} M${x + 16} ${y} V${y - 32}`} stroke="#f59e0b" strokeWidth={4} strokeLinecap="round" />
        <path d={`M${x - 22} ${y - 26} l6 -8 l6 8 M${x - 6} ${y - 36} l6 -8 l6 8 M${x + 10} ${y - 26} l6 -8 l6 8`} fill="none" stroke="#f59e0b" strokeWidth={3} />
      </g>
    );
  }
  if (node.kind === "up_arrow") {
    const hh = node.h ?? 90;
    return (
      <g style={common}>
        <path d={`M${x} ${y} V${y - hh}`} stroke={colors.red} strokeWidth={4} strokeLinecap="round" />
        <path d={`M${x - 9} ${y - hh + 12} l9 -13 l9 13`} fill="none" stroke={colors.red} strokeWidth={4} strokeLinecap="round" />
      </g>
    );
  }
  if (node.kind === "cut_cross") {
    return (
      <g style={common}>
        <path d={`M${x - 18} ${y + 18} L${x + 18} ${y - 18} M${x - 18} ${y - 18} L${x + 18} ${y + 18}`} stroke={colors.red} strokeWidth={8} strokeLinecap="round" />
        <TextLines text={node.text} x={x} y={y - 42} size={16} fill="#b91c1c" />
      </g>
    );
  }
  if (node.kind === "dry_zone") {
    return (
      <g style={common}>
        <rect x={x} y={y} width={w} height={h} rx={9} fill="none" stroke={colors.blue} strokeWidth={5} strokeDasharray="9 7" />
        <TextLines text={node.text} x={x + w / 2} y={y - 18} size={16} fill="#1d4ed8" />
      </g>
    );
  }
  if (node.kind === "sweep_line") {
    return (
      <g style={common}>
        <path d={`M${x} ${y} H${x + w}`} stroke="#f59e0b" strokeWidth={5} strokeLinecap="round" />
        <TextLines text={node.text} x={x + w / 2} y={y + 24} size={13} fill="#b45309" />
      </g>
    );
  }
  if (node.kind === "membrane_strip") {
    return (
      <g style={common}>
        <rect x={x} y={y} width={w} height={14} rx={5} fill={t.stroke} />
        <TextLines text={node.text} x={x + w / 2} y={y - 18} size={16} fill={t.text} />
      </g>
    );
  }
  if (node.kind === "coverage_bracket") {
    const x1 = node.x1 ?? x;
    const x2 = node.x2 ?? x + w;
    return (
      <g style={common}>
        <path d={`M${x1} ${y - 12} v22 M${x2} ${y - 12} v22 M${x1} ${y} H${x2}`} stroke={colors.teal} strokeWidth={4} fill="none" />
        <TextLines text={node.text} x={(x1 + x2) / 2} y={y + 32} size={13} fill="#047857" />
      </g>
    );
  }
  if (node.kind === "lap_curve") {
    const x1 = node.x1 ?? x;
    const x2 = node.x2 ?? x + w;
    return (
      <g style={common}>
        <path d={`M${x1} ${y} C${x1 + 40} ${y + 26} ${x2 - 40} ${y + 26} ${x2} ${y}`} stroke={colors.blue} strokeWidth={4} fill="none" strokeDasharray="10 7" />
      </g>
    );
  }
  if (node.kind === "water_layer") {
    return (
      <g style={common}>
        <rect x={x} y={y} width={w} height={24} rx={7} fill={colors.blue} opacity={0.72} />
        <TextLines text={node.text} x={x + w / 2} y={y - 16} size={16} fill="#1d4ed8" />
      </g>
    );
  }
  if (node.kind === "check_badge") {
    return (
      <g style={common}>
        <circle cx={x} cy={y} r={24} fill="#ecfdf5" stroke={colors.teal} strokeWidth={4} />
        <text x={x} y={y + 9} textAnchor="middle" fontSize={28} fontWeight={900} fill="#047857">✓</text>
      </g>
    );
  }
  if (node.kind === "process_flow") {
    const labels = labelsWithDefaults(node, ["先判", "再做", "复核", "写分"], 4);
    const stepGap = w / Math.max(labels.length, 1);
    return (
      <g style={common}>
        <TextLines text={node.text || "按顺序 reveal"} x={x + w / 2} y={y + 30} size={15} fill={t.text} />
        <path d={`M${x + 34} ${y + 88} H${x + w - 34}`} stroke="#cbd5e1" strokeWidth={8} strokeLinecap="round" />
        {labels.map((label, index) => {
          const cx = x + stepGap * index + stepGap / 2;
          const circleTone = toneOf(["blue", "success", "amber", "neutral"][index % 4]);
          const size = fitFontSize(label, 68, 13, 10);
          return (
            <g key={`${label}-${index}`}>
              <circle cx={cx} cy={y + 88} r={31} fill={circleTone.fill} stroke={circleTone.stroke} strokeWidth={4} />
              <TextLines text={label} x={cx} y={y + 93} size={size} fill={circleTone.text} />
              <TextLines text={`第${index + 1}步`} x={cx} y={y + 142} size={12} fill="#64748b" />
            </g>
          );
        })}
      </g>
    );
  }
  if (node.kind === "layer_stack") {
    const labels = labelsWithDefaults(node, ["面层", "防水层", "找平层", "基层"], 4);
    const fills = ["#60a5fa", "#10b981", "#c5b78f", "#87919d"];
    const startY = y + 70;
    const layerH = 28;
    return (
      <g style={common}>
        <TextLines text={node.text || "剖面分层"} x={x + w / 2} y={y + 36} size={16} fill={t.text} />
        <rect x={x + 28} y={startY - 12} width={w - 56} height={labels.length * layerH + 8} rx={18} fill="none" stroke="#eadfcb" strokeWidth={3} />
        {labels.map((label, index) => {
          const yy = startY + index * layerH;
          return (
            <g key={`${label}-${index}`}>
              <rect x={x + 38} y={yy} width={w - 76} height={layerH - 4} rx={6} fill={fills[index % fills.length]} opacity={0.88} />
              <TextLines text={label} x={x + 18} y={yy + 18} size={12} fill="#334155" anchor="start" />
            </g>
          );
        })}
      </g>
    );
  }
  if (node.kind === "network_graph") {
    const labels = labelsWithDefaults(node, ["A", "B", "C", "D"], 4);
    const coords: Array<[number, number]> = [[x + 36, y + 118], [x + 112, y + 72], [x + 112, y + 164], [x + 206, y + 118], [x + 282, y + 118]];
    const nodeLabels = ["始", labels[0], labels[1], labels[2], "终"];
    return (
      <g style={common}>
        <TextLines text={node.text || "图上推演"} x={x + w / 2} y={y + 32} size={16} fill={t.text} />
        <path d={`M${coords[0][0] + 24} ${coords[0][1]} C${x + 78} ${y + 116} ${x + 72} ${y + 76} ${coords[1][0] - 24} ${coords[1][1]}`} stroke="#94a3b8" strokeWidth={5} fill="none" />
        <path d={`M${coords[0][0] + 24} ${coords[0][1]} C${x + 78} ${y + 120} ${x + 72} ${y + 164} ${coords[2][0] - 24} ${coords[2][1]}`} stroke="#cbd5e1" strokeWidth={5} fill="none" />
        <path d={`M${coords[1][0] + 24} ${coords[1][1]} H${coords[3][0] - 24} M${coords[2][0] + 24} ${coords[2][1]} C${x + 164} ${y + 164} ${x + 166} ${y + 122} ${coords[3][0] - 24} ${coords[3][1]}`} stroke={colors.blue} strokeWidth={5} fill="none" />
        <path d={`M${coords[3][0] + 24} ${coords[3][1]} H${coords[4][0] - 24}`} stroke={colors.teal} strokeWidth={5} fill="none" />
        {coords.map(([cx, cy], index) => (
          <g key={index}>
            <rect x={cx - 25} y={cy - 20} width={50} height={40} rx={12} fill={index === 0 || index === 4 ? "#fff7ed" : "#eff6ff"} stroke={index === 0 || index === 4 ? "#f97316" : colors.blue} strokeWidth={3} />
            <TextLines text={nodeLabels[index]} x={cx} y={cy + 5} size={13} fill="#172033" />
          </g>
        ))}
      </g>
    );
  }
  if (node.kind === "formula_chain") {
    const labels = labelsWithDefaults(node, ["口径", "数量", "单价", "扣减"], 4);
    const expr = labels.join(" → ");
    return (
      <g style={common}>
        <TextLines text={node.text || "计算口径"} x={x + w / 2} y={y + 44} size={16} fill={t.text} />
        <rect x={x + 22} y={y + 76} width={w - 44} height={64} rx={18} fill="#fff7ed" stroke="#f59e0b" strokeWidth={4} />
        <TextLines text={expr} x={x + w / 2} y={y + 115} size={fitFontSize(expr, w - 62, 16, 11)} fill="#b45309" />
        <path d={`M${x + 56} ${y + 170} H${x + w - 56}`} stroke="#f97316" strokeWidth={6} strokeLinecap="round" />
      </g>
    );
  }
  if (node.kind === "decision_tree") {
    const labels = labelsWithDefaults(node, ["对象", "条件", "阈值", "结论"], 4);
    const gateY = y + 100;
    return (
      <g style={common}>
        <TextLines text={node.text || "判断树"} x={x + w / 2} y={y + 20} size={16} fill={t.text} />
        <rect x={x + 66} y={y + 30} width={w - 132} height={38} rx={13} fill="#ecfdf5" stroke={colors.teal} strokeWidth={3} />
        <TextLines text={labels[0]} x={x + w / 2} y={y + 55} size={13} fill="#047857" />
        {labels.slice(1, 4).map((label, index) => {
          const cx = x + 50 + index * ((w - 100) / 2);
          return (
            <g key={`${label}-${index}`}>
              <path d={`M${x + w / 2} ${y + 68} V${gateY - 16} H${cx}`} stroke="#94a3b8" strokeWidth={3} fill="none" />
              <rect x={cx - 38} y={gateY} width={76} height={42} rx={12} fill="#f8fafc" stroke="#cbd5e1" strokeWidth={3} />
              <TextLines text={label} x={cx} y={gateY + 27} size={fitFontSize(label, 76, 12, 10)} fill="#334155" />
            </g>
          );
        })}
      </g>
    );
  }
  if (node.kind === "contrast_pair") {
    const labels = labelsWithDefaults(node, ["错误做法", "正确做法", "错因", "采分"], 4);
    const left = labels[0] || "错误做法";
    const right = labels[1] || "正确做法";
    return (
      <g style={common}>
        <TextLines text={node.text || "左右对照"} x={x + w / 2} y={y + 28} size={16} fill={t.text} />
        <rect x={x + 20} y={y + 62} width={w / 2 - 30} height={102} rx={16} fill="#fff7ed" stroke="#f97316" strokeWidth={4} />
        <rect x={x + w / 2 + 10} y={y + 62} width={w / 2 - 30} height={102} rx={16} fill="#ecfdf5" stroke={colors.teal} strokeWidth={4} />
        <TextLines text="错" x={x + 42} y={y + 88} size={18} fill="#9a3412" />
        <TextLines text="对" x={x + w / 2 + 32} y={y + 88} size={18} fill="#047857" />
        <TextLines text={left} x={x + 20 + (w / 2 - 30) / 2} y={y + 125} size={fitFontSize(left, w / 2 - 46, 14, 10)} fill="#9a3412" />
        <TextLines text={right} x={x + w / 2 + 10 + (w / 2 - 30) / 2} y={y + 125} size={fitFontSize(right, w / 2 - 46, 14, 10)} fill="#047857" />
      </g>
    );
  }
  if (node.kind === "answer_scan") {
    const labels = labelsWithDefaults(node, ["对象", "条件", "依据", "采分句"], 4);
    const states = [["#ecfdf5", colors.teal, "hit"], ["#fffbeb", "#f59e0b", "partial"], ["#fef2f2", colors.red, "miss"], ["#eff6ff", colors.blue, "fix"]];
    return (
      <g style={common}>
        <TextLines text={node.text || "答案逐句扫描"} x={x + w / 2} y={y + 34} size={16} fill={t.text} />
        {labels.map((label, index) => {
          const yy = y + 62 + index * 38;
          const [fill, stroke, tag] = states[index % states.length];
          return (
            <g key={`${label}-${index}`}>
              <rect x={x + 30} y={yy} width={w - 60} height={28} rx={9} fill={fill} stroke={stroke} strokeWidth={2} />
              <TextLines text={label} x={x + 44} y={yy + 19} size={12} fill="#172033" anchor="start" />
              <TextLines text={tag} x={x + w - 46} y={yy + 19} size={11} fill="#64748b" />
            </g>
          );
        })}
      </g>
    );
  }
  if (node.kind === "memory_table") {
    const labels = labelsWithDefaults(node, ["数值", "条件", "例外", "记忆钩子"], 4);
    return (
      <g style={common}>
        <TextLines text={node.text || "参数辨析"} x={x + w / 2} y={y + 32} size={16} fill={t.text} />
        {labels.map((label, index) => {
          const yy = y + 58 + index * 36;
          return (
            <g key={`${label}-${index}`}>
              <rect x={x + 38} y={yy} width={w - 76} height={28} rx={8} fill="#f8fafc" stroke="#cbd5e1" strokeWidth={2} />
              <TextLines text={label} x={x + 56} y={yy + 19} size={12} fill="#334155" anchor="start" />
            </g>
          );
        })}
      </g>
    );
  }
  if (node.kind === "answer_box" || node.kind === "dialogue_box" || node.kind === "note") {
    const rx = node.kind === "note" ? 10 : 11;
    return (
      <g style={common}>
        <rect x={x} y={y} width={w} height={h} rx={rx} fill={t.fill} stroke={t.stroke} strokeWidth={2} />
        <TextLines text={node.text} x={x + w / 2} y={y + h / 2 + 5} size={13} fill={t.text} />
      </g>
    );
  }
  if (node.kind === "closing_text") {
    return (
      <g style={common}>
        <TextLines text={node.text} x={180} y={90} size={18} fill="#047857" />
        <TextLines text={node.subtext} x={180} y={132} size={19} fill={colors.text} />
      </g>
    );
  }
  if (node.kind === "challenge_button") {
    return (
      <g style={common}>
        <rect x={90} y={166} width={180} height={44} rx={22} fill={colors.amber} />
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
        <path d={`M${lineStart} ${y} H${x2}`} stroke={t.stroke} strokeWidth={5} strokeLinecap="round" />
        <path d={`M${x2 - 12} ${y - 8} L${x2} ${y} L${x2 - 12} ${y + 8}`} fill="none" stroke={t.stroke} strokeWidth={5} strokeLinecap="round" strokeLinejoin="round" />
        <LabelBadge text={label} cx={x1 + badgeW / 2} cy={y} tone={t} width={badgeW} size={12} />
      </g>
    );
  }
  if (node.kind === "threshold_meter") {
    const value = Math.max(0, Math.min(1, node.value ?? 0.62));
    const marker = x + w * value;
    return (
      <g style={common}>
        <rect x={x} y={y} width={w} height={18} rx={9} fill="#e2e8f0" />
        <rect x={x} y={y} width={w * value} height={18} rx={9} fill={t.stroke} opacity={0.85} />
        <path d={`M${marker} ${y - 8} V${y + 30}`} stroke="#f97316" strokeWidth={4} strokeLinecap="round" />
        <TextLines text={node.text} x={x + w / 2} y={y + 48} size={13} fill={t.text} />
      </g>
    );
  }
  return null;
};

const Board: React.FC<{ visual: VisualScene; scene: Scene; progress: number }> = ({ visual, scene, progress }) => {
  const nodes = visual.nodes || [];
  const board = visual.board || "warm_grid";
  const isPaper = board === "paper";
  const isClosing = board === "closing";
  return (
    <svg viewBox="0 0 360 270" style={{ width: "100%", height: "100%", display: "block" }}>
      {isPaper ? (
        <>
          <rect x="28" y="30" width="304" height="210" rx="18" fill="#fffdf7" stroke="#eadfcb" strokeWidth="4" />
          <TextLines text="答题纸这样写" x={54} y={72} size={15} fill="#176b7a" anchor="start" />
        </>
      ) : isClosing ? (
        <rect x="24" y="34" width="312" height="198" rx="22" fill="#ecfdf5" stroke={colors.teal} strokeWidth="3" />
      ) : (
        <>
          <rect x="12" y="18" width="336" height="234" rx="22" fill={colors.panel} stroke={colors.line} strokeWidth="3" />
          <path d="M44 66 H316 M44 120 H316 M44 174 H316 M88 40 V230 M180 40 V230 M272 40 V230" stroke={colors.grid} strokeWidth="1.2" />
        </>
      )}
      <g>
        {nodes.map((node, index) => (
          <Primitive
            key={node.id}
            node={node}
            opacity={nodeReveal(node, scene, progress, index)}
            highlighted={nodeHighlighted(node, scene, progress)}
          />
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
  const cameraAction = (scene.actions || []).find((action) => action.kind === "camera");
  const cameraProgress = ease((progress - (cameraAction?.start || 0)) / Math.max(0.04, (cameraAction?.end || 0.32) - (cameraAction?.start || 0)));
  const cameraVerb = cameraAction?.verb || scene.camera?.verb || "spotlight";
  const scaleTarget = cameraVerb === "pull-back" ? 0.98 : cameraVerb === "freeze-frame" ? 1.04 : 1.03;
  const boardScale = interpolate(cameraProgress, [0, 1], [0.985, scaleTarget], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

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
          padding: 72,
          height: "100%",
          display: "grid",
          gridTemplateRows: "auto 1fr auto auto",
          gap: 30,
        }}
      >
        <div>
          <div style={{ color: colors.amber, fontSize: 30, fontWeight: 900 }}>{displayKicker}</div>
          <div style={{ fontSize: 70, fontWeight: 950, lineHeight: 1.08, marginTop: 14 }}>{displayTitle}</div>
          <div style={{ color: "#9fb0c2", fontSize: 31, fontWeight: 850, lineHeight: 1.45, marginTop: 20 }}>
            {ir.main_exam_action}
          </div>
        </div>
        <div
          style={{
            borderRadius: 44,
            background: "#111d2a",
            border: "3px solid #26384d",
            overflow: "hidden",
            display: "grid",
            placeItems: "center",
            transform: `scale(${boardScale})`,
          }}
        >
          <Board visual={visual} scene={scene} progress={progress} />
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
          <div style={{ color: colors.amber, fontSize: 29, fontWeight: 900 }}>{scene.keycard}</div>
          <div style={{ fontSize: 34, fontWeight: 900, lineHeight: 1.42, marginTop: 10 }}>{scene.coach}</div>
          {segment?.text ? (
            <div
              style={{
                marginTop: 18,
                color: segment.speaker === "S" ? "#d7e9ff" : "#f8fafc",
                fontSize: 29,
                fontWeight: 900,
                lineHeight: 1.38,
              }}
            >
              {segment.text}
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

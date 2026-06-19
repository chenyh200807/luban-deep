import {
  AbsoluteFill,
  Audio,
  Easing,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

export const N01_FPS = 30;
export const N01_DURATION_FRAMES = 4801;

const FONT =
  '-apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif';
const INK = "#17202a";
const SUB = "#607287";
const PAPER = "#fffdf7";
const BOARD = "#fbfaf4";
const LINE = "#d8e2ec";
const TEAL = "#176b7a";
const BLUE = "#1d4ed8";
const ORANGE = "#f97316";
const RED = "#c2410c";
const GREEN = "#0f766e";
const AMBER = "#b45309";

const VISUAL_LEAD_SEC = 0;
const TOTAL_SEC = 160.016;

type Segment = {
  kind: "teach" | "q" | "a";
  state: string;
  speaker: "T" | "S";
  voice: string;
  text: string;
  start: number;
  dur: number;
};

const SEGMENTS: Segment[] = [
  {
    kind: "teach",
    state: "hook",
    speaker: "T",
    voice: "longanhuan_v3",
    start: 0,
    dur: 16.608,
    text: "先给你一个考试视角：网络计划题，表面问关键线路，实际要三件事：路径、总工期、判断依据。后面索赔和工期调整，也都靠这三件事。今天只练一个动作：把图，变成能拿分的一句话。",
  },
  {
    kind: "teach",
    state: "trap",
    speaker: "T",
    voice: "longanhuan_v3",
    start: 17.008,
    dur: 11.736,
    text: "所以第一步不是算，而是先防错觉。很多人一眼看见 C 工作四天最长，就说关键线路是 C。这里已经错了：C 只是一个工作，不是一条线。",
  },
  {
    kind: "teach",
    state: "logic",
    speaker: "T",
    voice: "longanhuan_v3",
    start: 29.144,
    dur: 11.616,
    text: "接下来才读箭线。A、B 可以同时开始；C、D 要等 A；D 还要等 B；E 要等 C 和 D。箭线读错，顺推、逆推都会跟着错。",
  },
  {
    kind: "teach",
    state: "forward",
    speaker: "T",
    voice: "longanhuan_v3",
    start: 41.16,
    dur: 11.28,
    text: "顺推最早时间时，遇到多个紧前工作，取完成最晚的那个。C 在第七天完成，D 在第五天完成，所以 E 只能等到第七天开始。",
  },
  {
    kind: "teach",
    state: "backward",
    speaker: "T",
    voice: "longanhuan_v3",
    start: 52.84,
    dur: 11.328,
    text: "有了总工期，再逆推最迟时间。逆推问的不是重新算一遍，而是：不拖总工期时，每项工作最晚还能什么时候开始、什么时候完成。",
  },
  {
    kind: "teach",
    state: "float",
    speaker: "T",
    voice: "longanhuan_v3",
    start: 64.568,
    dur: 9.096,
    text: "现在看总时差。B 有三天总时差，D 有两天总时差，说明它们有缓冲。能拖的工作，不控制总工期。",
  },
  {
    kind: "teach",
    state: "critical",
    speaker: "T",
    voice: "longanhuan_v3",
    start: 74.064,
    dur: 12.192,
    text: "把总时差为零的工作连成一条连续线：开始，A，C，E，结束。这条线没有缓冲，所以它控制总工期，总工期是十天。",
  },
  {
    kind: "teach",
    state: "score",
    speaker: "T",
    voice: "longanhuan_v3",
    start: 86.656,
    dur: 13.896,
    text: "最后落到答题纸：关键线路为开始，A，C，E，结束，总工期十天；理由是 A、C、E 的总时差均为零。你不是在写结论，是在写采分点。",
  },
  {
    kind: "q",
    state: "conclude",
    speaker: "S",
    voice: "Ethan",
    start: 100.952,
    dur: 3.76,
    text: "老师，所以最长工作不能直接当关键线路，对吗？",
  },
  {
    kind: "a",
    state: "conclude",
    speaker: "T",
    voice: "longanhuan_v3",
    start: 105.112,
    dur: 9.792,
    text: "对。最长工作只是一个点，关键线路是一条从开始到结束的路。判断它，要看这条路上的工作是否总时差为零。",
  },
  {
    kind: "q",
    state: "conclude",
    speaker: "S",
    voice: "Ethan",
    start: 115.304,
    dur: 3.28,
    text: "那我能不能只把每条路的工期加起来，选最长？",
  },
  {
    kind: "a",
    state: "conclude",
    speaker: "T",
    voice: "longanhuan_v3",
    start: 118.984,
    dur: 10.8,
    text: "可以作为检查，但不能跳过逻辑关系。像 D 要同时等 A 和 B，E 要同时等 C 和 D；不按紧前紧后读，路本身可能就读错。",
  },
  {
    kind: "q",
    state: "conclude",
    speaker: "S",
    voice: "Ethan",
    start: 130.184,
    dur: 2.96,
    text: "总时差和自由时差，我还是容易混。",
  },
  {
    kind: "a",
    state: "conclude",
    speaker: "T",
    voice: "longanhuan_v3",
    start: 133.544,
    dur: 12.696,
    text: "记住问法不同：总时差问拖多久不影响总工期；自由时差问拖多久不影响紧后工作最早开始。比如 B，总时差三天，自由时差只有一天。",
  },
  {
    kind: "a",
    state: "closing",
    speaker: "T",
    voice: "longanhuan_v3",
    start: 146.64,
    dur: 12.576,
    text: "收个尾：网络计划题，别背关键线路四个字。先把图翻译成三件套：路径、总工期、判断依据。现在进闯关，练到一眼能写出采分句。",
  },
];

const T = {
  hook: 0,
  trap: 17.008,
  logic: 29.144,
  forward: 41.16,
  backward: 52.84,
  float: 64.568,
  critical: 74.064,
  score: 86.656,
  qa: 100.952,
  qa2: 115.304,
  qa3: 130.184,
  closing: 146.64,
} as const;

const V = (sec: number) => Math.max(0, sec - VISUAL_LEAD_SEC);

const CUE = {
  tfZero: T.critical + 0.75,
  criticalPath: T.critical + 3.05,
  criticalLock: T.critical + 6.8,
  durationTen: T.critical + 8.4,
  scoreHeader: T.score + 1.15,
  scorePath: T.score + 2.45,
  scoreDuration: T.score + 5.3,
  scoreReason: T.score + 7.35,
} as const;

const CAPTION_CUES = [
  [0, "先看考试要什么：路径、总工期、判断依据。"],
  [5.5, "今天只练一个动作：把图写成采分句。"],
  [T.trap, "先防错觉：C 最长，不等于关键线路。"],
  [T.trap + 6.2, "C 是一个工作，不是一条从开始到结束的线。"],
  [T.logic, "第二步读箭线：谁等谁，先搞清楚。"],
  [T.logic + 4.8, "D 等 A 和 B，E 等 C 和 D。"],
  [T.forward, "顺推最早时间：多个紧前，取完成最晚。"],
  [T.forward + 6.1, "C 到第 7 天，D 到第 5 天，所以 E 等到第 7 天。"],
  [T.backward, "逆推最迟时间：不拖总工期时，最晚还能多晚。"],
  [T.float, "现在看总时差：B 有 3 天，D 有 2 天。"],
  [T.float + 5.0, "能拖的工作，不控制总工期。"],
  [T.critical, "把总时差为 0 的工作先亮出来。"],
  [CUE.criticalPath, "再连成完整线路：开始-A-C-E-结束。"],
  [CUE.criticalLock, "这才是关键线路。"],
  [CUE.durationTen, "总工期是 10 天。"],
  [T.score, "最后写到答题纸。"],
  [CUE.scorePath, "关键线路：开始-A-C-E-结束。"],
  [CUE.scoreDuration, "总工期：10 天。"],
  [CUE.scoreReason, "理由：A、C、E 总时差均为 0。"],
  [T.qa, "讲完，再补三个最容易丢分的追问。"],
  [T.closing, "收个尾：把图翻译成三件套。"],
  [T.closing + 6.1, "现在进闯关，练到一眼能写出采分句。"],
] as const;

const NODES = {
  START: { x: 96, y: 290, label: "开始" },
  A: { x: 245, y: 190, label: "A", dur: "3天", es: "0-3", ls: "0-3", tf: "总0/自0" },
  B: { x: 245, y: 390, label: "B", dur: "2天", es: "0-2", ls: "3-5", tf: "总3/自1" },
  C: { x: 430, y: 190, label: "C", dur: "4天", es: "3-7", ls: "3-7", tf: "总0/自0" },
  D: { x: 430, y: 390, label: "D", dur: "2天", es: "3-5", ls: "5-7", tf: "总2/自2" },
  E: { x: 615, y: 290, label: "E", dur: "3天", es: "7-10", ls: "7-10", tf: "总0/自0" },
  END: { x: 760, y: 290, label: "结束" },
} as const;

const EDGES = [
  ["START", "A"],
  ["START", "B"],
  ["A", "C"],
  ["A", "D"],
  ["B", "D"],
  ["C", "E"],
  ["D", "E"],
  ["E", "END"],
] as const;

const CRIT = new Set(["START-A", "A-C", "C-E", "E-END"]);
const CRIT_NODES = new Set(["START", "A", "C", "E", "END"]);

const clamp01 = (n: number) => Math.max(0, Math.min(1, n));

const CAMERA_TIMES = [
  T.trap - 0.8,
  T.trap + 0.35,
  T.logic - 0.45,
  T.logic + 0.35,
  T.forward - 0.45,
  T.forward + 0.35,
  T.backward - 0.45,
  T.backward + 0.35,
  T.float - 0.45,
  T.float + 0.35,
  T.critical - 0.45,
  T.critical + 0.35,
  T.score - 0.45,
  T.score + 0.35,
  T.qa - 0.6,
  T.qa + 0.25,
] as const;

const cameraValue = (time: number, values: number[]) =>
  interpolate(time, CAMERA_TIMES as unknown as number[], values, {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

const focusNodesFor = (time: number): Set<keyof typeof NODES> => {
  if (time >= V(T.trap) && time < V(T.logic) - 0.4) return new Set(["C"]);
  if (time >= V(T.forward) && time < V(T.backward) - 0.35) return new Set(["C", "E"]);
  if (time >= V(T.backward) && time < V(T.float) - 0.3) return new Set(["E", "C", "D"]);
  if (time >= V(T.float) && time < V(T.critical) - 0.3) return new Set(["A", "B", "C", "D", "E"]);
  if (time >= CUE.tfZero && time < T.qa) return new Set(["START", "A", "C", "E", "END"]);
  return new Set();
};

const focusEdgesFor = (time: number): Set<string> => {
  if (time >= V(T.forward) && time < V(T.backward) - 0.35) return new Set(["C-E"]);
  if (time >= CUE.criticalPath && time < T.qa) return CRIT;
  return new Set();
};

const useSec = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return frame / fps;
};

const useP = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (start: number, end: number, easing = Easing.bezier(0.16, 1, 0.3, 1)) =>
    interpolate(frame, [start * fps, end * fps], [0, 1], {
      easing,
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
};

const segAt = (time: number) => {
  let found = SEGMENTS[0];
  for (const seg of SEGMENTS) {
    if (time >= seg.start - 0.04) found = seg;
    else break;
  }
  return found;
};

const captionAt = (time: number, fallback: string) => {
  let text = fallback;
  for (const [start, caption] of CAPTION_CUES) {
    if (time >= start - 0.04) text = caption;
    else break;
  }
  return text;
};

const edgePath = (from: keyof typeof NODES, to: keyof typeof NODES) => {
  const a = NODES[from];
  const b = NODES[to];
  const bend =
    from === "A" && to === "D"
      ? 42
      : from === "B" && to === "D"
        ? -18
        : from === "C" && to === "E"
          ? 32
          : from === "D" && to === "E"
            ? -32
            : 0;
  const x1 = a.x + 48;
  const x2 = b.x - 48;
  const mx = (x1 + x2) / 2;
  return `M ${x1} ${a.y} C ${mx} ${a.y + bend}, ${mx} ${b.y - bend}, ${x2} ${b.y}`;
};

const DrawEdge: React.FC<{
  from: keyof typeof NODES;
  to: keyof typeof NODES;
  start: number;
  critical?: boolean;
  dim?: number;
  focus?: boolean;
}> = ({ from, to, start, critical = false, dim = 1, focus = false }) => {
  const p = useP();
  const draw = p(start, start + (critical ? 0.78 : 0.46));
  const key = `${from}-${to}`;
  const isCrit = critical || CRIT.has(key);
  const color = critical ? RED : focus ? BLUE : "#4b5d73";
  return (
    <path
      d={edgePath(from, to)}
      fill="none"
      stroke={color}
      strokeWidth={critical ? 7 : focus ? 7 : 5}
      strokeLinecap="round"
      strokeLinejoin="round"
      pathLength={1}
      strokeDasharray={1}
      strokeDashoffset={1 - draw}
      opacity={(focus ? 1 : isCrit ? 0.92 : 0.48) * dim}
      markerEnd={critical ? "url(#hotArrow)" : "url(#arrow)"}
    />
  );
};

const NodeBox: React.FC<{
  id: keyof typeof NODES;
  start: number;
  showEarly: number;
  showLate: number;
  showFloat: number;
  critical: number;
  dim?: number;
  focus?: boolean;
}> = ({ id, start, showEarly, showLate, showFloat, critical, dim = 1, focus = false }) => {
  const p = useP();
  const enter = p(start, start + 0.34);
  const node = NODES[id];
  const hasDur = "dur" in node;
  const isCrit = CRIT_NODES.has(id);
  const glow = critical * (isCrit ? 1 : 0);
  const scale = 0.86 + 0.14 * enter + 0.035 * glow + (focus ? 0.065 : 0);
  const opacity = (0.25 + 0.75 * enter) * dim;
  return (
    <g transform={`translate(${node.x} ${node.y}) scale(${scale})`} opacity={opacity}>
      <rect
        x="-52"
        y="-38"
        width="104"
        height="76"
        rx="14"
        fill={glow > 0 ? "#fff3e9" : focus ? "#eff6ff" : PAPER}
        stroke={glow > 0 ? RED : focus ? BLUE : "#4b5d73"}
        strokeWidth={glow > 0 || focus ? 6 : 4}
      />
      {focus ? <rect x="-62" y="-48" width="124" height="96" rx="20" fill="none" stroke={BLUE} strokeWidth="4" opacity="0.32" /> : null}
      <text y={hasDur ? -5 : 8} textAnchor="middle" fill={INK} fontSize="26" fontWeight="900">
        {node.label}
      </text>
      {hasDur ? (
        <text y="25" textAnchor="middle" fill={SUB} fontSize="19" fontWeight="850">
          {node.dur}
        </text>
      ) : null}
      {hasDur ? (
        <>
          <text x="0" y="-58" textAnchor="middle" fill={BLUE} fontSize="18" fontWeight="900" opacity={showEarly}>
            早 {node.es}
          </text>
          <text x="0" y="66" textAnchor="middle" fill={GREEN} fontSize="18" fontWeight="900" opacity={showLate}>
            迟 {node.ls}
          </text>
          <rect x="-42" y="44" width="84" height="27" rx="13" fill={node.tf.includes("总0") ? "#e8f7f0" : "#fff7ed"} opacity={showFloat} />
          <text
            x="0"
            y="64"
            textAnchor="middle"
            fill={node.tf.includes("总0") ? GREEN : AMBER}
            fontSize="17"
            fontWeight="950"
            opacity={showFloat}
          >
            {node.tf}
          </text>
        </>
      ) : null}
    </g>
  );
};

const HookScene: React.FC<{ time: number }> = ({ time }) => {
  const p = useP();
  const enter = p(0.1, 0.9);
  const leave = p(T.trap - 1.25, T.trap - 0.25, Easing.in(Easing.cubic));
  const opacity = enter * (1 - leave);
  const cards = [
    ["路径", "从开始到结束的一整条控制线", 3.0, TEAL],
    ["总工期", "这条线算出来的完成时间", 4.2, BLUE],
    ["判断依据", "为什么它控制总工期", 5.4, GREEN],
  ] as const;
  if (time > T.trap) return null;
  return (
    <div style={{ position: "absolute", inset: 0, opacity }}>
      <div style={{ position: "absolute", top: 120, left: 72, right: 72 }}>
        <div style={{ color: TEAL, fontSize: 30, fontWeight: 950 }}>先别急着算</div>
        <div style={{ color: INK, fontSize: 64, lineHeight: 1.08, fontWeight: 980, marginTop: 20 }}>
          考场要交的是三件套
        </div>
        <div style={{ color: SUB, fontSize: 29, lineHeight: 1.45, fontWeight: 850, marginTop: 28 }}>
          网络计划不是背定义。你要把一张图,推成路径、总工期和判断依据,最后写成能拿分的一句话。
        </div>
      </div>

      <div style={{ position: "absolute", top: 560, left: 70, right: 70, display: "grid", gap: 26 }}>
        {cards.map(([title, detail, start, color]) => {
          const cardIn = p(start, start + 0.42);
          const y = interpolate(cardIn, [0, 1], [28, 0]);
          return (
            <div
              key={title}
              style={{
                minHeight: 118,
                borderRadius: 28,
                border: `5px solid ${color}`,
                background: "#fff",
                boxShadow: "0 18px 45px rgba(31,41,55,.11)",
                padding: "24px 28px",
                opacity: cardIn,
                transform: `translateY(${y}px)`,
              }}
            >
              <div style={{ color, fontSize: 34, fontWeight: 980 }}>{title}</div>
              <div style={{ color: INK, fontSize: 27, fontWeight: 850, marginTop: 10 }}>{detail}</div>
            </div>
          );
        })}
      </div>

      <div
        style={{
          position: "absolute",
          left: 80,
          right: 80,
          bottom: 180,
          borderRadius: 30,
          background: "#fff7ed",
          border: "5px solid #fed7aa",
          padding: "30px 34px",
          color: "#7c2d12",
          fontSize: 35,
          lineHeight: 1.35,
          fontWeight: 950,
          opacity: p(8.8, 9.5),
        }}
      >
        今天只攻一条链：读逻辑 → 算时间 → 找 0 总时差连续线 → 写采分句。
      </div>
    </div>
  );
};

const TitleBlock: React.FC<{ time: number }> = ({ time }) => {
  const p = useP();
  const enter = p(T.trap - 0.6, T.trap + 0.15);
  const stages = [
    ["为何要学", T.hook],
    ["抓错觉", T.trap],
    ["读逻辑", T.logic],
    ["顺推", T.forward],
    ["逆推", T.backward],
    ["总时差", T.float],
    ["关键线", T.critical],
    ["采分句", T.score],
  ] as const;
  return (
    <div style={{ position: "absolute", top: 54, left: 70, right: 70, opacity: enter }}>
      <div style={{ color: TEAL, fontSize: 29, fontWeight: 900 }}>鲁班深母题 · N01 网络计划</div>
      <div style={{ color: INK, fontSize: 56, lineHeight: 1.08, fontWeight: 950, marginTop: 12 }}>
        关键线路不是最长那一项
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 10, marginTop: 24 }}>
        {stages.map(([label, start]) => {
          const next = stages[stages.findIndex(([stageLabel]) => stageLabel === label) + 1]?.[1] ?? Infinity;
          const active = time >= start - 0.2 && time < next - 0.2;
          const done = time >= next - 0.2;
          return (
            <div
              key={label}
              style={{
                minHeight: 46,
                borderRadius: 15,
                background: active ? "#e8f7f0" : done ? "#eef4f8" : "#f7fafc",
                border: `3px solid ${active ? TEAL : LINE}`,
                color: active ? TEAL : done ? "#8392a5" : SUB,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 19,
                fontWeight: 900,
              }}
            >
              {done ? "✓ " : ""}
              {label}
            </div>
          );
        })}
      </div>
    </div>
  );
};

const Board: React.FC = () => {
  const time = useSec();
  const p = useP();
  const boardIn = p(T.trap - 0.65, T.trap + 0.15);
  const trap = p(V(T.trap), V(T.logic) - 0.7) * (1 - p(V(T.logic) - 1.0, V(T.logic) - 0.2));
  const cross = p(V(T.trap) + 2.4, V(T.trap) + 2.85);
  const scoreCleanup = 1 - p(V(T.score) - 0.6, V(T.score) + 0.2);
  const logic = p(V(T.logic), V(T.forward) - 1.0) * (1 - p(V(T.forward) - 0.7, V(T.forward) - 0.05));
  const forward = p(V(T.forward), V(T.backward) - 1.0) * scoreCleanup;
  const backward = p(V(T.backward), V(T.float) - 0.9) * scoreCleanup;
  const float = p(V(T.float), V(T.critical) - 0.6) * scoreCleanup;
  const critical = p(CUE.tfZero, CUE.tfZero + 0.55);
  const criticalPath = p(CUE.criticalPath, CUE.criticalPath + 0.7);
  const criticalLock = p(CUE.criticalLock, CUE.criticalLock + 0.45);
  const durationTen = p(CUE.durationTen, CUE.durationTen + 0.45);
  const score = p(CUE.scoreHeader, CUE.scoreHeader + 0.5);
  const scorePath = p(CUE.scorePath, CUE.scorePath + 0.45);
  const scoreDuration = p(CUE.scoreDuration, CUE.scoreDuration + 0.45);
  const scoreReason = p(CUE.scoreReason, CUE.scoreReason + 0.45);
  const dimNonCritical = time >= CUE.tfZero ? 0.28 : 1;
  const focusNodes = focusNodesFor(time);
  const focusEdges = focusEdgesFor(time);
  const hasFocus = focusNodes.size > 0 && time < T.qa - 0.4;
  const cameraScale = cameraValue(time, [1, 1.18, 1.18, 1.02, 1.02, 1.24, 1.24, 1.16, 1.16, 1.2, 1.2, 1.02, 1.02, 0.86, 0.86, 0.78]);
  const cameraX = cameraValue(time, [0, -54, -54, 0, 0, -126, -126, -58, -58, -54, -54, 0, 0, 0, 0, 0]);
  const cameraY = cameraValue(time, [0, 22, 22, 0, 0, -20, -20, 56, 56, 62, 62, 0, 0, -88, -88, -120]);
  const boardFadeForScore = 1 - 0.28 * p(V(T.score) + 1.2, V(T.score) + 2.0);
  const boardFadeForQa = 1 - 0.42 * p(T.qa - 0.6, T.qa + 0.6);
  const boardOpacity = boardIn * boardFadeForScore * boardFadeForQa;
  const nodeStart: Record<keyof typeof NODES, number> = {
    START: V(T.trap) + 0.65,
    A: V(T.trap) + 0.95,
    B: V(T.trap) + 1.1,
    C: V(T.trap) + 1.25,
    D: V(T.trap) + 1.4,
    E: V(T.trap) + 1.55,
    END: V(T.trap) + 1.7,
  };

  return (
    <div
      style={{
        position: "absolute",
        top: 340,
        left: 58,
        right: 58,
        height: 760,
        opacity: boardOpacity,
        overflow: "hidden",
        borderRadius: 36,
      }}
    >
      <svg
        viewBox="0 0 860 700"
        style={{
          width: "100%",
          height: "100%",
          transform: `translate(${cameraX}px, ${cameraY}px) scale(${cameraScale})`,
          transformOrigin: "50% 50%",
        }}
      >
        <defs>
          <marker id="arrow" markerWidth="11" markerHeight="11" refX="10" refY="5.5" orient="auto" markerUnits="userSpaceOnUse">
            <path d="M0 0 L11 5.5 L0 11 z" fill="#4b5d73" />
          </marker>
          <marker id="hotArrow" markerWidth="14" markerHeight="14" refX="13" refY="7" orient="auto" markerUnits="userSpaceOnUse">
            <path d="M0 0 L14 7 L0 14 z" fill={RED} />
          </marker>
        </defs>
        <rect x="12" y="22" width="836" height="646" rx="30" fill={BOARD} stroke="#e6dbc7" strokeWidth="5" />
        <path d="M42 90 H818 M42 210 H818 M42 330 H818 M42 450 H818 M42 570 H818" stroke="#eee2cd" strokeWidth="2" opacity="0.55" />
        <path d="M120 55 V640 M300 55 V640 M480 55 V640 M660 55 V640" stroke="#eee2cd" strokeWidth="2" opacity="0.55" />

        <g opacity={trap}>
          <text x="430" y="118" textAnchor="middle" fill={RED} fontSize="34" fontWeight="950">
            C 最长 = 关键线路？
          </text>
          <path
            d="M250 78 L610 138 M608 78 L252 138"
            stroke={RED}
            strokeWidth="8"
            strokeLinecap="round"
            pathLength={1}
            strokeDasharray={1}
            strokeDashoffset={1 - cross}
          />
        </g>

        <g opacity={time < V(T.critical) ? 1 : dimNonCritical}>
          {EDGES.map(([from, to], i) => (
            <DrawEdge
              key={`${from}-${to}`}
              from={from}
              to={to}
              start={V(T.logic) + i * 0.38}
              dim={
                hasFocus && !focusEdges.has(`${from}-${to}`) && focusEdges.size > 0
                  ? 0.22
                  : CRIT.has(`${from}-${to}`)
                    ? 1
                    : dimNonCritical
              }
              focus={focusEdges.has(`${from}-${to}`)}
            />
          ))}
        </g>
        {criticalPath > 0.01 ? (
          <g opacity={criticalPath}>
            {EDGES.filter(([from, to]) => CRIT.has(`${from}-${to}`)).map(([from, to], i) => (
              <DrawEdge key={`crit-${from}-${to}`} from={from} to={to} start={CUE.criticalPath + i * 0.7} critical />
            ))}
          </g>
        ) : null}

        {(Object.keys(NODES) as Array<keyof typeof NODES>).map((id) => (
          <NodeBox
            key={id}
            id={id}
            start={nodeStart[id]}
            showEarly={forward}
            showLate={backward}
            showFloat={float}
            critical={critical}
            focus={focusNodes.has(id)}
            dim={hasFocus && !focusNodes.has(id) ? 0.36 : 1}
          />
        ))}

        <g opacity={logic}>
          <rect x="54" y="604" width="338" height="42" rx="21" fill="#f2f7ff" stroke="#c8dcf5" strokeWidth="3" />
          <text x="223" y="632" textAnchor="middle" fill={BLUE} fontSize="22" fontWeight="900">
            先读紧前紧后：D 等 A 和 B，E 等 C 和 D
          </text>
        </g>
        <g opacity={forward}>
          <path d="M502 126 C570 84 655 130 640 236" fill="none" stroke={BLUE} strokeWidth="5" strokeDasharray="12 10" />
          <text x="625" y="116" fill={BLUE} fontSize="24" fontWeight="950">
            E 要等 C 到第 7 天
          </text>
        </g>
        <g opacity={float}>
          <rect x="94" y="520" width="270" height="56" rx="20" fill="#fff7ed" stroke="#fed7aa" strokeWidth="4" />
          <text x="229" y="556" textAnchor="middle" fill={AMBER} fontSize="25" fontWeight="950">
            B 有 3 天缓冲，D 有 2 天缓冲
          </text>
        </g>
        <g opacity={score}>
          <rect x="70" y="90" width="720" height="136" rx="22" fill="#fff7ed" stroke="#fed7aa" strokeWidth="5" />
          <text x="122" y="154" textAnchor="start" fill={RED} fontSize="28" fontWeight="950">
            采分句：
          </text>
          <text x="250" y="134" textAnchor="start" fill={INK} fontSize="27" fontWeight="950" opacity={scorePath}>
            关键线路 开始-A-C-E-结束
          </text>
          <text x="250" y="170" textAnchor="start" fill={INK} fontSize="25" fontWeight="930" opacity={scoreDuration}>
            总工期 10 天
          </text>
          <text x="430" y="204" textAnchor="middle" fill="#7c2d12" fontSize="23" fontWeight="900" opacity={scoreReason}>
            理由：A、C、E 总时差均为 0
          </text>
        </g>
        <g opacity={criticalLock}>
          <rect x="272" y="36" width="316" height="58" rx="24" fill="#fff3e9" stroke={RED} strokeWidth="5" />
          <text x="430" y="73" textAnchor="middle" fill={RED} fontSize="28" fontWeight="980">
            这才是关键线路
          </text>
        </g>
        <g opacity={durationTen}>
          <rect x="606" y="216" width="146" height="62" rx="24" fill="#e8f7f0" stroke={TEAL} strokeWidth="5" />
          <text x="679" y="256" textAnchor="middle" fill={TEAL} fontSize="31" fontWeight="980">
            10 天
          </text>
        </g>
      </svg>
    </div>
  );
};

const ScenePages: React.FC<{ time: number }> = ({ time }) => {
  const p = useP();
  const calcIn = p(V(T.forward) + 1.0, V(T.forward) + 1.8);
  const calcOut = p(V(T.float) - 0.5, V(T.float) + 0.2, Easing.in(Easing.cubic));
  const floatIn = p(V(T.float), V(T.float) + 0.7);
  const scoreIn = p(CUE.scoreHeader, CUE.scoreHeader + 0.7);
  const scoreOut = p(T.qa - 1.0, T.qa - 0.2, Easing.in(Easing.cubic));
  const qaIn = p(T.qa - 0.35, T.qa + 0.4);
  const closingIn = p(T.closing - 0.5, T.closing + 0.35);
  const calcOpacity = calcIn * (1 - calcOut);
  const scoreOpacity = scoreIn * (1 - scoreOut);
  if (time < V(T.forward) && time < V(T.score)) return null;
  return (
    <>
      <div
        style={{
          position: "absolute",
          left: 84,
          right: 84,
          top: 1090,
          opacity: calcOpacity,
          transform: `translateY(${interpolate(calcIn, [0, 1], [42, 0])}px)`,
        }}
      >
        <div
          style={{
            borderRadius: 30,
            border: "5px solid #c8dcf5",
            background: "rgba(255,255,255,.96)",
            boxShadow: "0 22px 58px rgba(31,41,55,.14)",
            padding: "28px 34px",
          }}
        >
          <div style={{ color: BLUE, fontSize: 28, fontWeight: 980, marginBottom: 18 }}>计算便签</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 }}>
            {[
              ["顺推", "A 0-3  B 0-2  C 3-7  D 3-5  E 7-10", calcIn],
              ["逆推", "E 7-10  C 3-7  D 5-7  A 0-3  B 3-5", p(V(T.backward), V(T.backward) + 0.8)],
              ["总时差", "A0  B3  C0  D2  E0", floatIn],
              ["判断", "0 时差连成：开始-A-C-E-结束", p(V(T.critical), V(T.critical) + 0.7)],
            ].map(([label, text, op]) => (
              <div
                key={label as string}
                style={{
                  minHeight: 100,
                  borderRadius: 22,
                  background: label === "判断" ? "#fff7ed" : "#f7fafc",
                  border: `4px solid ${label === "判断" ? "#fed7aa" : LINE}`,
                  padding: "18px 20px",
                  opacity: op as number,
                }}
              >
                <div style={{ color: label === "判断" ? ORANGE : TEAL, fontSize: 24, fontWeight: 950 }}>{label}</div>
                <div style={{ color: INK, fontSize: 24, lineHeight: 1.35, fontWeight: 900, marginTop: 8 }}>{text}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div
        style={{
          position: "absolute",
          left: 76,
          right: 76,
          top: 500,
          opacity: scoreOpacity,
          transform: `scale(${0.94 + 0.06 * scoreIn}) rotate(${interpolate(scoreIn, [0, 1], [-1.5, 0])}deg)`,
        }}
      >
        <div
          style={{
            borderRadius: 34,
            background: "#fffdf7",
            border: "6px solid #e6dbc7",
            boxShadow: "0 32px 80px rgba(31,41,55,.18)",
            padding: "42px 44px",
          }}
        >
          <div style={{ color: RED, fontSize: 34, fontWeight: 980, marginBottom: 24 }}>答题纸上这样写</div>
          <div style={{ display: "grid", gap: 18 }}>
            {[
              ["关键线路", "开始-A-C-E-结束", CUE.scorePath],
              ["总工期", "10 天", CUE.scoreDuration],
              ["理由", "A、C、E 的总时差均为 0", CUE.scoreReason],
            ].map(([label, value, cue]) => (
              <div
                key={label}
                style={{
                  display: "grid",
                  gridTemplateColumns: "150px 1fr",
                  gap: 18,
                  alignItems: "center",
                  minHeight: 82,
                  borderBottom: "4px solid #efe4d1",
                  opacity: p(cue as number, (cue as number) + 0.45),
                }}
              >
                <div style={{ color: TEAL, fontSize: 28, fontWeight: 950 }}>{label}</div>
                <div style={{ color: INK, fontSize: 32, fontWeight: 950 }}>{value}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div
        style={{
          position: "absolute",
          left: 76,
          right: 76,
          top: 430,
          opacity: qaIn * (1 - closingIn),
          transform: `translateY(${interpolate(qaIn, [0, 1], [50, 0])}px)`,
        }}
      >
        <div style={{ color: TEAL, fontSize: 34, fontWeight: 980, marginBottom: 18 }}>最后 3 个追问</div>
        <div style={{ display: "grid", gap: 20 }}>
          {[
            ["1", "C 最长，是不是就看 C？", T.qa],
            ["2", "只把路径工期相加够不够？", T.qa2],
            ["3", "总时差和自由时差差在哪？", T.qa3],
          ].map(([num, text, start]) => {
            const active = time >= (start as number) - 0.2;
            return (
              <div
                key={num}
                style={{
                  display: "grid",
                  gridTemplateColumns: "62px 1fr",
                  gap: 20,
                  alignItems: "center",
                  minHeight: 94,
                  borderRadius: 26,
                  background: active ? "#fff7ed" : "rgba(255,255,255,.9)",
                  border: `5px solid ${active ? "#fed7aa" : LINE}`,
                  padding: "18px 24px",
                }}
              >
                <div
                  style={{
                    width: 62,
                    height: 62,
                    borderRadius: 31,
                    background: active ? ORANGE : "#dbe5ee",
                    color: "#fff",
                    display: "grid",
                    placeItems: "center",
                    fontSize: 28,
                    fontWeight: 980,
                  }}
                >
                  {num}
                </div>
                <div style={{ color: active ? "#7c2d12" : INK, fontSize: 30, fontWeight: 940 }}>{text}</div>
              </div>
            );
          })}
        </div>
      </div>

      <div
        style={{
          position: "absolute",
          left: 76,
          right: 76,
          top: 410,
          opacity: closingIn,
          transform: `translateY(${interpolate(closingIn, [0, 1], [46, 0])}px) scale(${0.96 + closingIn * 0.04})`,
        }}
      >
        <div
          style={{
            borderRadius: 36,
            background: "#fffdf7",
            border: "6px solid #e6dbc7",
            boxShadow: "0 32px 78px rgba(31,41,55,.18)",
            padding: "46px 48px",
          }}
        >
          <div style={{ color: TEAL, fontSize: 32, fontWeight: 980 }}>收个尾</div>
          <div style={{ color: INK, fontSize: 58, lineHeight: 1.1, fontWeight: 980, marginTop: 16 }}>
            把图翻译成三件套
          </div>
          <div style={{ display: "grid", gap: 16, marginTop: 32 }}>
            {[
              ["路径", "开始-A-C-E-结束", TEAL],
              ["总工期", "10 天", BLUE],
              ["依据", "A、C、E 总时差为 0", GREEN],
            ].map(([label, value, color], i) => {
              const itemIn = p(T.closing + 1.5 + i * 1.0, T.closing + 2.05 + i * 1.0);
              return (
                <div
                  key={label}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "150px 1fr",
                    alignItems: "center",
                    gap: 24,
                    minHeight: 82,
                    borderRadius: 26,
                    border: `5px solid ${color}`,
                    background: "#fff",
                    padding: "18px 24px",
                    opacity: itemIn,
                    transform: `translateY(${interpolate(itemIn, [0, 1], [24, 0])}px)`,
                  }}
                >
                  <div style={{ color, fontSize: 29, fontWeight: 980 }}>{label}</div>
                  <div style={{ color: INK, fontSize: 31, lineHeight: 1.24, fontWeight: 940 }}>{value}</div>
                </div>
              );
            })}
          </div>
          <div
            style={{
              marginTop: 36,
              borderRadius: 28,
              background: "#fff7ed",
              border: "5px solid #fed7aa",
              padding: "28px 32px",
              color: "#7c2d12",
              fontSize: 36,
              lineHeight: 1.32,
              fontWeight: 960,
              opacity: p(T.closing + 7.0, T.closing + 7.75),
            }}
          >
            现在进闯关：练到一眼能写出采分句。
          </div>
        </div>
      </div>
    </>
  );
};

const Subtitle: React.FC<{ segment: Segment; time: number }> = ({ segment, time }) => {
  const p = useP();
  const enter = p(segment.start, segment.start + 0.35);
  const isQa = segment.kind !== "teach";
  const label = segment.state === "closing" ? "收束提醒" : segment.kind === "q" ? "晨煦的追问" : segment.kind === "a" ? "老师补充" : "白板讲解";
  const caption = isQa ? segment.text : captionAt(time, segment.text);
  return (
    <div
      style={{
        position: "absolute",
        left: 70,
        right: 70,
        bottom: 190,
        opacity: enter,
      }}
    >
      <div
        style={{
          background: "#ffffff",
          border: `4px solid ${isQa ? "#fed7aa" : "#c8dcf5"}`,
          borderLeft: `14px solid ${isQa ? ORANGE : TEAL}`,
          borderRadius: 28,
          padding: "30px 36px",
          boxShadow: "0 20px 52px rgba(31,41,55,.13)",
        }}
      >
        <div style={{ color: isQa ? ORANGE : TEAL, fontSize: 25, fontWeight: 950, marginBottom: 12 }}>
          {label}
        </div>
        <div style={{ color: INK, fontSize: 38, lineHeight: 1.36, fontWeight: 900 }}>{caption}</div>
      </div>
    </div>
  );
};

const QaRail: React.FC<{ time: number }> = ({ time }) => {
  const p = useP();
  const enter = p(T.qa - 1.0, T.qa + 0.2);
  const close = p(T.closing - 0.5, T.closing + 0.2, Easing.in(Easing.cubic));
  const qs = [
    ["最长单项≠关键线路", T.qa],
    ["只加工期会漏逻辑", T.qa2],
    ["总时差≠自由时差", T.qa3],
  ] as const;
  if (time < T.qa - 1.2) return null;
  return (
    <div style={{ position: "absolute", top: 1100, left: 70, right: 70, opacity: enter * (1 - close) }}>
      <div style={{ color: TEAL, fontSize: 28, fontWeight: 950, marginBottom: 18 }}>讲完追问，把三个坑补上</div>
      <div style={{ display: "grid", gap: 15 }}>
        {qs.map(([label, start], i) => {
          const active = time >= start;
          return (
            <div
              key={label}
              style={{
                minHeight: 70,
                borderRadius: 20,
                border: `4px solid ${active ? ORANGE : LINE}`,
                background: active ? "#fff7ed" : "#f7fafc",
                color: active ? "#7c2d12" : SUB,
                display: "flex",
                alignItems: "center",
                gap: 18,
                padding: "0 24px",
                fontSize: 28,
                fontWeight: 950,
              }}
            >
              <span
                style={{
                  width: 42,
                  height: 42,
                  borderRadius: 21,
                  background: active ? ORANGE : "#dbe5ee",
                  color: "#fff",
                  display: "grid",
                  placeItems: "center",
                }}
              >
                {i + 1}
              </span>
              {label}
            </div>
          );
        })}
      </div>
    </div>
  );
};

const ProgressBar: React.FC<{ time: number }> = ({ time }) => {
  const pct = clamp01(time / TOTAL_SEC) * 100;
  return (
    <div style={{ position: "absolute", bottom: 82, left: 70, right: 70 }}>
      <div style={{ height: 12, borderRadius: 999, background: "#d6e2ec", overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${pct}%`, background: `linear-gradient(90deg, ${TEAL}, ${ORANGE})` }} />
      </div>
      <div style={{ marginTop: 20, textAlign: "center", color: SUB, fontSize: 23, fontWeight: 800 }}>
        教学演示 · 自测训练 · 非官方评分依据
      </div>
    </div>
  );
};

export const N01NetworkVideoFirst: React.FC = () => {
  const time = useSec();
  const segment = segAt(time);
  return (
    <AbsoluteFill
      style={{
        background: "#eaf1f6",
        fontFamily: FONT,
        color: INK,
      }}
    >
      <Audio src={staticFile("N01_network_video_first.lesson.mp3")} />
      <HookScene time={time} />
      <TitleBlock time={time} />
      <Board />
      <ScenePages time={time} />
      <QaRail time={time} />
      <Subtitle segment={segment} time={time} />
      <ProgressBar time={time} />
    </AbsoluteFill>
  );
};

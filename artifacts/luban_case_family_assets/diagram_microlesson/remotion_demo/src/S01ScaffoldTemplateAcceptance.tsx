import {
  AbsoluteFill,
  Audio,
  Easing,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

export const S01_FPS = 30;
export const S01_DURATION_FRAMES = 4845;

const FONT =
  '-apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif';
const INK = "#17202a";
const SUB = "#607287";
const PAPER = "#fffdf7";
const LINE = "#d8e2ec";
const TEAL = "#176b7a";
const BLUE = "#1d4ed8";
const ORANGE = "#f97316";
const RED = "#c2410c";
const GREEN = "#0f766e";
const AMBER = "#b45309";

type Segment = {
  kind: "teach" | "q" | "a";
  state: string;
  speaker: "T" | "S";
  voice: string;
  start: number;
  dur: number;
  text: string;
};

const SEGMENTS: Segment[] = [
  {
    kind: "teach",
    state: "hook",
    speaker: "T",
    voice: "longanhuan_v3",
    start: 0,
    dur: 12.984,
    text: "先给你一个安全题的考试视角:它不是问架子搭没搭完,而是问能不能放行。脚手架、模板支架这类题,最容易丢在一句话:未经验收,就先使用或先浇筑。",
  },
  {
    kind: "teach",
    state: "trap",
    speaker: "T",
    voice: "longanhuan_v3",
    start: 13.384,
    dur: 11.256,
    text: "最危险的错觉是:现场看着挺稳,可以先干,验收资料后补。考试里这样写,基本就把安全控制点放掉了。搭完,不等于能用。",
  },
  {
    kind: "teach",
    state: "object",
    speaker: "T",
    voice: "longanhuan_v3",
    start: 25.04,
    dur: 12.432,
    text: "第一刀,先判对象。题干出现脚手架、现浇混凝土模板支撑系统,就要立刻想到:这是设备设施安全验收检查的对象,不是普通外观检查。",
  },
  {
    kind: "teach",
    state: "timing",
    speaker: "T",
    voice: "longanhuan_v3",
    start: 37.872,
    dur: 13.104,
    text: "第二刀,再看时点。搭设完成后、使用前、浇筑前,都是放行门。支撑脚手架搭设过程中到规定高度,也要分阶段验收,不能一口气搭到最后再说。",
  },
  {
    kind: "teach",
    state: "acceptance",
    speaker: "T",
    voice: "longanhuan_v3",
    start: 51.376,
    dur: 11.664,
    text: "第三刀,看验收闭环。只说检查过不够,只说看着稳定也不够。要有验收合格、形成记录、签字确认。缺一个,都不能把它当成已放行。",
  },
  {
    kind: "teach",
    state: "outcome",
    speaker: "T",
    voice: "longanhuan_v3",
    start: 63.44,
    dur: 11.328,
    text: "回到题干:模板支架准备浇筑,但验收记录还没有签字。结论不是先浇筑,而是停止放行,完成验收签字;不合格处整改后复验。",
  },
  {
    kind: "teach",
    state: "score",
    speaker: "T",
    voice: "longanhuan_v3",
    start: 75.168,
    dur: 13.608,
    text: "最后写成采分句:脚手架或模板支架搭设完成后,应按专项施工方案和规范要求组织验收;验收合格并形成记录、签字确认后,方可使用或浇筑。",
  },
  {
    kind: "teach",
    state: "bridge",
    speaker: "T",
    voice: "longanhuan_v3",
    start: 89.176,
    dur: 11.616,
    text: "记忆钩子就一句:搭完不等于能用。考试只走四步,对象、时点、验收、放行。后面换成脚手架、支撑脚手架,也按这四步判。",
  },
  {
    kind: "q",
    state: "conclude",
    speaker: "S",
    voice: "Ethan",
    start: 101.192,
    dur: 4.88,
    text: "老师,如果现场已经检查过,只是签字没补,也不能先浇筑吗?",
  },
  {
    kind: "a",
    state: "conclude",
    speaker: "T",
    voice: "longanhuan_v3",
    start: 106.472,
    dur: 8.904,
    text: "不能。考试看的是验收闭环,不是口头说检查过。记录和签字没有完成,就不能写成已经验收合格。",
  },
  {
    kind: "q",
    state: "conclude",
    speaker: "S",
    voice: "Ethan",
    start: 115.776,
    dur: 4.72,
    text: "那这张卡只适合模板支架吗?换成脚手架会不会又不一样?",
  },
  {
    kind: "a",
    state: "conclude",
    speaker: "T",
    voice: "longanhuan_v3",
    start: 120.896,
    dur: 11.28,
    text: "判法一样。你先认对象,再看时点,再看验收闭环,最后写能不能放行。具体验收阶段和检查内容会换,但这个判断模板不变。",
  },
  {
    kind: "q",
    state: "conclude",
    speaker: "S",
    voice: "Ethan",
    start: 132.576,
    dur: 1.92,
    text: "主观题我怎么写才不像口水话?",
  },
  {
    kind: "a",
    state: "conclude",
    speaker: "T",
    voice: "longanhuan_v3",
    start: 134.896,
    dur: 11.784,
    text: "按四个采分原子写:对象是什么,到了什么放行时点,验收是否合格并签字,最后能不能使用或浇筑。四个原子齐了,表达就稳。",
  },
  {
    kind: "a",
    state: "closing",
    speaker: "T",
    voice: "longanhuan_v3",
    start: 147.08,
    dur: 13.608,
    text: "收个尾:你能想到要检查架体,方向已经对了一半。真正得分的是再补两个词:验收合格、签字确认。现在进闯关,换几个题干,看你能不能把放行门守住。",
  },
];

const T = {
  hook: 0,
  trap: 13.384,
  object: 25.04,
  timing: 37.872,
  acceptance: 51.376,
  outcome: 63.44,
  score: 75.168,
  bridge: 89.176,
  qa: 101.192,
  qa2: 115.776,
  qa3: 132.576,
  closing: 147.08,
} as const;

const CAPTION_CUES = [
  [0, "安全题先问:能不能放行?"],
  [5.4, "未经验收就使用/浇筑,是丢分点。"],
  [T.trap, "先打错觉:搭完,不等于能用。"],
  [T.trap + 5.4, "资料后补,不能替代放行前验收。"],
  [T.object, "第一刀:对象。脚手架/模板支架,要验收。"],
  [T.timing, "第二刀:时点。使用前、浇筑前,都是放行门。"],
  [T.timing + 8.0, "支撑脚手架搭到控制高度,也要阶段验收。"],
  [T.acceptance, "第三刀:验收闭环。合格、记录、签字。"],
  [T.acceptance + 7.2, "缺一个,都不能当成已放行。"],
  [T.outcome, "本题:记录未签字,不得先浇筑。"],
  [T.score, "最后写采分句。"],
  [T.score + 3.2, "对象 + 时点 + 验收闭环 + 结论。"],
  [T.bridge, "记忆钩子:搭完不等于能用。"],
  [T.qa, "讲完补三个真实追问。"],
  [T.closing, "收尾:检查架体之外,补上验收合格、签字确认。"],
] as const;

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

const useStageOpacity = (time: number, start: number, end: number) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter =
    start <= 0
      ? 1
      : interpolate(frame, [start * fps, (start + 0.5) * fps], [0, 1], {
          easing: Easing.bezier(0.16, 1, 0.3, 1),
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
  const leave = interpolate(frame, [(end - 0.55) * fps, end * fps], [0, 1], {
    easing: Easing.in(Easing.cubic),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const visible = time >= start - 0.7 && time <= end + 0.7 ? 1 : 0;
  return visible * enter * (1 - leave);
};

const Card: React.FC<{
  title: string;
  body: string;
  color: string;
  top: number;
  delay: number;
}> = ({ title, body, color, top, delay }) => {
  const p = useP();
  const enter = p(delay, delay + 0.42);
  const y = interpolate(enter, [0, 1], [26, 0]);
  return (
    <div
      style={{
        position: "absolute",
        top,
        left: 82,
        right: 82,
        minHeight: 118,
        borderRadius: 28,
        border: `5px solid ${color}`,
        background: "#fff",
        boxShadow: "0 18px 45px rgba(31,41,55,.11)",
        padding: "24px 28px",
        opacity: enter,
        transform: `translateY(${y}px)`,
      }}
    >
      <div style={{ color, fontSize: 34, fontWeight: 980 }}>{title}</div>
      <div style={{ color: INK, fontSize: 27, fontWeight: 850, marginTop: 10, lineHeight: 1.28 }}>{body}</div>
    </div>
  );
};

const ScaffoldSvg: React.FC<{ time: number; dim?: boolean; highlight?: string }> = ({
  time,
  dim = false,
  highlight,
}) => {
  const p = useP();
  const draw = p(T.trap + 0.2, T.trap + 2.1);
  const legs = [140, 260, 380, 500];
  const floors = [250, 360, 470, 580, 690];
  const baseOpacity = dim ? 0.24 : 1;
  const bad = time >= T.trap && time < T.object - 0.3;
  const signIn = p(T.trap + 2.9, T.trap + 3.4);
  return (
    <svg viewBox="0 0 640 760" style={{ width: "100%", height: "100%", overflow: "visible" }}>
      <defs>
        <marker id="s01Arrow" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto">
          <path d="M0 0 L9 4.5 L0 9 z" fill={TEAL} />
        </marker>
      </defs>
      <rect x="52" y="695" width="540" height="22" rx="11" fill="#d9c7a4" opacity={baseOpacity} />
      {legs.map((x, i) => (
        <line
          key={`leg-${x}`}
          x1={x}
          y1={180}
          x2={x}
          y2={700}
          stroke="#425466"
          strokeWidth={10}
          strokeLinecap="round"
          opacity={baseOpacity * Math.min(1, draw + i * 0.18)}
        />
      ))}
      {floors.map((y, i) => (
        <line
          key={`floor-${y}`}
          x1={100}
          y1={y}
          x2={540}
          y2={y}
          stroke="#425466"
          strokeWidth={9}
          strokeLinecap="round"
          opacity={baseOpacity * Math.min(1, draw + i * 0.11)}
        />
      ))}
      {[0, 1, 2].map((i) => (
        <path
          key={`brace-${i}`}
          d={`M ${140 + i * 120} 690 L ${260 + i * 120} 250 M ${260 + i * 120} 690 L ${140 + i * 120} 250`}
          stroke="#8aa0b4"
          strokeWidth={7}
          strokeLinecap="round"
          opacity={baseOpacity * Math.min(1, draw + 0.18)}
        />
      ))}
      <rect
        x="112"
        y="120"
        width="414"
        height="70"
        rx="20"
        fill={highlight === "object" ? "#eff6ff" : "#f7fafc"}
        stroke={highlight === "object" ? BLUE : LINE}
        strokeWidth={highlight === "object" ? 6 : 3}
        opacity={baseOpacity}
      />
      <text x="320" y="164" textAnchor="middle" fill={highlight === "object" ? BLUE : INK} fontSize="30" fontWeight="950">
        模板支架 / 脚手架
      </text>
      {bad ? (
        <g opacity={signIn}>
          <rect x="108" y="360" width="424" height="126" rx="28" fill="#fff7ed" stroke={RED} strokeWidth="8" />
          <text x="320" y="412" textAnchor="middle" fill={RED} fontSize="40" fontWeight="980">
            先浇筑
          </text>
          <text x="320" y="456" textAnchor="middle" fill="#7c2d12" fontSize="27" fontWeight="900">
            验收资料后补?
          </text>
          <path d="M120 334 L520 516 M520 334 L120 516" stroke={RED} strokeWidth="12" strokeLinecap="round" />
        </g>
      ) : null}
    </svg>
  );
};

const HookScene: React.FC<{ time: number }> = ({ time }) => {
  const opacity = useStageOpacity(time, T.hook, T.trap + 0.25);
  if (!opacity) return null;
  return (
    <div style={{ position: "absolute", inset: 0, opacity }}>
      <div style={{ position: "absolute", top: 122, left: 72, right: 72 }}>
        <div style={{ color: TEAL, fontSize: 30, fontWeight: 950 }}>安全题先问放行</div>
        <div style={{ color: INK, fontSize: 62, lineHeight: 1.08, fontWeight: 980, marginTop: 20 }}>
          搭完不等于能用
        </div>
        <div style={{ color: SUB, fontSize: 29, lineHeight: 1.45, fontWeight: 850, marginTop: 28 }}>
          脚手架和模板支架,考场真正要你判断的是:现在能不能使用、能不能浇筑。
        </div>
      </div>
      <Card title="对象" body="脚手架 / 模板支架" color={TEAL} top={520} delay={3.0} />
      <Card title="时点" body="搭设完成后 / 使用前 / 浇筑前" color={BLUE} top={665} delay={4.2} />
      <Card title="验收" body="合格 + 记录 + 签字确认" color={GREEN} top={810} delay={5.4} />
      <div
        style={{
          position: "absolute",
          left: 80,
          right: 80,
          bottom: 196,
          borderRadius: 30,
          background: "#fff7ed",
          border: "5px solid #fed7aa",
          padding: "30px 34px",
          color: "#7c2d12",
          fontSize: 34,
          lineHeight: 1.35,
          fontWeight: 950,
        }}
      >
        这张卡只练一个动作:走过放行门,再写采分句。
      </div>
    </div>
  );
};

const TrapScene: React.FC<{ time: number }> = ({ time }) => {
  const opacity = useStageOpacity(time, T.trap, T.object + 0.25);
  if (!opacity) return null;
  return (
    <div style={{ position: "absolute", inset: 0, opacity }}>
      <div style={{ position: "absolute", top: 90, left: 70, right: 70 }}>
        <div style={{ color: RED, fontSize: 30, fontWeight: 950 }}>先打掉错觉</div>
        <div style={{ color: INK, fontSize: 56, lineHeight: 1.12, fontWeight: 980, marginTop: 18 }}>
          现场看着稳,不能替代验收
        </div>
      </div>
      <div style={{ position: "absolute", left: 130, right: 130, top: 350, height: 760 }}>
        <ScaffoldSvg time={time} />
      </div>
    </div>
  );
};

const Gate: React.FC<{
  x: number;
  y: number;
  label: string;
  detail: string;
  active: number;
  passed?: boolean;
  failed?: boolean;
}> = ({ x, y, label, detail, active, passed = false, failed = false }) => {
  const color = failed ? RED : passed ? GREEN : active > 0.5 ? BLUE : LINE;
  const fill = failed ? "#fff3e9" : passed ? "#e8f7f0" : active > 0.5 ? "#eff6ff" : "#f7fafc";
  return (
    <g transform={`translate(${x} ${y})`}>
      <rect x="-258" y="-56" width="516" height="112" rx="24" fill={fill} stroke={color} strokeWidth={active > 0.5 || failed || passed ? 7 : 3} />
      <text x="-224" y="-10" fill={color === LINE ? SUB : color} fontSize="29" fontWeight="980">
        {label}
      </text>
      <text x="-224" y="30" fill={INK} fontSize="24" fontWeight="850">
        {detail}
      </text>
      {passed ? (
        <circle cx="216" cy="0" r="28" fill={GREEN} />
      ) : failed ? (
        <circle cx="216" cy="0" r="28" fill={RED} />
      ) : null}
      {passed || failed ? (
        <text x="216" y="10" textAnchor="middle" fill="#fff" fontSize="33" fontWeight="980">
          {passed ? "✓" : "!"}
        </text>
      ) : null}
    </g>
  );
};

const DecisionScene: React.FC<{ time: number }> = ({ time }) => {
  const opacity = useStageOpacity(time, T.object - 0.2, T.score + 0.25);
  const p = useP();
  if (!opacity) return null;
  const objectOn = p(T.object, T.object + 0.5);
  const timingOn = p(T.timing, T.timing + 0.5);
  const acceptanceOn = p(T.acceptance, T.acceptance + 0.5);
  const outcomeOn = p(T.outcome, T.outcome + 0.55);
  const dimScaffold = time >= T.acceptance;
  return (
    <div style={{ position: "absolute", inset: 0, opacity }}>
      <div style={{ position: "absolute", top: 82, left: 70, right: 70 }}>
        <div style={{ color: TEAL, fontSize: 27, fontWeight: 950 }}>放行判断树</div>
        <div style={{ color: INK, fontSize: 50, lineHeight: 1.14, fontWeight: 980, marginTop: 12 }}>
          对象、时点、验收,三道门
        </div>
      </div>
      <div style={{ position: "absolute", left: 78, top: 390, width: 390, height: 600, opacity: dimScaffold ? 0.45 : 1 }}>
        <ScaffoldSvg time={time} dim={dimScaffold} highlight={time < T.timing ? "object" : undefined} />
      </div>
      <svg viewBox="0 0 1080 1920" style={{ position: "absolute", inset: 0 }}>
        <defs>
          <marker id="gateArrow" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto">
            <path d="M0 0 L10 5 L0 10 z" fill={TEAL} />
          </marker>
        </defs>
        <path
          d="M 520 572 C 610 572, 610 572, 660 572"
          stroke={TEAL}
          strokeWidth="8"
          strokeLinecap="round"
          markerEnd="url(#gateArrow)"
          opacity={objectOn}
          fill="none"
        />
        <Gate x={820} y={545} label="对象" detail="脚手架 / 模板支架" active={objectOn} passed={time >= T.timing - 0.2} />
        <Gate x={820} y={715} label="时点" detail="使用前 / 浇筑前" active={timingOn} passed={time >= T.acceptance - 0.2} />
        <Gate x={820} y={885} label="验收" detail="合格 + 记录 + 签字" active={acceptanceOn} failed={time >= T.outcome - 0.2} />
        <path d="M 820 608 L 820 654" stroke={time >= T.timing ? TEAL : LINE} strokeWidth="8" strokeLinecap="round" opacity={Math.max(objectOn, timingOn)} />
        <path d="M 820 778 L 820 824" stroke={time >= T.acceptance ? TEAL : LINE} strokeWidth="8" strokeLinecap="round" opacity={Math.max(timingOn, acceptanceOn)} />
        <g opacity={outcomeOn}>
          <rect x="596" y="1036" width="448" height="142" rx="30" fill="#fff3e9" stroke={RED} strokeWidth="8" />
          <text x="820" y="1098" textAnchor="middle" fill={RED} fontSize="40" fontWeight="980">
            不得先浇筑
          </text>
          <text x="820" y="1148" textAnchor="middle" fill="#7c2d12" fontSize="27" fontWeight="900">
            停止放行 · 补验收签字 · 整改复验
          </text>
        </g>
      </svg>
    </div>
  );
};

const ScoreScene: React.FC<{ time: number }> = ({ time }) => {
  const opacity = useStageOpacity(time, T.score - 0.4, T.qa - 0.2);
  const p = useP();
  if (!opacity) return null;
  const rows = [
    ["对象", "脚手架或模板支架", T.score + 1.3, TEAL],
    ["时点", "搭设完成后、使用前或浇筑前", T.score + 3.0, BLUE],
    ["验收", "验收合格并形成记录、签字确认", T.score + 5.2, GREEN],
    ["结论", "未经验收或未签字,不得使用/浇筑", T.score + 7.7, RED],
  ] as const;
  return (
    <div style={{ position: "absolute", inset: 0, opacity }}>
      <div style={{ position: "absolute", top: 112, left: 74, right: 74 }}>
        <div style={{ color: ORANGE, fontSize: 30, fontWeight: 950 }}>答题纸镜头</div>
        <div style={{ color: INK, fontSize: 56, lineHeight: 1.12, fontWeight: 980, marginTop: 18 }}>
          把判断写成采分句
        </div>
      </div>
      <div
        style={{
          position: "absolute",
          left: 72,
          right: 72,
          top: 390,
          borderRadius: 34,
          border: `5px solid ${LINE}`,
          background: "#fff",
          padding: "36px 36px 26px",
          boxShadow: "0 24px 60px rgba(31,41,55,.12)",
        }}
      >
        {rows.map(([k, v, start, color]) => {
          const on = p(start, start + 0.4);
          return (
            <div
              key={k}
              style={{
                display: "grid",
                gridTemplateColumns: "130px 1fr",
                gap: 22,
                alignItems: "center",
                minHeight: 116,
                borderBottom: `2px dashed ${LINE}`,
                opacity: on,
                transform: `translateY(${interpolate(on, [0, 1], [18, 0])}px)`,
              }}
            >
              <div style={{ color, fontSize: 34, fontWeight: 980 }}>{k}</div>
              <div style={{ color: INK, fontSize: 32, lineHeight: 1.28, fontWeight: 900 }}>{v}</div>
            </div>
          );
        })}
        <div style={{ color: SUB, fontSize: 24, lineHeight: 1.5, fontWeight: 800, marginTop: 22 }}>
          不是写“要检查一下”,而是写清楚验收合格、记录签字、能否放行。
        </div>
      </div>
    </div>
  );
};

const QaScene: React.FC<{ time: number }> = ({ time }) => {
  const opacity = useStageOpacity(time, T.qa - 0.4, T.closing - 0.25);
  const p = useP();
  if (!opacity) return null;
  const active = segAt(time);
  const isStudent = active.speaker === "S";
  const panel = p(active.start, active.start + 0.28);
  return (
    <div style={{ position: "absolute", inset: 0, opacity }}>
      <div style={{ position: "absolute", top: 106, left: 72, right: 72 }}>
        <div style={{ color: TEAL, fontSize: 30, fontWeight: 950 }}>讲完追问</div>
        <div style={{ color: INK, fontSize: 56, lineHeight: 1.12, fontWeight: 980, marginTop: 18 }}>
          把学生真会卡的地方补上
        </div>
      </div>
      <div style={{ position: "absolute", left: 110, right: 110, top: 420 }}>
        <div
          style={{
            borderRadius: 34,
            background: isStudent ? "#eff6ff" : "#fff7ed",
            border: `6px solid ${isStudent ? BLUE : ORANGE}`,
            padding: "34px 38px",
            minHeight: 250,
            boxShadow: "0 22px 58px rgba(31,41,55,.12)",
            transform: `translateY(${interpolate(panel, [0, 1], [28, 0])}px)`,
            opacity: panel,
          }}
        >
          <div style={{ color: isStudent ? BLUE : ORANGE, fontSize: 30, fontWeight: 980 }}>
            {isStudent ? "晨煦的追问" : "老师补充"}
          </div>
          <div style={{ color: INK, fontSize: 38, lineHeight: 1.38, fontWeight: 900, marginTop: 22 }}>
            {active.text}
          </div>
        </div>
      </div>
      <div style={{ position: "absolute", left: 120, right: 120, bottom: 300 }}>
        <div style={{ color: SUB, fontSize: 27, lineHeight: 1.45, fontWeight: 850 }}>
          问题不多,但必须是真卡点:资料后补、换工程迁移、主观题怎么写。
        </div>
      </div>
    </div>
  );
};

const ClosingScene: React.FC<{ time: number }> = ({ time }) => {
  const opacity = useStageOpacity(time, T.closing - 0.25, T.closing + 16.0);
  const p = useP();
  if (!opacity) return null;
  const words = [
    ["对象", TEAL, T.closing + 2.4],
    ["时点", BLUE, T.closing + 3.2],
    ["验收", GREEN, T.closing + 4.0],
    ["放行", ORANGE, T.closing + 4.8],
  ] as const;
  return (
    <div style={{ position: "absolute", inset: 0, opacity }}>
      <div style={{ position: "absolute", top: 156, left: 72, right: 72 }}>
        <div style={{ color: TEAL, fontSize: 30, fontWeight: 950 }}>收尾</div>
        <div style={{ color: INK, fontSize: 62, lineHeight: 1.1, fontWeight: 980, marginTop: 20 }}>
          把放行门守住
        </div>
        <div style={{ color: SUB, fontSize: 30, lineHeight: 1.45, fontWeight: 850, marginTop: 30 }}>
          检查架体只是方向对了一半。真正得分,要写验收合格和签字确认。
        </div>
      </div>
      <div style={{ position: "absolute", top: 610, left: 80, right: 80, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
        {words.map(([word, color, start]) => {
          const on = p(start, start + 0.38);
          return (
            <div
              key={word}
              style={{
                height: 150,
                borderRadius: 30,
                background: "#fff",
                border: `6px solid ${color}`,
                display: "grid",
                placeItems: "center",
                color,
                fontSize: 48,
                fontWeight: 980,
                opacity: on,
                transform: `scale(${0.92 + 0.08 * on})`,
              }}
            >
              {word}
            </div>
          );
        })}
      </div>
      <div
        style={{
          position: "absolute",
          left: 84,
          right: 84,
          bottom: 220,
          borderRadius: 32,
          background: "#fff7ed",
          border: "5px solid #fed7aa",
          padding: "30px 34px",
          color: "#7c2d12",
          fontSize: 35,
          lineHeight: 1.35,
          fontWeight: 950,
        }}
      >
        现在闯关,看你能不能换题干也写出采分句。
      </div>
    </div>
  );
};

const Subtitle: React.FC<{ time: number }> = ({ time }) => {
  const seg = segAt(time);
  const text = captionAt(time, seg.text);
  const label = seg.state === "closing" ? "收束提醒" : seg.kind === "q" ? "晨煦的追问" : seg.kind === "a" ? "老师补充" : "白板讲解";
  return (
    <div
      style={{
        position: "absolute",
        left: 80,
        right: 80,
        bottom: 102,
        borderRadius: 26,
        background: "#fff",
        border: `4px solid ${LINE}`,
        borderLeft: `14px solid ${seg.speaker === "S" ? BLUE : TEAL}`,
        boxShadow: "0 16px 42px rgba(31,41,55,.13)",
        padding: "22px 26px",
      }}
    >
      <div style={{ color: seg.speaker === "S" ? BLUE : TEAL, fontSize: 22, fontWeight: 950, marginBottom: 8 }}>
        {label}
      </div>
      <div style={{ color: INK, fontSize: 34, lineHeight: 1.32, fontWeight: 930 }}>{text}</div>
    </div>
  );
};

export const S01ScaffoldTemplateAcceptance: React.FC = () => {
  const time = useSec();
  return (
    <AbsoluteFill style={{ background: "#eaf1f6", fontFamily: FONT, overflow: "hidden" }}>
      <Audio src={staticFile("S01_scaffold_template_acceptance.lesson.mp3")} />
      <div
        style={{
          position: "absolute",
          inset: 48,
          borderRadius: 42,
          background: "#fbfaf4",
          border: "6px solid #d9e4ee",
          boxShadow: "0 28px 90px rgba(31,41,55,.13)",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            position: "absolute",
            inset: 54,
            backgroundImage:
              "linear-gradient(rgba(148,163,184,.14) 2px, transparent 2px), linear-gradient(90deg, rgba(148,163,184,.14) 2px, transparent 2px)",
            backgroundSize: "180px 180px",
          }}
        />
        <HookScene time={time} />
        <TrapScene time={time} />
        <DecisionScene time={time} />
        <ScoreScene time={time} />
        <QaScene time={time} />
        <ClosingScene time={time} />
        <Subtitle time={time} />
        <div style={{ position: "absolute", left: 90, right: 90, bottom: 48, height: 10, borderRadius: 999, background: "#d7e4ee" }}>
          <div
            style={{
              width: `${Math.min(100, (time / 161.488) * 100)}%`,
              height: "100%",
              borderRadius: 999,
              background: `linear-gradient(90deg, ${TEAL}, ${ORANGE})`,
            }}
          />
        </div>
      </div>
    </AbsoluteFill>
  );
};

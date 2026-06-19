import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";

// 语义色(收敛 style-guide 单一源): 绿=对/红=错/琥珀=风险/蓝=湿润进度。
const GREEN = "#1aa06d";
const RED = "#d9534f";
const AMBER = "#e08a1e";
const BLUE = "#2f6df0";
const INK = "#1d2530";
const SUB = "#6b7686";

const FONT =
  '-apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif';

type Step = { no: string; label: string; caption: string; color: string };
const STEPS: Step[] = [
  { no: "①", label: "清浮浆", caption: "清除水泥薄膜、松动石子和软弱层", color: SUB },
  { no: "②", label: "凿毛", caption: "凿毛,做出粗糙结合面", color: AMBER },
  { no: "③", label: "湿润", caption: "充分湿润,但不积水", color: BLUE },
  { no: "④", label: "铺浆浇筑", caption: "铺同配合比水泥砂浆,再浇新混凝土、振捣密实", color: GREEN },
];
const STEP_START = [60, 170, 280, 390];
const CLOSING = 500;

export const JointWorkflow: React.FC = () => {
  const frame = useCurrentFrame();
  const p = (s: number, e: number) =>
    interpolate(frame, [s, e], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  const active =
    frame >= CLOSING ? 4 : frame < 60 ? -1 : Math.min(3, Math.floor((frame - 60) / 110));

  const baseIn = p(0, 40);
  // 浮浆: 开场淡入(=老混凝土一起), step1 被清除
  const laitance = interpolate(frame, [0, 40, 70, 140], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const chisel = p(180, 240); // 凿毛
  const wet = interpolate(frame, [290, 350, 392, 440], [0, 0.72, 0.72, 0.32], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  }); // 湿润(铺浆后淡)
  const mortar = p(400, 450); // 同配合比砂浆
  const newConc = p(412, 472); // 新浇混凝土填入

  // 当前字幕
  let caption = "继续浇筑前,接缝面不能直接浇 —— 先做这四步";
  let capColor = INK;
  let capOpacity = p(12, 40);
  if (active >= 0 && active <= 3) {
    caption = `${STEPS[active].no} ${STEPS[active].caption}`;
    capColor = STEPS[active].color;
    capOpacity = p(STEP_START[active], STEP_START[active] + 18);
  } else if (active === 4) {
    caption = "采分关键:清浮浆 · 凿毛 · 充分湿润 · 同配合比水泥砂浆";
    capColor = GREEN;
    capOpacity = p(505, 528);
  }

  // 凿毛锯齿(沿接缝竖面)
  const teeth = Array.from({ length: 9 }, (_, i) => {
    const y = 168 + i * 23;
    return `M330 ${y} l16 11 l-16 11`;
  }).join(" ");

  return (
    <AbsoluteFill style={{ background: "linear-gradient(180deg,#eef4f8 0%,#f7f8f4 55%,#f2f5f7 100%)", fontFamily: FONT }}>
      {/* 标题区 */}
      <div style={{ position: "absolute", top: 96, left: 0, right: 0, textAlign: "center", opacity: baseIn }}>
        <div style={{ fontSize: 30, fontWeight: 800, color: BLUE, letterSpacing: 2 }}>鲁班图解微课 · 动画讲解</div>
        <div style={{ fontSize: 56, fontWeight: 800, color: INK, marginTop: 14 }}>混凝土施工缝 · 接缝处理</div>
        <div style={{ fontSize: 34, color: SUB, marginTop: 12 }}>继续浇筑前必做的四步工序</div>
      </div>

      {/* 步骤进度点 */}
      <div style={{ position: "absolute", top: 360, left: 0, right: 0, display: "flex", justifyContent: "center", gap: 26, opacity: baseIn }}>
        {STEPS.map((s, i) => {
          const on = active >= i;
          const isActive = active === i;
          return (
            <div key={s.no} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
              <div style={{
                width: 72, height: 72, borderRadius: 36, display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 34, fontWeight: 800, color: on ? "#fff" : SUB,
                background: on ? s.color : "#fff", border: `3px solid ${on ? s.color : "#d5dde7"}`,
                boxShadow: isActive ? `0 0 0 8px ${s.color}22` : "none", transition: "none",
              }}>{i + 1}</div>
              <div style={{ fontSize: 24, fontWeight: 700, color: on ? s.color : SUB }}>{s.label}</div>
            </div>
          );
        })}
      </div>

      {/* 接缝剖面示意(确定性图元, 非规范详图) */}
      <div style={{ position: "absolute", top: 540, left: 60, right: 60 }}>
        <svg viewBox="0 0 720 480" style={{ width: "100%", height: "auto" }}>
          <rect x="40" y="40" width="640" height="420" rx="22" fill="#fffdf8" stroke="#e7ebf0" strokeWidth="2" />
          {/* 老混凝土块(左, 已硬化) */}
          <g opacity={baseIn}>
            <rect x="80" y="160" width="250" height="210" rx="6" fill="#cdd6e2" stroke="#9aa6b6" strokeWidth="3" />
            {[[120, 200], [180, 250], [150, 320], [240, 210], [270, 300], [110, 290]].map(([cx, cy], i) => (
              <circle key={i} cx={cx} cy={cy} r={i % 2 ? 9 : 13} fill="#b3bdca" />
            ))}
            <text x="205" y="408" textAnchor="middle" fontSize="26" fontWeight="700" fill={SUB}>老混凝土(已硬化)</text>
          </g>
          {/* 待浇区框(右) */}
          <g opacity={baseIn}>
            <rect x="330" y="160" width="290" height="210" rx="6" fill="none" stroke="#c3cdd9" strokeWidth="3" strokeDasharray="10 8" />
            <text x="475" y="408" textAnchor="middle" fontSize="26" fontWeight="700" fill={SUB}>待浇筑区</text>
          </g>
          {/* 浮浆层(step1 清除) */}
          <g opacity={laitance}>
            <rect x="326" y="160" width="16" height="210" fill="#f1eee6" />
            <text x="334" y="146" textAnchor="middle" fontSize="22" fontWeight="700" fill={AMBER}>浮浆/松动层</text>
          </g>
          {/* 凿毛锯齿(step2) */}
          <path d={teeth} fill="none" stroke={AMBER} strokeWidth="5" strokeLinejoin="round" strokeLinecap="round" opacity={chisel} />
          {/* 湿润蓝(step3) */}
          <rect x="322" y="160" width="22" height="210" fill={BLUE} opacity={wet} />
          {/* 同配合比砂浆(step4 接缝绿层) */}
          <rect x="320" y="160" width="26" height="210" fill={GREEN} opacity={mortar} />
          {/* 新浇混凝土(step4 填入) */}
          <g opacity={newConc}>
            <rect x="346" y="162" width="272" height="206" rx="5" fill="#aebfd6" stroke="#7f93b4" strokeWidth="3" />
            <text x="482" y="280" textAnchor="middle" fontSize="26" fontWeight="800" fill="#2c3c57">新浇混凝土</text>
          </g>
          {/* 接缝标注 */}
          <text x="334" y="452" textAnchor="middle" fontSize="24" fontWeight="800" fill={INK} opacity={baseIn}>↑ 施工缝接缝面</text>
        </svg>
      </div>

      {/* 字幕条 */}
      <div style={{ position: "absolute", top: 1300, left: 80, right: 80, textAlign: "center" }}>
        <div style={{
          opacity: capOpacity, background: "#ffffff", border: `2px solid ${capColor}33`,
          borderLeft: `10px solid ${capColor}`, borderRadius: 22, padding: "34px 36px",
          fontSize: 44, fontWeight: 700, color: INK, lineHeight: 1.5, boxShadow: "0 18px 44px rgba(29,37,48,.12)",
        }}>{caption}</div>
      </div>

      {/* 记忆钩子(收尾) */}
      <div style={{ position: "absolute", top: 1560, left: 80, right: 80, textAlign: "center", opacity: p(508, 532) }}>
        <div style={{ fontSize: 36, fontWeight: 800, color: GREEN }}>记忆钩子:浇前凿毛湿润铺浆</div>
      </div>

      {/* 底部进度 + 诚实边界角标 */}
      <div style={{ position: "absolute", bottom: 96, left: 80, right: 80 }}>
        <div style={{ height: 10, borderRadius: 999, background: "#dde6f0", overflow: "hidden" }}>
          <div style={{ height: "100%", width: `${(frame / 540) * 100}%`, background: `linear-gradient(90deg,${BLUE},${GREEN})` }} />
        </div>
        <div style={{ marginTop: 22, textAlign: "center", fontSize: 24, color: SUB }}>
          教学示意 · 非规范详图 · 教研候选 · 非官方阅卷
        </div>
      </div>
    </AbsoluteFill>
  );
};

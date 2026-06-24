import type { Caption } from "@remotion/captions";
import type { CSSProperties } from "react";
import {
  AbsoluteFill,
  Easing,
  Sequence,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

export const F16_DURATION_FRAMES = 720;
export const F16_FPS = 30;

const INK = "#1d2530";
const MUTED = "#6f7a87";
const PAPER = "#fbfaf5";
const BLUE = "#2f6df0";
const TEAL = "#15a78b";
const GREEN = "#1aa06d";
const AMBER = "#e08a1e";
const RED = "#d94f45";
const GRAPHITE = "#303946";
const FONT =
  '-apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif';

const CAPTIONS: Caption[] = [
  {
    text: "起鼓不是直接贴补丁。先看清:鼓包里有气,基层和卷材已经脱开。",
    startMs: 900,
    endMs: 4300,
    timestampMs: null,
    confidence: 1,
  },
  {
    text: "第一步,割开鼓包后先放气。别急着补,先把鼓里的气排掉。",
    startMs: 5000,
    endMs: 8400,
    timestampMs: null,
    confidence: 1,
  },
  {
    text: "第二步,擦干基层,清除旧胶结料。这里漏写,采分点就会少一半。",
    startMs: 8800,
    endMs: 12300,
    timestampMs: null,
    confidence: 1,
  },
  {
    text: "第三步,喷灯烘烤,分层剥开旧卷材。重点不是烤一下,是分层处理。",
    startMs: 12700,
    endMs: 16300,
    timestampMs: null,
    confidence: 1,
  },
  {
    text: "第四步,重贴新卷材并连续搭接压实。补丁要变成一体,不能留下新缝口。",
    startMs: 16800,
    endMs: 20700,
    timestampMs: null,
    confidence: 1,
  },
  {
    text: "记住采分句:放气、擦干、清旧胶;喷灯烘烤、分层剥开、重贴新卷材。",
    startMs: 21100,
    endMs: 23500,
    timestampMs: null,
    confidence: 1,
  },
];

const STEPS = [
  { no: "1", label: "放气", color: BLUE, start: 5.0 },
  { no: "2", label: "擦干清胶", color: AMBER, start: 8.8 },
  { no: "3", label: "烘烤分层", color: RED, start: 12.7 },
  { no: "4", label: "重贴搭接", color: GREEN, start: 16.8 },
];

const clamp = (value: number) => Math.max(0, Math.min(1, value));

const useProgress = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (startS: number, endS: number, easing = Easing.bezier(0.16, 1, 0.3, 1)) =>
    interpolate(frame, [startS * fps, endS * fps], [0, 1], {
      easing,
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
};

const DrawPath: React.FC<{
  d: string;
  color?: string;
  width?: number;
  start: number;
  end: number;
  opacity?: number;
  dash?: number;
}> = ({ d, color = INK, width = 6, start, end, opacity = 1, dash = 900 }) => {
  const progress = useProgress()(start, end);
  return (
    <path
      d={d}
      fill="none"
      stroke={color}
      strokeWidth={width}
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeDasharray={dash}
      strokeDashoffset={dash * (1 - progress)}
      opacity={opacity}
    />
  );
};

const PaperBackground: React.FC = () => (
  <AbsoluteFill
    style={{
      background: PAPER,
      backgroundImage:
        "linear-gradient(#ecede7 1px, transparent 1px), linear-gradient(90deg, #ecede7 1px, transparent 1px)",
      backgroundSize: "54px 54px",
      fontFamily: FONT,
      color: INK,
    }}
  />
);

const Header: React.FC = () => {
  const p = useProgress();
  const intro = p(0.1, 1.1);
  return (
    <div
      style={{
        position: "absolute",
        top: 70,
        left: 70,
        right: 70,
        opacity: intro,
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 24,
        }}
      >
        <div>
          <div style={{ color: BLUE, fontSize: 28, fontWeight: 800 }}>
            F16 防水 · 白板图解微课样片
          </div>
          <div style={{ marginTop: 10, fontSize: 58, fontWeight: 900, lineHeight: 1.12 }}>
            屋面卷材起鼓割补
          </div>
        </div>
        <div
          style={{
            border: "3px solid #dfe5ec",
            background: "#fff",
            borderRadius: 16,
            padding: "18px 22px",
            textAlign: "right",
            color: MUTED,
            fontSize: 22,
            fontWeight: 700,
            lineHeight: 1.45,
          }}
        >
          Q18 P10/P11
          <br />
          教学示意 · 非官方阅卷
        </div>
      </div>
    </div>
  );
};

const StepTimeline: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const time = frame / fps;
  const p = useProgress();
  const enter = p(2.1, 2.9);

  return (
    <div
      style={{
        position: "absolute",
        top: 282,
        left: 78,
        right: 78,
        opacity: enter,
      }}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          gap: 16,
        }}
      >
        {STEPS.map((step, index) => {
          const next = STEPS[index + 1]?.start ?? 21;
          const active = time >= step.start && time < next;
          const done = time >= next;
          return (
            <div
              key={step.no}
              style={{
                background: active ? `${step.color}18` : done ? "#eef7f2" : "#fff",
                border: `3px solid ${active || done ? step.color : "#dbe1e8"}`,
                borderRadius: 16,
                padding: "18px 12px",
                textAlign: "center",
                boxShadow: active ? `0 14px 32px ${step.color}24` : "none",
              }}
            >
              <div
                style={{
                  width: 48,
                  height: 48,
                  margin: "0 auto 10px",
                  borderRadius: 24,
                  background: active || done ? step.color : "#f2f4f6",
                  color: active || done ? "#fff" : MUTED,
                  fontSize: 26,
                  fontWeight: 900,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                {step.no}
              </div>
              <div style={{ color: active || done ? step.color : MUTED, fontSize: 24, fontWeight: 850 }}>
                {step.label}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

const MarkerHand: React.FC<{ x: number; y: number; color: string; opacity: number }> = ({
  x,
  y,
  color,
  opacity,
}) => (
  <g transform={`translate(${x} ${y}) rotate(-16)`} opacity={opacity}>
    <rect x="-10" y="-44" width="20" height="82" rx="10" fill={color} />
    <path d="M-10 38 L10 38 L0 64 Z" fill="#f4d6a7" stroke={INK} strokeWidth="3" />
  </g>
);

const RoofSection: React.FC = () => {
  const p = useProgress();
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const time = frame / fps;

  const boardIn = p(1.0, 2.0);
  const bubbleShow = p(2.2, 3.4);
  const cut = p(5.2, 6.8);
  const vent = p(6.4, 8.2);
  const clean = p(9.0, 11.4);
  const heat = p(12.9, 14.7);
  const peel = p(14.1, 16.0);
  const patch = p(16.9, 19.0);
  const close = p(20.8, 22.1);
  const diagnosis = p(3.0, 4.1) * (1 - p(16.3, 17.2));
  const cutVisible = cut * (1 - p(16.8, 17.6));
  const cleanVisible = clean * (1 - p(12.0, 12.8));
  const heatVisible = heat * (1 - p(16.0, 16.8));
  const peelVisible = peel * (1 - p(18.1, 18.9));

  const bubbleLift = 68 * bubbleShow * (1 - 0.7 * patch);
  const membraneD = `M90 365 L278 365 C300 ${365 - bubbleLift} 430 ${365 - bubbleLift} 452 365 L630 365`;
  const airY = interpolate(vent, [0, 1], [0, -52]);
  const airOpacity = vent * (1 - clamp((time - 8.1) / 0.8));
  const oldAdhesiveOpacity = clamp(1 - clean);
  const cleanSweepX = interpolate(clean, [0, 1], [220, 444]);
  const markerOpacity = time >= 5 && time <= 19.2 ? 1 : 0;
  const markerX = time < 8.7 ? 360 : time < 12.6 ? cleanSweepX : time < 16.7 ? 424 : 496;
  const markerY = time < 8.7 ? 284 : time < 12.6 ? 415 : time < 16.7 ? 312 : 358;

  return (
    <div
      style={{
        position: "absolute",
        top: 450,
        left: 58,
        right: 58,
        height: 790,
        opacity: boardIn,
      }}
    >
      <svg viewBox="0 0 720 790" style={{ width: "100%", height: "100%" }}>
        <rect x="18" y="20" width="684" height="738" rx="24" fill="#fffefa" stroke="#dfe5ec" strokeWidth="4" />
        <path d="M74 122 C166 96 278 96 370 122 S566 150 648 118" fill="none" stroke="#edf0f4" strokeWidth="12" />

        <text x="62" y="86" fill={MUTED} fontSize="24" fontWeight="800">
          剖面示意:卷材起鼓后,按割补工序恢复连续防水层
        </text>

        <g opacity={bubbleShow}>
          <path d="M116 505 H604" stroke="#9d8367" strokeWidth="22" strokeLinecap="round" />
          <text x="620" y="514" fill={MUTED} fontSize="24" fontWeight="750">
            基层
          </text>
        </g>

        <g opacity={bubbleShow}>
          <path d={membraneD} fill="none" stroke={GRAPHITE} strokeWidth="24" strokeLinecap="round" strokeLinejoin="round" />
          <path d={membraneD} fill="none" stroke="#ffffff" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" opacity="0.62" />
          <text x="102" y="337" fill={MUTED} fontSize="24" fontWeight="750">
            防水卷材
          </text>
        </g>

        <g opacity={diagnosis}>
          <ellipse cx="365" cy="332" rx="118" ry="58" fill="#fff0e2" stroke={AMBER} strokeWidth="5" strokeDasharray="12 10" />
          <text x="365" y="252" textAnchor="middle" fill={AMBER} fontSize="28" fontWeight="900">
            起鼓:先排气,不是直接补
          </text>
        </g>

        <g opacity={oldAdhesiveOpacity * bubbleShow}>
          {[260, 295, 336, 382, 424].map((x, index) => (
            <path
              key={x}
              d={`M${x} 472 q${index % 2 ? 22 : -18} -18 ${index % 2 ? 44 : 38} 0`}
              fill="none"
              stroke="#b88d5a"
              strokeWidth="9"
              strokeLinecap="round"
              opacity="0.65"
            />
          ))}
          <text x="360" y="456" textAnchor="middle" fill="#9a7041" fontSize="22" fontWeight="800">
            旧胶结料
          </text>
        </g>

        <g opacity={cutVisible}>
          <DrawPath d="M316 305 L414 407" color={RED} width={8} start={5.2} end={6.0} />
          <DrawPath d="M414 305 L316 407" color={RED} width={8} start={5.8} end={6.6} />
          <text x="532" y="310" fill={RED} fontSize="28" fontWeight="900">
            割开
          </text>
        </g>

        <g opacity={airOpacity}>
          {[326, 360, 394].map((x, index) => (
            <g key={x} transform={`translate(0 ${airY - index * 10})`}>
              <path d={`M${x} 308 C${x - 12} 284 ${x + 18} 270 ${x + 4} 246`} fill="none" stroke={BLUE} strokeWidth="5" strokeLinecap="round" />
              <path d={`M${x + 4} 246 l-10 13 M${x + 4} 246 l15 7`} fill="none" stroke={BLUE} strokeWidth="5" strokeLinecap="round" />
            </g>
          ))}
          <text x="178" y="300" fill={BLUE} fontSize="28" fontWeight="900">
            放气
          </text>
        </g>

        <g opacity={cleanVisible}>
          <rect x={cleanSweepX - 44} y="424" width="88" height="28" rx="14" fill="#dae4ef" stroke={BLUE} strokeWidth="4" />
          <path d={`M${cleanSweepX - 70} 462 C${cleanSweepX - 20} 482 ${cleanSweepX + 34} 482 ${cleanSweepX + 88} 462`} fill="none" stroke={AMBER} strokeWidth="7" strokeLinecap="round" />
          <text x="158" y="448" fill={AMBER} fontSize="28" fontWeight="900">
            擦干 + 清胶
          </text>
        </g>

        <g opacity={heatVisible}>
          <path d="M520 245 l62 -48 l24 34 l-65 50 Z" fill="#384352" stroke={INK} strokeWidth="4" />
          <path d="M500 292 C486 255 530 245 520 208 C564 239 580 274 540 312 C530 296 518 291 500 292 Z" fill="#ff9f2f" stroke={RED} strokeWidth="4" />
          <text x="564" y="164" textAnchor="middle" fill={RED} fontSize="28" fontWeight="900">
            喷灯烘烤
          </text>
        </g>

        <g opacity={peelVisible}>
          <path d="M278 365 C300 338 330 324 350 316" fill="none" stroke={GRAPHITE} strokeWidth="18" strokeLinecap="round" />
          <path d="M452 365 C430 338 402 324 380 316" fill="none" stroke={GRAPHITE} strokeWidth="18" strokeLinecap="round" />
          <text x="365" y="612" textAnchor="middle" fill={RED} fontSize="30" fontWeight="900">
            分层剥开旧卷材
          </text>
        </g>

        <g opacity={patch}>
          <rect x="250" y="343" width="230" height="44" rx="22" fill={GREEN} />
          <rect x="222" y="334" width="286" height="12" rx="6" fill="#c5ebda" />
          <path d="M250 365 H480" stroke="#0c6e52" strokeWidth="6" strokeLinecap="round" />
          <text x="365" y="304" textAnchor="middle" fill={GREEN} fontSize="30" fontWeight="900">
            新卷材重贴 · 连续搭接
          </text>
        </g>

        <g opacity={close}>
          <circle cx="610" cy="626" r="48" fill={`${GREEN}22`} stroke={GREEN} strokeWidth="7" />
          <path d="M586 626 l18 18 l34 -42" fill="none" stroke={GREEN} strokeWidth="9" strokeLinecap="round" strokeLinejoin="round" />
          <text x="360" y="686" textAnchor="middle" fill={GREEN} fontSize="30" fontWeight="900">
            采分收口:先处理旧鼓包,再恢复连续防水层
          </text>
        </g>

        <MarkerHand x={markerX} y={markerY} color={time < 12.6 ? BLUE : time < 16.7 ? RED : GREEN} opacity={markerOpacity} />
      </svg>
    </div>
  );
};

const ScorepointRail: React.FC = () => {
  const p = useProgress();
  const show = p(19.5, 21.1);
  const rowStyle: CSSProperties = {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 16,
    padding: "18px 22px",
    borderRadius: 16,
    background: "#fff",
    border: "3px solid #e3e8ef",
    fontSize: 24,
    fontWeight: 800,
  };

  return (
    <div
      style={{
        position: "absolute",
        top: 1518,
        left: 78,
        right: 78,
        opacity: show,
      }}
    >
      <div style={{ display: "grid", gap: 14 }}>
        <div style={rowStyle}>
          <span style={{ color: BLUE }}>P10</span>
          <span style={{ flex: 1 }}>放气 / 擦干 / 清除旧胶结料</span>
          <span style={{ color: MUTED }}>0.75</span>
        </div>
        <div style={rowStyle}>
          <span style={{ color: RED }}>P11</span>
          <span style={{ flex: 1 }}>喷灯烘烤 / 分层剥开 / 重贴新卷材</span>
          <span style={{ color: MUTED }}>0.75</span>
        </div>
      </div>
    </div>
  );
};

const CaptionTrack: React.FC = () => {
  const { fps } = useVideoConfig();
  return (
    <>
      {CAPTIONS.map((caption) => {
        const from = Math.round((caption.startMs / 1000) * fps);
        const durationInFrames = Math.max(
          1,
          Math.round(((caption.endMs - caption.startMs) / 1000) * fps),
        );
        return (
          <Sequence
            key={caption.startMs}
            from={from}
            durationInFrames={durationInFrames}
            layout="none"
          >
            <CaptionBox caption={caption} durationInFrames={durationInFrames} />
          </Sequence>
        );
      })}
    </>
  );
};

const CaptionBox: React.FC<{ caption: Caption; durationInFrames: number }> = ({
  caption,
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const enter = interpolate(frame, [0, 16], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const exit = interpolate(frame, [durationInFrames - 16, durationInFrames], [1, 0], {
    easing: Easing.in(Easing.cubic),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const opacity = Math.min(enter, exit);
  const y = interpolate(enter, [0, 1], [18, 0]);

  return (
    <div
      style={{
        position: "absolute",
        left: 78,
        right: 78,
        top: 1282 + y,
        opacity,
      }}
    >
      <div
        style={{
          background: "#ffffff",
          border: "4px solid #dfe7ef",
          borderLeft: `14px solid ${BLUE}`,
          borderRadius: 20,
          boxShadow: "0 18px 42px rgba(29,37,48,.14)",
          color: INK,
          fontSize: 40,
          fontWeight: 850,
          lineHeight: 1.42,
          padding: "30px 34px",
          textAlign: "left",
        }}
      >
        {caption.text}
      </div>
    </div>
  );
};

const OpeningQuestion: React.FC = () => {
  const p = useProgress();
  const show = p(1.3, 2.2) * (1 - p(4.2, 4.9));
  return (
    <div
      style={{
        position: "absolute",
        top: 1262,
        left: 78,
        right: 78,
        opacity: show,
      }}
    >
      <div
        style={{
          background: "#fff",
          border: `4px solid ${AMBER}`,
          borderRadius: 20,
          padding: "26px 30px",
          boxShadow: "0 16px 38px rgba(224,138,30,.16)",
        }}
      >
        <div style={{ color: AMBER, fontSize: 26, fontWeight: 900, marginBottom: 10 }}>
          今日一刀
        </div>
        <div style={{ fontSize: 38, fontWeight: 900, lineHeight: 1.34 }}>
          屋面卷材起鼓了,怎么割补才踩到采分点?
        </div>
      </div>
    </div>
  );
};

const Footer: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const width = `${Math.min(100, (frame / durationInFrames) * 100)}%`;
  return (
    <div style={{ position: "absolute", bottom: 76, left: 78, right: 78 }}>
      <div style={{ height: 12, borderRadius: 99, background: "#dfe7ef", overflow: "hidden" }}>
        <div style={{ width, height: "100%", background: `linear-gradient(90deg, ${BLUE}, ${GREEN})` }} />
      </div>
      <div style={{ marginTop: 20, textAlign: "center", color: MUTED, fontSize: 23, fontWeight: 700 }}>
        白板动画样片 · 确定性 SVG 图元 · 依据 Q18 P10/P11 · 不替代规范详图
      </div>
    </div>
  );
};

export const F16RoofBlisterRepair: React.FC = () => {
  return (
    <AbsoluteFill>
      <PaperBackground />
      <Header />
      <StepTimeline />
      <RoofSection />
      <OpeningQuestion />
      <CaptionTrack />
      <ScorepointRail />
      <Footer />
    </AbsoluteFill>
  );
};

import React from "react";
import {
  AbsoluteFill,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import ir from "../../F16_qigu.animation_ir.v0.json";

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
};

type AnimationIr = {
  main_exam_action: string;
  render_contract: { max_visible_nodes: number };
  scenes: Scene[];
};

const animationIr = ir as AnimationIr;
export const F16_IR_FPS = 30;
export const F16_IR_DURATION_FRAMES = Math.ceil(
  animationIr.scenes[animationIr.scenes.length - 1].end_sec * F16_IR_FPS,
);

const colors = {
  bg: "#0d1723",
  panel: "#13202e",
  line: "#26384d",
  cream: "#fff7e5",
  teal: "#10b981",
  blue: "#60a5fa",
  amber: "#ffd27f",
  red: "#ef4444",
};

const SceneDiagram: React.FC<{ scene: Scene; p: number }> = ({ scene, p }) => {
  const spotlight = scene.visible_nodes.includes("bulge") ? "bulge" : scene.focus;
  const reveal = interpolate(p, [0, 0.18, 1], [0, 1, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const focusScale = interpolate(p, [0, 0.18, 0.72, 1], [0.96, 1.04, 1.04, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  if (scene.id === "score") {
    return (
      <div style={paperStyle}>
        <div style={paperKicker}>答题纸这样写</div>
        <div style={scoreLine}>割开放气 + 排气干燥 + 清旧胶</div>
        <div style={{ ...scoreLine, borderColor: colors.blue, color: "#1d4ed8" }}>
          附加层 + 搭接封严 + 蓄水检验
        </div>
        <div style={paperHint}>不是写结论，是写采分动作</div>
      </div>
    );
  }

  if (scene.id === "closing_challenge") {
    return (
      <div style={closingStyle}>
        <div style={{ fontSize: 42, color: "#bbf7d0", fontWeight: 900 }}>三步闭环</div>
        <div style={{ fontSize: 56, fontWeight: 900 }}>治病因 → 恢复闭合 → 检验</div>
        <div style={challengePill}>开始闯关</div>
      </div>
    );
  }

  return (
    <svg viewBox="0 0 760 560" style={{ width: "100%", height: "100%" }}>
      <rect x="46" y="58" width="668" height="444" rx="38" fill={colors.panel} stroke={colors.line} strokeWidth="4" />
      <g opacity={0.45}>
        <path d="M86 176 H674 M86 300 H674 M86 424 H674 M190 88 V474 M380 88 V474 M570 88 V474" stroke="#26384d" strokeWidth="2" />
      </g>
      <g transform={`translate(0 ${18 * (1 - reveal)})`} opacity={reveal}>
        <rect x="112" y="344" width="536" height="92" rx="8" fill="#87919d" />
        <rect x="112" y="316" width="536" height="28" fill="#c5b78f" />
        <rect x="112" y="292" width="536" height="24" fill="#34465b" />
        {scene.id === "hook" && (
          <>
            <rect x="128" y="132" width="504" height="62" rx="18" fill="#fff7ed" stroke={colors.red} strokeWidth="5" />
            <text x="380" y="173" textAnchor="middle" fontSize="32" fontWeight="900" fill="#9a3412">
              错觉：只写“修补防水层”
            </text>
            <rect x="172" y="226" width="416" height="76" rx="20" fill="#ecfdf5" stroke={colors.teal} strokeWidth="5" />
            <text x="380" y="258" textAnchor="middle" fontSize="26" fontWeight="900" fill="#047857">
              治因 → 闭合 → 检验
            </text>
          </>
        )}
        {["disease", "cut", "dry"].includes(scene.id) && (
          <>
            <path
              d="M320 292 Q380 186 440 292 Z"
              fill="#34465b"
              stroke={scene.id === "cut" ? colors.red : colors.blue}
              strokeWidth="7"
              transform={`translate(380 260) scale(${spotlight === "bulge" ? focusScale : 1}) translate(-380 -260)`}
            />
            {scene.id === "disease" && (
              <text x="380" y="168" textAnchor="middle" fontSize="30" fontWeight="900" fill="#7fc7ff">
                气/水汽顶起卷材
              </text>
            )}
            {scene.id === "cut" && (
              <>
                <path d="M342 318 L418 242 M342 242 L418 318" stroke={colors.red} strokeWidth="16" strokeLinecap="round" />
                <path d="M380 260 V170" stroke="#fecaca" strokeWidth="8" />
                <text x="380" y="138" textAnchor="middle" fontSize="32" fontWeight="900" fill="#fecaca">
                  割开放气
                </text>
              </>
            )}
            {scene.id === "dry" && (
              <>
                <rect x="280" y="278" width="200" height="78" rx="18" fill="none" stroke="#7fc7ff" strokeWidth="8" strokeDasharray="18 14" />
                <text x="380" y="236" textAnchor="middle" fontSize="32" fontWeight="900" fill="#7fc7ff">
                  排气干燥 + 清基层
                </text>
              </>
            )}
          </>
        )}
        {["add", "seal", "test"].includes(scene.id) && (
          <>
            <rect x="252" y="272" width="256" height="26" rx="10" fill={scene.id === "seal" ? colors.blue : colors.teal} />
            {scene.id === "test" && <rect x="112" y="228" width="536" height="44" rx="12" fill="#7fc7ff" opacity={0.72} />}
            <text x="380" y="216" textAnchor="middle" fontSize="32" fontWeight="900" fill={scene.id === "test" ? "#bfdbfe" : "#bbf7d0"}>
              {scene.id === "add" ? "附加层盖过边缘" : scene.id === "seal" ? "搭接封严" : "蓄水/淋水检验"}
            </text>
          </>
        )}
      </g>
    </svg>
  );
};

export const F16AnimationIrPreview: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const scene =
    animationIr.scenes.find((item) => t >= item.start_sec && t < item.end_sec) ??
    animationIr.scenes[animationIr.scenes.length - 1];
  const p = (t - scene.start_sec) / Math.max(0.001, scene.end_sec - scene.start_sec);
  const cameraScale = interpolate(p, [0, 0.2, 0.82, 1], [0.97, 1.02, 1.02, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg, color: "#eef3f8", fontFamily: "PingFang SC, Microsoft YaHei, Arial" }}>
      <div style={{ padding: 74, height: "100%", display: "grid", gridTemplateRows: "auto 1fr auto", gap: 34 }}>
        <div>
          <div style={{ color: colors.amber, fontSize: 28, fontWeight: 900 }}>鲁班深母题 · F16 起鼓割补</div>
          <div style={{ fontSize: 66, fontWeight: 900, lineHeight: 1.08, marginTop: 12 }}>屋面卷材防水起鼓怎么修补</div>
          <div style={{ color: "#9fb0c2", fontSize: 30, fontWeight: 800, lineHeight: 1.45, marginTop: 18 }}>
            {animationIr.main_exam_action}
          </div>
        </div>
        <div style={{ display: "grid", gridTemplateRows: "1fr auto", gap: 26 }}>
          <div style={{ borderRadius: 42, background: "#111d2a", border: `3px solid ${colors.line}`, overflow: "hidden", transform: `scale(${cameraScale})` }}>
            <SceneDiagram scene={scene} p={p} />
          </div>
          <div style={coachStyle}>
            <div style={{ color: colors.amber, fontSize: 28, fontWeight: 900 }}>{scene.keycard}</div>
            <div style={{ fontSize: 34, fontWeight: 900, lineHeight: 1.42, marginTop: 10 }}>{scene.coach}</div>
          </div>
        </div>
        <div style={{ display: "flex", gap: 14 }}>
          {animationIr.scenes.map((item) => (
            <div
              key={item.id}
              style={{
                flex: 1,
                height: 32,
                borderRadius: 20,
                background: item.id === scene.id ? colors.amber : "#223147",
              }}
            />
          ))}
        </div>
      </div>
    </AbsoluteFill>
  );
};

const coachStyle: React.CSSProperties = {
  borderLeft: `12px solid ${colors.amber}`,
  background: "#172434",
  borderRadius: 28,
  padding: "28px 32px",
  boxShadow: "0 28px 70px rgba(0,0,0,.28)",
};

const paperStyle: React.CSSProperties = {
  margin: "60px auto",
  width: "82%",
  height: "72%",
  borderRadius: 34,
  background: "#fffdf7",
  color: "#0f1722",
  padding: 52,
  border: "6px solid #eadfcb",
};

const paperKicker: React.CSSProperties = {
  color: "#176b7a",
  fontSize: 30,
  fontWeight: 900,
  marginBottom: 28,
};

const scoreLine: React.CSSProperties = {
  border: `4px solid ${colors.teal}`,
  color: "#047857",
  borderRadius: 22,
  padding: "26px 30px",
  fontSize: 34,
  fontWeight: 900,
  marginBottom: 24,
};

const paperHint: React.CSSProperties = {
  color: "#b45309",
  fontSize: 28,
  fontWeight: 900,
  marginTop: 22,
};

const closingStyle: React.CSSProperties = {
  margin: "72px auto",
  width: "88%",
  height: "68%",
  borderRadius: 40,
  border: `6px solid ${colors.teal}`,
  background: "#10251a",
  display: "grid",
  placeItems: "center",
  textAlign: "center",
  padding: 46,
};

const challengePill: React.CSSProperties = {
  color: "#0f1722",
  background: colors.amber,
  borderRadius: 999,
  padding: "22px 54px",
  fontSize: 34,
  fontWeight: 900,
};

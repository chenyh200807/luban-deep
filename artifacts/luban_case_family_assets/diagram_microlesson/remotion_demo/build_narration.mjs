// 离线旁白构建:逐句 say 配音 → ffprobe 量真实时长 → 拼成一条 narration.mp3
// → 据各句时长算时间轴写 timing.json(动画/字幕据此对齐)。
// 这是"做一次预存复用"管线的配音环节;产物(mp3+timing)随后被 Remotion 读取渲成带声 mp4。
import { execFileSync, execSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";

const FPS = 30;
const GAP = 0.5; // 句间停顿(秒)
const TAIL = 0.8; // 收尾留白
const VOICE = "Tingting"; // 普通话女声(离线;以后换云 TTS 只改这一环)

// 旁白文本 = 字幕文本(单一源);color 对应动画语义色
const NAR = [
  { id: "opening", color: "#1d2530", text: "这道施工缝的题,丢分常常不是不知道有施工缝,而是说不清继续浇筑前要怎么处理接缝。我们一步一步看。" },
  { id: "s1", color: "#6b7686", text: "第一步,清除接缝面的水泥薄膜、松动石子和软弱层,把浮浆清理干净。" },
  { id: "s2", color: "#e08a1e", text: "第二步,把接缝面凿毛,做出粗糙的结合面,让新旧混凝土咬得住。" },
  { id: "s3", color: "#2f6df0", text: "第三步,充分湿润接缝面,但要注意不能积水。" },
  { id: "s4", color: "#1aa06d", text: "第四步,铺一层同配合比的水泥砂浆,再浇筑新混凝土并振捣密实。" },
  { id: "closing", color: "#1aa06d", text: "记住这四步:清浮浆、凿毛、湿润、铺同配合比砂浆。这就是这道题的采分关键。" },
];

mkdirSync("tmp", { recursive: true });
mkdirSync("public", { recursive: true });
mkdirSync("src", { recursive: true });

const probe = (f) =>
  parseFloat(execSync(`ffprobe -v error -show_entries format=duration -of csv=p=0 "${f}"`).toString().trim());

const durs = [];
NAR.forEach((n, i) => {
  execFileSync("say", ["-v", VOICE, "-o", `tmp/${i}.aiff`, n.text]);
  // 统一为 44.1k 单声道 wav, 便于无缝拼接
  execSync(`ffmpeg -y -loglevel error -i tmp/${i}.aiff -ar 44100 -ac 1 tmp/${i}.wav`);
  durs.push(probe(`tmp/${i}.wav`));
  console.log(`  ${n.id}: ${durs[i].toFixed(2)}s`);
});

// 句间静音
execSync(`ffmpeg -y -loglevel error -f lavfi -i anullsrc=r=44100:cl=mono -t ${GAP} tmp/gap.wav`);

// 拼接列表: s0, gap, s1, gap, ... 末句无 gap
const list = [];
NAR.forEach((_, i) => {
  list.push(`file 'tmp/${i}.wav'`);
  if (i < NAR.length - 1) list.push(`file 'tmp/gap.wav'`);
});
writeFileSync("tmp/filelist.txt", list.join("\n"));
execSync(`ffmpeg -y -loglevel error -f concat -safe 0 -i tmp/filelist.txt -c:a libmp3lame -q:a 3 public/narration.mp3`);

// 时间轴: 各句起止帧
let t = 0;
const segments = NAR.map((n, i) => {
  const startSec = t;
  t += durs[i];
  const seg = {
    id: n.id,
    color: n.color,
    text: n.text,
    startFrame: Math.round(startSec * FPS),
    durFrame: Math.round(durs[i] * FPS),
  };
  if (i < NAR.length - 1) t += GAP;
  return seg;
});
const durationInFrames = Math.ceil((t + TAIL) * FPS);

writeFileSync(
  "src/timing.json",
  JSON.stringify({ fps: FPS, durationInFrames, audio: "narration.mp3", segments }, null, 2),
);
console.log(`narration.mp3 + timing.json 就绪: ${durationInFrames} 帧 (${(durationInFrames / FPS).toFixed(1)}s)`);

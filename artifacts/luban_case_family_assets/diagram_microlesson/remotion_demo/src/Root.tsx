import { Composition } from "remotion";
import {
  P40_A02AnimationIrPreview,
  P40_A02_DURATION_FRAMES,
  P40_A02_FPS,
} from "./P40_A02AnimationIrPreview";
import {
  F16AnimationIrPreview,
  F16_IR_DURATION_FRAMES,
  F16_IR_FPS,
} from "./F16AnimationIrPreview";
import {
  F16RoofBlisterRepair,
  F16_DURATION_FRAMES,
  F16_FPS,
} from "./F16RoofBlisterRepair";
import { JointWorkflow } from "./JointWorkflow";
import {
  N01_DURATION_FRAMES,
  N01_FPS,
  N01NetworkVideoFirst,
} from "./N01NetworkVideoFirst";
import {
  S01_DURATION_FRAMES,
  S01_FPS,
  S01ScaffoldTemplateAcceptance,
} from "./S01ScaffoldTemplateAcceptance";
import {
  P40_S02AnimationIrPreview,
  P40_S02_IR_DURATION_FRAMES,
  P40_S02_IR_FPS,
} from "./P40_S02AnimationIrPreview";
import {
  P40_G01AnimationIrPreview,
  P40_G01_IR_DURATION_FRAMES,
  P40_G01_IR_FPS,
} from "./P40_G01AnimationIrPreview";
import {
  P40_S07BAnimationIrPreview,
  P40_S07B_IR_DURATION_FRAMES,
  P40_S07B_IR_FPS,
} from "./P40_S07BAnimationIrPreview";

// 竖屏手机比例 1080x1920, 30fps, 18 秒 = 540 帧。
export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="JointWorkflow"
        component={JointWorkflow}
        durationInFrames={540}
        fps={30}
        width={1080}
        height={1920}
      />
      <Composition
        id="F16RoofBlisterRepair"
        component={F16RoofBlisterRepair}
        durationInFrames={F16_DURATION_FRAMES}
        fps={F16_FPS}
        width={1080}
        height={1920}
      />
      <Composition
        id="P40-A02-AnimationIrPreview"
        component={P40_A02AnimationIrPreview}
        durationInFrames={P40_A02_DURATION_FRAMES}
        fps={P40_A02_FPS}
        width={1080}
        height={1920}
      />
      <Composition
        id="F16AnimationIrPreview"
        component={F16AnimationIrPreview}
        durationInFrames={F16_IR_DURATION_FRAMES}
        fps={F16_IR_FPS}
        width={1080}
        height={1920}
      />
      <Composition
        id="P40-S02-AnimationIrPreview"
        component={P40_S02AnimationIrPreview}
        durationInFrames={P40_S02_IR_DURATION_FRAMES}
        fps={P40_S02_IR_FPS}
        width={1080}
        height={1920}
      />
      <Composition
        id="P40-G01-AnimationIrPreview"
        component={P40_G01AnimationIrPreview}
        durationInFrames={P40_G01_IR_DURATION_FRAMES}
        fps={P40_G01_IR_FPS}
        width={1080}
        height={1920}
      />
      <Composition
        id="P40-S07B-AnimationIrPreview"
        component={P40_S07BAnimationIrPreview}
        durationInFrames={P40_S07B_IR_DURATION_FRAMES}
        fps={P40_S07B_IR_FPS}
        width={1080}
        height={1920}
      />
      <Composition
        id="N01NetworkVideoFirst"
        component={N01NetworkVideoFirst}
        durationInFrames={N01_DURATION_FRAMES}
        fps={N01_FPS}
        width={1080}
        height={1920}
      />
      <Composition
        id="S01ScaffoldTemplateAcceptance"
        component={S01ScaffoldTemplateAcceptance}
        durationInFrames={S01_DURATION_FRAMES}
        fps={S01_FPS}
        width={1080}
        height={1920}
      />
    </>
  );
};

import { Composition } from "remotion";
import {
  C02AnimationIrPreview,
  C02_IR_DURATION_FRAMES,
  C02_IR_FPS,
} from "./C02AnimationIrPreview";
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
        id="C02AnimationIrPreview"
        component={C02AnimationIrPreview}
        durationInFrames={C02_IR_DURATION_FRAMES}
        fps={C02_IR_FPS}
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

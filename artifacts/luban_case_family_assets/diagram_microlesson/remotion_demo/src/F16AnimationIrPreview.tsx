import React from "react";
import ir from "../../F16_qigu.animation_ir.v0.json";
import timing from "../../F16_qigu.lesson.timing.json";
import {
  AnimationIr,
  AnimationIrRenderer,
  animationIrDurationFrames,
} from "./AnimationIrRenderer";

const animationIr = ir as AnimationIr;

export const F16_IR_FPS = 30;
export const F16_IR_DURATION_FRAMES = animationIrDurationFrames(animationIr, F16_IR_FPS);

export const F16AnimationIrPreview: React.FC = () => {
  return (
    <AnimationIrRenderer
      ir={animationIr}
      timing={timing}
      kicker="鲁班深母题 · F16 起鼓割补"
      title="屋面卷材防水起鼓怎么修补"
    />
  );
};

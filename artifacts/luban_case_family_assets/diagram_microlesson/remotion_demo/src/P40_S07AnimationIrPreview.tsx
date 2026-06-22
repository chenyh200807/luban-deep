import React from "react";
import ir from "../../P40_S07.animation_ir.v0.json";
import timing from "../../P40_S07.lesson.timing.json";
import {
  AnimationIr,
  AnimationIrRenderer,
  animationIrDurationFrames,
} from "./AnimationIrRenderer";

const animationIr = ir as AnimationIr;

export const P40_S07_IR_FPS = 30;
export const P40_S07_IR_DURATION_FRAMES = animationIrDurationFrames(animationIr, P40_S07_IR_FPS);

export const P40_S07AnimationIrPreview: React.FC = () => {
  return <AnimationIrRenderer ir={animationIr} timing={timing} />;
};

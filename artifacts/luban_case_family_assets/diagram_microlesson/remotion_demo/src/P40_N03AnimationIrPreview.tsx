import React from "react";
import ir from "../../P40_N03.animation_ir.v0.json";
import timing from "../../P40_N03.lesson.timing.json";
import {
  AnimationIr,
  AnimationIrRenderer,
  animationIrDurationFrames,
} from "./AnimationIrRenderer";

const animationIr = ir as AnimationIr;

export const P40_N03_IR_FPS = 30;
export const P40_N03_IR_DURATION_FRAMES = animationIrDurationFrames(animationIr, P40_N03_IR_FPS);

export const P40_N03AnimationIrPreview: React.FC = () => {
  return <AnimationIrRenderer ir={animationIr} timing={timing} />;
};

import React from "react";
import ir from "../../P40_K01.animation_ir.v0.json";
import timing from "../../P40_K01.lesson.timing.json";
import {
  AnimationIr,
  AnimationIrRenderer,
  animationIrDurationFrames,
} from "./AnimationIrRenderer";

const animationIr = ir as AnimationIr;

export const P40_K01_IR_FPS = 30;
export const P40_K01_IR_DURATION_FRAMES = animationIrDurationFrames(animationIr, P40_K01_IR_FPS);

export const P40_K01AnimationIrPreview: React.FC = () => {
  return <AnimationIrRenderer ir={animationIr} timing={timing} />;
};

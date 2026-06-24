import React from "react";
import ir from "../../C02_progress_payment.animation_ir.v0.json";
import timing from "../../C02_progress_payment.lesson.timing.json";
import {
  AnimationIr,
  AnimationIrRenderer,
  animationIrDurationFrames,
} from "./AnimationIrRenderer";

const animationIr = ir as AnimationIr;

export const C02_IR_FPS = 30;
export const C02_IR_DURATION_FRAMES = animationIrDurationFrames(animationIr, C02_IR_FPS);

export const C02AnimationIrPreview: React.FC = () => {
  return (
    <AnimationIrRenderer
      ir={animationIr}
      timing={timing}
      kicker="鲁班深母题 · C02 进度款"
      title="进度款题先判四口径"
    />
  );
};

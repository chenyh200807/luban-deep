import React from "react";
import ir from "../../P40_A02.animation_ir.v0.json";
import timing from "../../P40_A02.lesson.timing.json";
import { AnimationIrRenderer } from "./AnimationIrRenderer";

export const P40_A02_FPS = 30;
export const P40_A02_DURATION_FRAMES = Math.ceil(((timing as any).totalSec || (timing as any).total_sec || 240) * P40_A02_FPS);

export function P40_A02AnimationIrPreview() {
  return <AnimationIrRenderer ir={ir as any} timing={timing as any} />;
}

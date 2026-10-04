export type CompiledCard = {
  timeline: {kill(): void; duration(): number};
  duration: number;
  seek: (t: number) => void;
  kinds: string[];
  problems: string[];
};
export type CardLibs = {SplitText?: unknown; CustomEase?: unknown; drawSVG?: boolean; morphSVG?: boolean; motionPath?: boolean};
export function compileCard(gsap: unknown, root: Element,
  opts?: {fps?: number; duration?: number; timeline?: string; libs?: CardLibs}): CompiledCard;
export const CARD_ANIM_KINDS: string[];

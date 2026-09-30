export type CompiledCard = {
  timeline: {kill(): void; duration(): number};
  duration: number;
  seek: (t: number) => void;
  kinds: string[];
  problems: string[];
};
export function compileCard(gsap: unknown, root: Element, opts?: {fps?: number; duration?: number}): CompiledCard;
export const CARD_ANIM_KINDS: string[];

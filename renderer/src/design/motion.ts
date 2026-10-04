// 모션 토큰 — 공개된 디자인 스킬들의 원칙을 영상(30fps)용으로 옮긴 것.
//
// 출처(원칙만 차용, 코드/문장 복제 아님):
//  - delphi-ai/animate-skill (Emil Kowalski "Animations on the Web"): 들어올 땐 ease-out, 나갈 땐 ease-in,
//    화면 안 이동은 ease-in-out, 퇴장은 진입의 ~75%, transform/opacity 만 애니메이션, 글자 리빌은 마스크+슬라이드업+스태거
//  - freshtechbro/claudedesignskills motion-framer: variants/staggerChildren, 스프링 프리셋(gentle/stiff/slow)
//  - claudedesignskills modern-web-design: bold minimalism, "이유를 설명 못 하는 애니메이션은 지운다"
//  - remotion-dev/skills: useCurrentFrame()+interpolate() 로만, scale 은 perceptual 보정
// UI(200~300ms)보다 영상은 시선 이동 거리가 길어 약 1.5배 길게 잡는다.
import {Easing, interpolate, spring} from 'remotion';

export const EASE = {
  outQuint: Easing.bezier(0.23, 1, 0.32, 1), // 진입(기본)
  outExpo: Easing.bezier(0.19, 1, 0.22, 1), // 텍스트 리빌
  outCubic: Easing.bezier(0.33, 1, 0.68, 1),
  inOutCubic: Easing.bezier(0.645, 0.045, 0.355, 1), // 화면 안 이동
  inCubic: Easing.bezier(0.32, 0, 0.67, 0), // 퇴장
  // 2026-10-04 채널 주인: '바운시한 느낌은 싫다 — 플로팅처럼 젠틀하게'. 되튐(오버슛) 곡선은 이름만 남기고 모두 되튐 없는 감속으로
  outBack: Easing.bezier(0.22, 1, 0.36, 1), // (예전 되튐) → 부드러운 감속
  inExpo: Easing.bezier(0.7, 0, 0.84, 0), // 전환: 나가는 장면이 컷으로 빨려 들어감
  inQuart: Easing.bezier(0.5, 0, 0.75, 0),
  linear: Easing.linear,
  // ── v2: 곡선 이름이 아니라 '역할'로 고른다(docs/upgrade/06 6-1, 06b) — 진입·이동·퇴장에 서로 다른 곡선 ──
  enter: Easing.bezier(0.22, 1, 0.36, 1), // 작은·중간 요소 진입 — easeOutQuint(easings.net)
  enterText: Easing.bezier(0.16, 1, 0.3, 1), // 글 마스크 리빌 — easeOutExpo
  enterLarge: Easing.bezier(0.05, 0.7, 0.1, 1), // 큰 면(종이 판·전면) — Material 3 emphasized-decelerate
  move: Easing.bezier(0.2, 0, 0, 1), // 화면 안 A→B — Material 3 standard(빨리 떠나 길게 앉는다)
  exit: Easing.bezier(0.3, 0, 0.8, 0.15), // 퇴장 — Material 3 emphasized-accelerate
  settle: Easing.bezier(0.25, 0.9, 0.3, 1), // 정착 — 되튐 없이 길게 내려앉는다(숫자 끝·칩)
  settlePaper: Easing.bezier(0.2, 0.85, 0.25, 1), // 종이 안착 — 되튐 없이
  pop: Easing.bezier(0.16, 1, 0.3, 1), // 펀치 구간·숏폼 훅 — 빠르게 오되 되튀지 않는다
} as const;

export type EaseName = keyof typeof EASE;

/** 30fps 기준 프레임 길이 */
export const DUR = {
  micro: 5, // 강조색 전환
  fast: 8, // 단어 팝, 퇴장
  normal: 12, // 일반 진입(400ms)
  slow: 18, // 큰 면 진입
  reveal: 24, // 헤드라인 리빌
} as const;

/** 퇴장은 진입의 75% */
export const exitFrames = (enterFrames: number) => Math.max(3, Math.round(enterFrames * 0.75));

/** 장면 전환 기본 길이(프레임, 30fps) — 컷을 가운데 두고 앞뒤 절반씩 */
export const TRANSITION = {
  whip: 10,
  zoom: 10,
  blur: 16,
  push: 12,
  flash: 9,
  dip: 18,
  wipe: 16,
  leak: 24,
} as const;

/** 롱폼 무대(components/longform/) 모션 시그니처 — docs/롱폼_무대_디자인.md */
export const LONG = {
  plateIn: 14, // 플레이트: 바깥 가장자리에서 안으로 쓸어 들어옴
  boardIn: 18, // 보드 판
  rule: 12, // 괘선 그리기
  line: 14, // 줄 마스크 슬라이드
  underline: 10, // 강조 낱말 밑줄 스윕
  count: 24, // 숫자 카운트업(outExpo)
  out: 10, // 퇴장(페이드 + 8px)
} as const;

/** 카메라: 펀치인 진입/복귀(ease 스타일) */
export const CAMERA = {
  punchIn: 5,
  punchOut: 8,
} as const;

export const STAGGER = {
  char: 1, // ≈33ms (animate-skill 30ms)
  word: 2,
  line: 3,
  item: 5,
} as const;

// 감쇠비 ζ = damping / (2·√(stiffness·mass)), 오버슛 = exp(−ζπ/√(1−ζ²)). Remotion 기본값(100/10, ζ 0.5 · 약 16%)은 쓰지 않는다.
export const SPRING = {
  gentle: {stiffness: 100, damping: 20, mass: 1}, // ζ 1.0  · 0%
  stiff: {stiffness: 400, damping: 40, mass: 1}, // ζ 1.0 · 0% (되튐 없음)
  slow: {stiffness: 50, damping: 20, mass: 1}, // ζ 1.41 · 0%
  paper: {stiffness: 260, damping: 33, mass: 1}, // ζ 1.02 · 0% — 메모의 '회전' 정착
  snap: {stiffness: 500, damping: 45, mass: 1}, // ζ 1.0 · 0% — 칩·배지·테이프
  heavy: {stiffness: 120, damping: 22, mass: 1}, // ζ 1.0  · 0% — 종이 판·전면
  float: {stiffness: 40, damping: 18, mass: 1}, // ζ 1.42 · 0% — 배경·시차
} as const;

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

export const tween = (frame: number, start: number, dur: number, ease: EaseName = 'outQuint') =>
  interpolate(frame, [start, start + Math.max(1, dur)], [0, 1], {...clamp, easing: EASE[ease]});

export const tweenOut = (frame: number, end: number, dur: number, ease: EaseName = 'inCubic') =>
  interpolate(frame, [end - Math.max(1, dur), end], [1, 0], {...clamp, easing: EASE[ease]});

export const springIn = (frame: number, fps: number, delay = 0, preset: keyof typeof SPRING = 'stiff') =>
  spring({frame: frame - delay, fps, config: SPRING[preset]});

/** 진입 + 퇴장(75%) 합성 가시도 */
export const visibility = (frame: number, total: number, enterDur: number = DUR.normal) =>
  Math.min(tween(frame, 0, enterDur), tweenOut(frame, total, exitFrames(enterDur)));

// ─────────────────────────────────────────────────────────────────────────────
// 모션 토큰 v2(docs/upgrade/06 6장 · 06b) — 값은 [제안], 스틸·시퀀스를 렌더해 확정한다.

/** 퇴장은 진입보다 짧다. 기본 0.75, 허용 0.6~0.87. */
export const EXIT_RATIO = 0.75;

/** 길이는 거리와 면적으로 고른다(30fps 프레임). distPct: 이동 거리(짧은 변 대비 %), areaPct: 요소 면적(프레임 대비 %) */
export const durFor = (distPct: number, areaPct = 0): number => {
  const d = distPct < 5 ? 8 : distPct < 15 ? 11 : distPct < 35 ? 15 : distPct < 60 ? 19 : 23;
  return Math.min(26, d + (areaPct > 50 ? 3 : areaPct > 25 ? 2 : 0));
};

/** 장식적 스태거의 총 길이 상한 15f(0.5초). 말에 맞춘 순차 등장(목록·단계)에는 쓰지 않는다. */
export const staggerFor = (n: number, base: number, cap = 15): number =>
  n <= 1 ? 0 : Math.max(1, Math.min(base, Math.floor(cap / (n - 1))));

/** 읽는 시간: 모든 모션이 끝난 뒤 글자가 멈춰 있어야 하는 길이 — max(1.2초, 글자 수 ÷ 7). */
export const HOLD = {cps: 7, minSec: 1.2} as const;
export const restFrames = (chars: number, fps = 30): number => Math.ceil(Math.max(HOLD.minSec, chars / HOLD.cps) * fps);

/** 부품 시간차(팔로스루): 본체 도착 기준 프레임. 꼬리는 maxTail 안에서 끝난다. */
export const FOLLOW = {shadow: 2, tape: 3, badge: 4, underline: 6, note: 8, maxTail: 12} as const;

/** 진입·퇴장 가족 — 변주 선택기가 고른다(06 문서 5·6장). */
export const ENTER_KINDS = ['place', 'slide', 'unfold', 'rule'] as const;
export const EXIT_KINDS = ['fade', 'peel', 'swap'] as const;
export type EnterKind = (typeof ENTER_KINDS)[number];
export type ExitKind = (typeof EXIT_KINDS)[number];

/** 손맛 스텝: hold 프레임마다만 값이 바뀐다. 종이·테이프·사진·손글씨에만(자막·화자·카메라·20f 넘는 이동 제외). */
export const stepFrame = (frame: number, hold = 2): number => Math.floor(frame / hold) * hold;

/** 보일: 정지한 종이가 4프레임마다 아주 조금 다르게 놓인다. 글자는 종이와 같은 변환 안에 둔다. */
export const BOIL = {hold: 4, rotate: 0.4, shift: 0.8, seeds: 3} as const; // ±도, ±px
const rnd = (n: number): number => {
  const x = Math.sin(n * 127.1 + 311.7) * 43758.5453;
  return x - Math.floor(x);
};
export const boil = (frame: number, seed: number): {rotate: number; dx: number; dy: number} => {
  const k = Math.floor(frame / BOIL.hold) % BOIL.seeds;
  const r = (i: number) => rnd(seed * 13 + k * 7 + i) * 2 - 1;
  return {rotate: r(1) * BOIL.rotate, dx: r(2) * BOIL.shift, dy: r(3) * BOIL.shift};
};

/**
 * 붙이기(place): 종이가 살짝 떠 있다가 내려앉는다 — 스케일 바운스가 아니라 회전과 그림자가 정착한다.
 * rest = 도착 각(tokens.ts paperRotate). elev 는 tokens.ts paperShadow(elev) 에 넣는다(3 → 1).
 */
export const placeIn = (frame: number, rest: number, dur = 10, step = true) => {
  const f = step ? stepFrame(frame, 2) : frame;
  const p = interpolate(f, [0, dur], [0, 1], {...clamp, easing: EASE.enter});
  return {
    opacity: interpolate(f, [0, Math.max(2, Math.round(dur * 0.4))], [0, 1], clamp), // 불투명도는 먼저 끝난다
    scale: 1.03 - 0.03 * p,
    translateY: -14 * (1 - p),
    // 회전은 위치보다 3f 늦게 끝나고 도착 각을 0.5° 지나쳤다 돌아온다
    rotate: interpolate(f, [0, Math.round(dur * 0.7), dur + 3], [rest + 2.5, rest - 0.5, rest], {...clamp, easing: EASE.outCubic}),
    elev: 3 - 2 * p,
  };
};

/** 펼치기(unfold): 테이프가 붙은 변을 축으로 열린다. clip 은 가려진 비율(1 → 0). */
export const unfoldIn = (frame: number, dur = 12) => {
  const p = interpolate(frame, [0, dur], [0, 1], {...clamp, easing: EASE.enter});
  return {clip: 1 - p, scaleCross: 0.96 + 0.04 * p, opacity: interpolate(frame, [0, 4], [0, 1], clamp)};
};

/** 떼기(peel) 퇴장: 테이프 쪽을 축으로 2° 돌며 뜬다. 불투명도는 마지막 4f 에만. */
export const peelOut = (frame: number, end: number, rest: number, dur = 8) => {
  const p = interpolate(frame, [end - dur, end], [0, 1], {...clamp, easing: EASE.exit});
  return {rotate: rest + 2 * p, translateY: -10 * p, elev: 1 + p, opacity: interpolate(frame, [end - 4, end], [1, 0], clamp)};
};

/** 역할 이름으로 쓰는 진입 진행도(0→1). tween() 과 같고 기본 곡선만 다르다. */
export const enterP = (frame: number, start: number, dur: number, role: 'enter' | 'enterText' | 'enterLarge' = 'enter') =>
  interpolate(frame, [start, start + Math.max(1, dur)], [0, 1], {...clamp, easing: EASE[role]});

/**
 * 떠다니는 움직임(플로팅) — 2026-10-04 채널 주인: "모션 그래픽은 떠다니는 움직임이 젠틀하게, 모션이 많아야 한다".
 * 결정적(같은 프레임은 늘 같은 값)인 느린 사인 두 개를 겹쳐 규칙적인 왕복처럼 보이지 않게 한다. amp px, period 초.
 */
export const floatOffset = (frame: number, fps: number, seed = 0, amp = 6, period = 6.5) => {
  const t = frame / fps;
  const ph = seed * 1.7;
  const y = amp * (0.7 * Math.sin((2 * Math.PI * t) / period + ph) + 0.3 * Math.sin((2 * Math.PI * t) / (period * 0.53) + ph * 2.3));
  const x = amp * 0.35 * Math.sin((2 * Math.PI * t) / (period * 1.37) + ph * 0.7);
  const rot = 0.35 * Math.sin((2 * Math.PI * t) / (period * 1.21) + ph * 1.3);
  return {x, y, rot};
};

/** 앰비언트 카메라 — 장면 내내 아주 느리게 다가간다(scale 1 → 1+push, 선형). 화면 가장자리가 드러나지 않게 1 이상만 */
export const ambientPush = (frame: number, dur: number, push = 0.03) =>
  1 + push * Math.min(1, Math.max(0, frame / Math.max(1, dur)));

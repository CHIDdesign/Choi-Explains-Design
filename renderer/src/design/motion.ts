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
  outBack: Easing.bezier(0.34, 1.56, 0.64, 1), // 아주 가끔: 숫자·아이콘 팝
  inExpo: Easing.bezier(0.7, 0, 0.84, 0), // 전환: 나가는 장면이 컷으로 빨려 들어감
  inQuart: Easing.bezier(0.5, 0, 0.75, 0),
  linear: Easing.linear,
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

export const SPRING = {
  gentle: {stiffness: 100, damping: 20, mass: 1},
  stiff: {stiffness: 400, damping: 30, mass: 1},
  slow: {stiffness: 50, damping: 20, mass: 1},
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

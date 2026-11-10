import React from 'react';
import {Img, staticFile} from 'remotion';
import {collageStep} from '../../design/motion';
import {FONT, MAT} from '../../design/tokens';
import {balanceLines, estWidth, fitBlock, fitSize} from '../../lib/fit';
import type {Cutout as CutoutData} from '../../lib/types';
import {seeded} from '../paper/Paper';
import {Sheet} from './Sheet';
import type {Edges} from './Sheet';
import {GrainLayer, TexBackdrop, useMaterials} from './Texture';
import type {TexName} from './Texture';

/**
 * 콜라주(템플릿 collage · 타이틀 · 챕터 · 숏폼 첫머리): 흑백 망점으로 인쇄해 오린 실제 사람·건물이 겹쳐 한 덩어리가 되는 것이 주인공, 머리 뒤로 대부분 가려진 평면색 원 하나,
 * 민짜 종이 바탕 + 초점이 나간 신문 조각 하나, 찢긴 이름표. 조각은 8fps 로 놓이고 멈춘다(되튐·떠다니기 없음). 사각 인화지는 예외로 한 장까지.
 */

export const NEWS_COPY = '도시는 한 사람이 혼자 쓰는 문장이 아니다. 골목의 폭과 창의 높이, 문턱 하나의 높낮이까지 누군가의 판단이 쌓여 우리가 걷는 속도를 정한다. '
  + '좋은 공간은 설명 없이도 몸이 먼저 안다. 그늘을 어디에 드리울지, 사람들이 어디서 멈춰 서게 할지, 그 작은 결정들이 모여 한 동네의 표정이 된다. '
  + '그래서 디자인을 읽는다는 것은 물건의 모양을 보는 일이 아니라 그 안에 숨은 결정을 찾아내는 일이다. 왜 여기에 계단이 있고 왜 저기에는 창이 없는가. ';

const CUT_SHADOW = 'drop-shadow(1px 2px 2px rgba(0,0,0,0.42)) drop-shadow(10px 14px 22px rgba(0,0,0,0.26))';   // 값이 프레임마다 바뀌지 않는다 — 위 왼쪽 빛
const STEP = 4;                    // 조각 사이 프레임(8fps 한 칸 ≈ 3.75)
const DISC: Record<string, string> = {mint: MAT.mint, orange: MAT.orange};
const GROUND: TexName[] = ['kraft', 'parchment', 'gray'];
const HEAD = 0.2;                  // 흉상 파일에서 머리 가운데의 높이(위에서)

type Slot = {cx: number; top: number; h: number; rot: number; z: number; maxW?: number; base?: number};      // maxW = 짧은 변에 대한 폭 상한 · base = 아래 끝의 최소 높이(무대 비율) — 몸통 뒤로 숨는다
type Placed = CutoutData & {s: Slot; i: number; bleed: boolean};

/** 자리(무대 비율): 첫 사람이 가운데 크게, 곁 인물은 어깨 뒤에서 머리만 나와 겹치고(아래 끝이 화면 밖이라 작게 놓으면 얼굴까지 어깨에 묻힌다), 건물 하나가 머리 뒤로 솟는다 — 실루엣이 하나다 */
const WIDE = {
  people: [{cx: 0.5, top: 0.1, h: 0.98, rot: -0.8, z: 6}, {cx: 0.335, top: 0.32, h: 0.72, rot: -4, z: 4}, {cx: 0.665, top: 0.28, h: 0.76, rot: 3.5, z: 5}, {cx: 0.18, top: 0.46, h: 0.58, rot: -6, z: 2}, {cx: 0.82, top: 0.46, h: 0.58, rot: 5, z: 3}],
  under: {top: 0.24, h: 0.86},      // 건물이 뒤에 있으면 사람은 조금 낮게 — 건물 꼭대기가 머리 위로 보인다
  place: {cx: 0.5, top: -0.02, h: 0.86, rot: 0.4, z: 1, maxW: 1.0, base: 0.84},
  skyline: [{cx: 0.5, top: 0.1, h: 0.98, rot: -0.6, z: 6}, {cx: 0.27, top: 0.32, h: 0.74, rot: -1.4, z: 4}, {cx: 0.74, top: 0.26, h: 0.8, rot: 1.2, z: 5}],
  print: {top: 0.1, h: 0.35, rot: 2.4, z: 0},      // 콜라주의 예외인 사각 인화지: 뒤쪽에 작게
  alone: {cx: 0.5, top: 0.14, h: 0.62, rot: -1, z: 6},
  disc: 0.23, maxW: 1.07,
};
const TALL = {
  people: [{cx: 0.5, top: 0.3, h: 0.72, rot: -0.8, z: 6}, {cx: 0.2, top: 0.42, h: 0.6, rot: -5, z: 4}, {cx: 0.8, top: 0.38, h: 0.64, rot: 4, z: 5}, {cx: 0.08, top: 0.5, h: 0.52, rot: -7, z: 2}, {cx: 0.92, top: 0.5, h: 0.52, rot: 6, z: 3}],
  under: {top: 0.33, h: 0.69},
  place: {cx: 0.5, top: 0.14, h: 0.66, rot: 0.4, z: 1, maxW: 1.5, base: 0.8},
  skyline: [{cx: 0.5, top: 0.27, h: 0.75, rot: -0.6, z: 6}, {cx: 0.2, top: 0.42, h: 0.6, rot: -1.4, z: 4}, {cx: 0.82, top: 0.38, h: 0.64, rot: 1.2, z: 5}],
  print: {top: 0.2, h: 0.2, rot: 2.4, z: 0},
  alone: {cx: 0.5, top: 0.3, h: 0.36, rot: -1, z: 6},
  disc: 0.24, maxW: 1.45,
};

const arrange = (items: CutoutData[], tall: boolean): Placed[] => {
  const T = tall ? TALL : WIDE;
  const indexed = items.map((c, i) => ({c, i}));
  const cut = indexed.filter(({c}) => c.cut);
  const people = cut.filter(({c}) => c.kind !== 'place');
  const places = cut.filter(({c}) => c.kind === 'place');
  const print = indexed.find(({c}) => !c.cut);
  const rect: Placed[] = print ? [{...print.c, i: print.i, s: cut.length ? {...T.print, cx: print.i % 2 ? 0.34 : 0.66} : T.alone, bleed: false}] : [];
  if (!people.length) return [...rect, ...places.slice(0, T.skyline.length).map(({c, i}, n) => ({...c, i, s: T.skyline[n], bleed: true}))];
  return [
    ...rect,
    ...places.slice(0, 1).map(({c, i}) => ({...c, i, s: T.place, bleed: false})),
    ...people.slice(0, T.people.length).map(({c, i}, n) => {
      const flank = places.length && n ? {h: T.people[n].h * 0.86, top: T.people[n].top + 0.08} : {};      // 곁 인물은 언제나 주인공보다 작다
      return {...c, i, bleed: true, s: n === 0 && places.length ? {...T.people[0], ...T.under} : {...T.people[n], ...flank}};
    }),
  ];
};

/** 조각의 상자. bleed = 아래 끝이 언제나 프레임 밖 — 오린 밑동이 화면 안에 보이면 종 모양 윤곽이 드러난다(기울어도 모서리가 안 올라오게) */
const pieceBox = (item: Placed, W: number, H: number) => {
  const a = item.w && item.h ? item.w / item.h : 0.9;
  const h = Math.min(item.s.h * H, ((item.s.maxW ?? (H > W ? TALL.maxW : WIDE.maxW)) * Math.min(W, H)) / a);
  const w = h * a;
  const low = item.bleed ? H + 40 + (w / 2) * Math.abs(Math.sin((item.s.rot * Math.PI) / 180)) : (item.s.base ?? 0) * H;
  return {w, h, left: item.s.cx * W - w / 2, top: Math.max(item.s.top * H, low - h)};
};

/** 8fps 로 놓인다: 첫 칸은 어긋나고, 둘째 칸에서 거의 제자리, 그다음 멈춘다 */
const landing = (frame: number, at: number, seed: number, fps: number) => {
  if (frame < at) return null;
  const k = collageStep(frame - at, fps);
  const off = k === 0 ? 1 : k === 1 ? 0.28 : 0;
  const r = seeded(seed + 0.1);
  return {x: (r() - 0.5) * 88 * off, y: (r() - 0.5) * 58 * off, rot: (r() - 0.5) * 7 * off};
};

const PieceImg: React.FC<{item: Placed; W: number; H: number; x: number; y: number; rot: number}> = ({item, W, H, x, y, rot}) => {  // W = 덩어리가 놓이는 폭
  const {w, h, left, top} = pieceBox(item, W, H);
  if (item.cut) return <Img src={staticFile(item.image)} style={{position: 'absolute', left: left + x, top: top + y, width: w, height: h, rotate: `${item.s.rot + rot}deg`, filter: CUT_SHADOW, zIndex: item.s.z}} />;
  const rim = 12;
  return (
    <div style={{position: 'absolute', left: left + x - rim, top: top + y - rim, width: w + 2 * rim, height: h + 2 * rim, rotate: `${item.s.rot + rot}deg`, background: MAT.memo, boxShadow: '1px 2px 3px rgba(0,0,0,0.4), 9px 14px 24px rgba(0,0,0,0.26)', zIndex: item.s.z}}>
      <Img src={staticFile(item.image)} style={{position: 'absolute', left: rim, top: rim, width: w, height: h, display: 'block'}} />
    </div>
  );
};

/** 신문 조각 하나(화면의 15~17%): 덩어리 뒤에서 절반 넘게 가려지고 자리·각도는 시드로 — 콜라주마다 같은 자리에 깔리면 템플릿이 드러난다 */
const newsScrap = (seed: number, W: number, H: number, tall: boolean, cy: number) => {
  const r = seeded(seed + 0.7);
  const side = r() < 0.5 ? -1 : 1;
  const [w, h] = tall ? [0.66 * W, 0.25 * H] : [0.3 * W, 0.52 * H];
  return {x: W / 2 - w / 2 + side * (0.07 + r() * 0.06) * W, y: cy - h / 2 + (r() - 0.5) * 0.08 * H, w, h, rot: side * (1.5 + r() * 2.5), torn: (side < 0 ? {left: true, top: true} : {right: true, top: true}) as Edges};
};

/** 이름표: 위아래만 불규칙하게 찢긴 거친 회색 종이에 작고 자간 넓은 명조 제호 + 작은 한 줄. 자막 위에서 끝난다 */
const NameLabel: React.FC<{name: string; sub?: string; W: number; H: number; seed: number; at: number; frame: number; fps: number; bottom: number; labelW?: number}> = ({name, sub, W, H, seed, at, frame, fps, bottom, labelW}) => {
  const place = landing(frame, at, seed + 40, fps);
  if (!place) return null;
  const tall = H > W;
  const pad = 44;
  const room = (labelW ?? (tall ? 0.55 : 0.3)) * W - 2 * pad;
  const {size} = fitBlock(name, room, 220, tall ? 84 : 72, 46, 1.22, 2, 0.02);
  const lines = balanceLines(name, size, room, 2, 0.02);
  const subSize = sub ? fitSize(sub, room, tall ? 30 : 26, 18, 0.04) : 0;
  const w = Math.min(room, Math.max(...lines.map((l) => estWidth(l, size, 0.02)), sub ? estWidth(sub, subSize, 0.04) : 0)) + 2 * pad;
  const h = lines.length * size * 1.22 + (sub ? subSize * 1.7 : 0) + 58;
  return (
    <Sheet x={(W - w) / 2 + place.x} y={H - bottom - h + place.y} w={w} h={h} tex="gray" seed={seed + 3} rotate={-1.5 + place.rot} liftLevel={2.4} torn={{top: true, bottom: true}} amp={14} fibre={10} style={{zIndex: 9, wordBreak: 'keep-all'}}>
      <div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: MAT.ink}}>
        {lines.map((l, i) => <div key={i} style={{fontFamily: FONT.masthead, fontWeight: 700, fontSize: size, lineHeight: 1.22, letterSpacing: '0.02em', whiteSpace: 'nowrap'}}>{l}</div>)}
        {sub ? <div style={{marginTop: subSize * 0.3, fontFamily: FONT.sans, fontWeight: 500, fontSize: subSize, lineHeight: 1.1, letterSpacing: '0.04em', color: MAT.inkSoft, whiteSpace: 'nowrap'}}>{sub}</div> : null}
      </div>
    </Sheet>
  );
};

/** 콜라주 무대. seed 로 바탕 종이 한 장과 신문 조각의 자리가 정해진다. disc = 'mint' | 'orange'(없으면 민트 — 오렌지는 세 곳에 한 곳까지). labelW = 이름표 폭(화면 비율, 영상 제목처럼 긴 글) */
export const Collage: React.FC<{items: CutoutData[]; W: number; H: number; frame: number; fps: number; seed: number; disc?: string; name?: string; sub?: string; bottom?: number;
  from?: number; noLabel?: boolean; narrow?: number; labelW?: number}> = ({items, W, H, frame, fps, seed, disc, name = '', sub, bottom, from = 2, noLabel = false, narrow, labelW}) => {
  useMaterials();
  const tall = H > W;
  const list = arrange(items.slice(0, 5), tall);
  const T = tall ? TALL : WIDE;
  const color = (disc && (DISC[disc] ?? (disc.startsWith('#') ? disc : undefined))) || MAT.mint;
  const paced = (i: number) => from + (i + 2) * STEP;     // 낱말에 맞춘 시각이 없으면 고르게
  const last = Math.max(0, ...list.map((c) => (c.at !== undefined ? c.at * fps : paced(c.i))));
  const discAt = landing(frame, from + STEP, seed + 30, fps);
  const R = T.disc * Math.min(W, H);
  const SW = narrow ?? W;           // 챕터 카드: 덩어리는 왼쪽, 오른쪽은 글이 놓일 종이
  const hero = list.reduce<Placed | undefined>((a, b) => (a && a.s.z >= b.s.z ? a : b), undefined);
  const box = hero ? pieceBox(hero, SW, H) : undefined;
  const hx = box ? box.left + box.w / 2 : SW / 2;
  const hy = (box ? box.top + (hero?.cut && hero.kind !== 'place' ? HEAD : 0.42) * box.h : 0.42 * H) - (tall ? 0.3 * R : 0);      // 원은 주인공 머리 뒤에서 대부분 가려진다(세로형은 머리가 원만큼 커서 조금 위로)
  const news = newsScrap(seed, SW, H, tall, hy);
  const newsAt = landing(frame, from, seed + 11, fps);
  return (
    <div style={{position: 'absolute', inset: 0, overflow: 'hidden', isolation: 'isolate'}}>{/* 조각의 zIndex 가 자막 위로 새지 않게 */}
      <TexBackdrop name={GROUND[Math.abs(seed) % GROUND.length]} seed={seed} />
      <GrainLayer opacity={0.08} />
      {newsAt ? <Sheet x={news.x + newsAt.x} y={news.y + newsAt.y} w={news.w} h={news.h} tex="newsblur" seed={seed + 7} rotate={news.rot + newsAt.rot} liftLevel={1.4} torn={news.torn} amp={14} on="board" /> : null}
      {discAt ? <div style={{position: 'absolute', left: hx - R + discAt.x, top: hy - R + discAt.y, width: 2 * R, height: 2 * R, borderRadius: '50%', rotate: '45deg', backgroundColor: color,
        backgroundImage: 'radial-gradient(circle, rgba(34,33,30,0.2) 1.3px, transparent 1.8px)', backgroundSize: '6px 6px'}} /> : null}
      {list.map((item) => {
        const at = item.at !== undefined ? item.at * fps : paced(item.i);
        const p = landing(frame, at, seed + item.i * 13 + 1, fps);
        return p ? <PieceImg key={item.image + item.i} item={item} W={SW} H={H} x={p.x} y={p.y} rot={p.rot} /> : null;
      })}
      {name && !noLabel ? <NameLabel name={name} sub={sub} W={W} H={H} seed={seed} at={last + STEP} frame={frame} fps={fps} bottom={bottom ?? (tall ? 500 : 212)} labelW={labelW} /> : null}
    </div>
  );
};

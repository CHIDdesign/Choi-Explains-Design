import React from 'react';
import {Img, OffthreadVideo, interpolate, staticFile} from 'remotion';
import {EASE} from '../../design/motion';
import {MODERN} from '../../design/tokens';
import {coverMap, tooSoft} from '../../lib/crop';
import type {MapFn, Pt, Rect} from '../../lib/crop';
import type {EvidenceAsset, GraphicData} from '../../lib/types';
import type {TemplateProps} from '../graphics/common';
import {ArchiveSheet, DeskDocument} from '../material/Document';
import {PhotoOverlays} from '../material/Overlays';
import {CenterWord, CornerCredit, QuoteSlot, Super, superOn, superRight} from '../modern/Modern';

/**
 * 증거 자료(evidence) — 디자인 v5: 실물을 전면으로 끊어 넣는다. 각진 풀블리드, 액자·테이프·필름 룩 없음, 움직임은 약한 3% 푸시뿐,
 * 우하단 출처는 항상. 세로 자료는 대상이 보이는 띠 안에 들면 잘라 전면으로, 아니면 모눈 작업지 위 인쇄물로.
 */

type Win = {w: number; h: number; cover?: boolean; soft?: boolean};
const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

/** 세로 사진을 전면으로 잘라도 되는가: 화질이 버티고, 볼 대상(초점 상자)이 보이는 띠 안에 다 든다 */
const cropHolds = (a: EvidenceAsset, win: Win) => !!a.focus && a.w >= win.w * 0.6 && a.focus[3] * 1.1 <= a.w / a.h / (win.w / win.h);

/** 사진·영상은 cover(초점 상자 쪽을 남긴다), 세로 사진은 대상이 띠 안에 들 때만 잘라 전면으로, 아니면 책상 위 인쇄물로. 문서·화면·로고는 자르지 않는다 */
const fitFor = (a: EvidenceAsset, win: Win): 'cover' | 'contain' => {
  if (win.cover) return 'cover';                 // 인용·흐림 바탕: 세로 자료를 그대로 흐리면 회색 기둥 + 검은 기둥이 된다
  if (a.kind !== 'photo' && a.kind !== 'video') return 'contain';
  if (!a.w || !a.h) return 'cover';
  if (a.kind === 'photo' && tooSoft(a.w, a.h, win.w, win.h, win.soft)) return 'contain';   // 흐려지는 사진은 전면으로 키우지 않고 책상 위 인화지로
  return a.w / a.h < 1.0 && win.w / win.h > 1.0 && !cropHolds(a, win) ? 'contain' : 'cover';
};

/** objectPosition(0~1): 초점 상자가 크롭의 가운데에 오게(object-position 은 백분율 정렬이라 상자 가운데 값을 그대로 주면 치우친다) */
const focusOf = (a: EvidenceAsset, win: Win): [number, number] => {
  const [fx, fy, fw, fh] = a.focus ?? [0.3, 0.3, 0.4, 0.4];
  if (!a.w || !a.h) return [fx + fw / 2, fy + fh / 2];
  const s = Math.max(win.w / a.w, win.h / a.h);
  const pos = (c: number, v: number) => (v < 1 ? Math.max(0, Math.min(1, (c - v / 2) / (1 - v))) : 0.5);
  return [pos(fx + fw / 2, win.w / (a.w * s)), pos(fy + fh / 2, win.h / (a.h * s))];
};

const winOf = (d: GraphicData, W: number, H: number): Win => ({w: W, h: H, cover: !!d.quote || d.tone === 'blur', soft: d.safe?.soft});

/** 첫 그림의 초점 상자 가운데가 화면 어디에 그려지는가(크롭 반영) — 조각 전환이 대상 둘레에서 열리게. 책상 위 인쇄물은 인쇄물 가운데 */
export const focusPoint = (d: GraphicData, W: number, H: number): Pt | null => {
  const a = d.assets?.[0];
  if (!a?.focus) return null;
  const win = winOf(d, W, H);
  const fit = fitFor(a, win);
  if ((a.kind === 'photo' || a.kind === 'document') && fit === 'contain') return [W * 0.54, (H - 130) / 2];
  const [px, py] = focusOf(a, win);
  const map = coverMap(a.w, a.h, W, H, px, py, fit);
  return map ? map(a.focus[0] + a.focus[2] / 2, a.focus[1] + a.focus[3] / 2) : null;
};

/** 대상(초점 상자) 쪽으로 약한 3% 푸시 — 문서·화면·로고는 움직이지 않는다. children(그림 위 그래픽)은 그림과 함께 움직인다 */
const AssetFill: React.FC<{asset: EvidenceAsset; win: Win; frame: number; dur: number; children?: React.ReactNode}> = ({asset, win, frame, dur, children}) => {
  const [cx, cy] = focusOf(asset, win).map((v) => v * 100);
  const still = asset.kind === 'document' || asset.kind === 'screen' || asset.kind === 'logo';
  const s = still ? 1 : interpolate(frame, [0, Math.max(1, dur)], [1, 1.03], clamp);
  const style: React.CSSProperties = {width: '100%', height: '100%', objectFit: fitFor(asset, win), objectPosition: `${cx}% ${cy}%`};
  return (
    <div style={{position: 'absolute', inset: 0, transformOrigin: `${cx}% ${cy}%`, scale: `${s}`}}>
      {asset.kind === 'video' ? <OffthreadVideo src={staticFile(asset.src)} muted style={style} />
        : <Img src={staticFile(asset.src)} style={style} />}
      {children}
    </div>
  );
};

/** 여러 장은 같은 길이로 하드 컷 */
const AssetSequence: React.FC<{assets: EvidenceAsset[]; win: Win; frame: number; dur: number; children?: React.ReactNode}> = ({assets, win, frame, dur, children}) => {
  const n = Math.max(1, assets.length);
  const seg = dur / n;
  const i = Math.min(n - 1, Math.floor(frame / Math.max(1, seg)));
  const a = assets[i];
  return <AssetFill key={a.src + i} asset={a} win={win} frame={frame - i * seg} dur={seg}>{children}</AssetFill>;
};

/** 화면 캡처: 가짜 브라우저 틀 없이 폭에 맞춰, 0.8초 멈춘 뒤 천천히 스크롤(초당 창 높이 35% 이하) */
const ScreenScroll: React.FC<{asset: EvidenceAsset; win: Win; frame: number; dur: number; fps: number}> = ({asset, win, frame, dur, fps}) => {
  const k = win.w / Math.max(1, asset.w);
  const maxY = Math.max(0, asset.h * k - win.h);
  const hold = Math.round(0.8 * fps);
  const span = Math.max(1, dur - 2 * hold);
  const limit = (0.35 * win.h * span) / fps;
  const y = interpolate(frame, [hold, hold + span], [0, -Math.min(maxY * 0.6, limit)], {...clamp, easing: EASE.inOutCubic});
  return (
    <div style={{position: 'absolute', inset: 0, overflow: 'hidden', background: '#FFFFFF'}}>
      <Img src={staticFile(asset.src)} style={{position: 'absolute', left: 0, top: y, width: win.w, height: asset.h * k}} />
    </div>
  );
};

/** 여러 장 격자·나란히: 맞붙은 칸 */
const Grid: React.FC<{assets: EvidenceAsset[]; win: Win; cols: number}> = ({assets, win, cols}) => {
  const rows = Math.ceil(assets.length / cols);
  const cw = win.w / cols;
  const ch = win.h / rows;
  return (
    <>
      {assets.map((a, i) => (
        <div key={a.src + i} style={{position: 'absolute', left: (i % cols) * cw, top: Math.floor(i / cols) * ch, width: cw, height: ch,
          overflow: 'hidden', background: MODERN.dark}}>
          <Img src={staticFile(a.src)} style={{width: '100%', height: '100%', objectFit: fitFor(a, {w: cw, h: ch})}} />
        </div>
      ))}
    </>
  );
};

/** 증거 템플릿 — treatment 로 모양을 가른다(전면 전용) */
export const EvidenceCard: React.FC<TemplateProps> = ({data, frame, dur, fps, theme, box}) => {
  const W = box.w;
  const H = box.h;
  const assets = data.assets ?? [];
  const t = data.treatment ?? (assets.length ? 'hero' : 'archive_card');
  const win = winOf(data, W, H);
  if (t === 'archive_card' || !assets.length) {
    const arc = data.archive ?? {variant: 'type' as const, title: data.title ?? '', rows: []};
    return <><ArchiveSheet archive={arc} fallbackLabel={data.title !== arc.title ? data.title : ''} W={W} H={H} /><CornerCredit text={data.credit || ''} /></>;
  }
  const first = assets[0];
  const layers = (map: MapFn | null, grain = true, onDesk = false, view?: Rect) => <PhotoOverlays data={data} map={map} W={W} H={H} frame={frame} fps={fps} grain={grain} marks={!data.quote && !data.display} onDesk={onDesk} view={view} />;
  const swept = (data.overlays ?? []).filter((o) => o.kind === 'highlight' && o.box);    // 형광펜: 비전이 문서에서 찾은 줄을 그 낱말에
  const markY = data.overlays?.find((o) => o.kind === 'dimension' && o.poly?.length === 2)?.poly?.[0][1];    // 확대돼도 치수선이 화면에 남게
  // 세로 자료는 한 가지 방식으로만: 책상 위 인쇄물 + 접촉 그림자
  const print = (first.kind === 'photo' || first.kind === 'document') && fitFor(first, win) === 'contain' && t !== 'doc_highlight' && t !== 'grid' && t !== 'compare_pair';
  let inner: React.ReactNode;
  if (t === 'browser_frame' && first.kind === 'screen') inner = <><ScreenScroll asset={first} win={win} frame={frame} dur={dur} fps={fps} />{layers(null, false)}</>;
  else if (t === 'doc_highlight' && first.kind === 'document') inner = <DeskDocument asset={first} lines={swept.map((o) => o.box!)} lineAt={swept.map((o) => o.at ?? 0)} markY={markY} W={W} H={H} frame={frame} dur={dur} fps={fps} accent={theme.accent}>{(m, v) => layers(m, false, true, v)}</DeskDocument>;
  else if (t === 'grid' && assets.length >= 4) inner = <><Grid assets={assets.slice(0, 9)} win={win} cols={assets.length <= 4 ? 2 : 3} />{layers(null)}</>;
  else if (t === 'compare_pair' && assets.length >= 2) inner = <><Grid assets={assets.slice(0, 2)} win={win} cols={2} />{layers(null)}</>;
  else if (print) {
    const seg = dur / assets.length;
    const i = Math.min(assets.length - 1, Math.floor(frame / Math.max(1, seg)));
    inner = <DeskDocument key={i} asset={assets[i]} markY={markY} W={W} H={H} frame={frame - i * seg} dur={seg} fps={fps} clearLeft={superRight(data.title, data.caption || data.year)}>{(m, v) => layers(m, false, true, v)}</DeskDocument>;
  } else {
    // 오림으로 얹는 둘째 그림은 차례로 보여 주지 않는다
    const shown = data.overlays?.some((o) => o.kind === 'cutout') ? assets.slice(0, 1) : assets;
    const [px, py] = focusOf(first, win);
    inner = <AssetSequence assets={shown} win={win} frame={frame} dur={dur}>{layers(coverMap(first.w, first.h, W, H, px, py, fitFor(first, win)), first.kind === 'photo' || first.kind === 'video')}</AssetSequence>;
  }
  return (
    <div style={{position: 'absolute', inset: 0, overflow: 'hidden', background: '#0B0B0B'}}>
      {inner}
      {data.display && !data.quote ? <div style={{position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.4)'}} /> : null}
      {data.quote ? <QuoteSlot text={data.quote} W={W} H={H} frame={frame} />
        : data.display ? <CenterWord text={data.display} sub={data.year || data.title} W={W} H={H} frame={frame} y={0.46} />
          : data.title ? <Super name={data.title} sub={data.caption || data.year} theme={theme} box={box} frame={frame} on={print || first.kind !== 'photo' ? undefined : superOn(data.safe?.lum, coverMap(first.w, first.h, W, H, ...focusOf(first, win), fitFor(first, win)), box, data.title, data.caption || data.year)} /> : null}
      <CornerCredit text={data.credit || first.credit || ''} tall={H > W} />
    </div>
  );
};

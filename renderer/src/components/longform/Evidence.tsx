import React from 'react';
import {Img, OffthreadVideo, interpolate, staticFile} from 'remotion';
import {DUR, EASE, LONG, STAGGER, tween, tweenOut} from '../../design/motion';
import {FONT, NOTE, paperShadow, MODERN} from '../../design/tokens';
import type {Theme} from '../../design/tokens';
import type {EvidenceAsset, GraphicData, NBox} from '../../lib/types';
import type {TemplateProps} from '../graphics/common';
import {hashSeed} from '../paper/Paper';
import {CornerCredit, FilmLook, Halftone, PaperFiber, PaperNote} from './Note';
import {Numerals, RiseLine, Rule} from './Stage';
import {CollageScene} from '../press/CollageScene';
import {GRADE_QUOTE, Highlighter, NameChip, PaperStage, QuoteOverlay, pressColors} from '../press/Press';

/**
 * 증거 자료(evidence) — 사진을 "붙이지" 않고 "편집"한다(docs/upgrade/03b_자료_트리트먼트_컴포넌트.md).
 * P1: EvidenceFrame(공통 껍데기) · FocusMove(대상을 아는 켄 번즈) · ArchiveCard(자료·출처·타이포 카드) · DocHighlight(문서) ·
 * BrowserFrame(화면 캡처) + 여러 장(크로스 디졸브 시퀀스 · 그리드 · 나란히). 색은 크림 종이 · 웜 잉크 · 시그널 셋뿐,
 * 움직임은 tween(useCurrentFrame 기반)만, 화면 전체 필터 없음. 자막 띠(y 900~1026)는 비운다.
 */

type Box = {x: number; y: number; w: number; h: number};
// 16:9 무대 치수(03b 2절): hero = 종이 내용 96,84,1728×796 → 이미지 창 1728×724 + 캡션 줄 72
export const HERO: Box = {x: 96, y: 84, w: 1728, h: 724};
const CAP_H = 72;

const sx = (W: number) => W / 1920;

/** 사진·스톡 영상은 창을 채우고(cover — 초점 상자 쪽을 남긴다), 세로 사진·포스터·문서·화면·로고는 자르지 않고 맞춘다
 *  (03b 3절 — 남는 곳은 종이) */
const fitFor = (a: EvidenceAsset, win: {w: number; h: number}): 'cover' | 'contain' => {
  if (a.kind !== 'photo' && a.kind !== 'video') return 'contain';
  if (!a.w || !a.h) return 'cover';
  return a.w / a.h < 1.0 && win.w / win.h > 1.0 ? 'contain' : 'cover';
};

/** FocusMove — 화면 중앙이 아니라 대상(초점 상자)의 중심을 향해 아주 느리게(4~8%). 문서·화면 캡처에는 쓰지 않는다 */
export const FocusMove: React.FC<{asset: EvidenceAsset; win: {w: number; h: number}; frame: number; dur: number;
  move?: 'in' | 'out' | 'pan'; amount?: number; fit?: 'cover' | 'contain'}> = ({asset, win, frame, dur, move = 'in',
  amount = 0.06, fit}) => {
  const [fx, fy, fw, fh] = asset.focus ?? [0.3, 0.3, 0.4, 0.4];
  const cx = (fx + fw / 2) * 100;
  const cy = (fy + fh / 2) * 100;
  const still = asset.kind === 'document' || asset.kind === 'screen' || asset.kind === 'logo';
  const t = interpolate(frame, [0, Math.max(1, dur)], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
    easing: EASE.inOutCubic});
  const amt = still ? 0.015 : asset.kind === 'video' ? 0.03 : amount;
  const s = move === 'out' ? 1 + amt * (1 - t) : 1 + amt * t;
  const tx = move === 'pan' && !still ? interpolate(t, [0, 1], [-1.5, 1.5]) : 0;
  const f = fit ?? fitFor(asset, win);
  const style: React.CSSProperties = {width: '100%', height: '100%', objectFit: f, objectPosition: `${cx}% ${cy}%`};
  return (
    <div style={{position: 'absolute', inset: 0, transformOrigin: `${cx}% ${cy}%`, scale: `${s}`, translate: `${tx}% 0`}}>
      {asset.kind === 'video'
        ? <OffthreadVideo src={staticFile(asset.src)} muted style={style} />
        : <Img src={staticFile(asset.src)} style={style} />}
    </div>
  );
};

/** 여러 장을 한 그래픽 안에서 크로스 디졸브로(장당 같은 길이, 15f 겹침), 움직임 방향은 번갈아(같은 푸시인 3연속 금지) */
const AssetSequence: React.FC<{assets: EvidenceAsset[]; win: {w: number; h: number}; frame: number; dur: number;
  bleed?: boolean}> = ({assets, win, frame, dur}) => {
  const n = Math.max(1, assets.length);
  const seg = dur / n;
  const moves: Array<'in' | 'out' | 'pan'> = ['in', 'out', 'pan'];
  return (
    <>
      {assets.map((a, i) => {
        const a0 = i * seg;
        const a1 = a0 + seg;
        const vis = i === 0 ? 1 : tween(frame, a0 - 7, 15, 'inOutCubic');
        const gone = i === n - 1 ? 1 : 1 - tween(frame, a1 - 7, 15, 'inOutCubic');
        const op = Math.min(vis, gone);
        if (frame < a0 - 8 || (i < n - 1 && frame > a1 + 9)) return null;
        return (
          <div key={a.src + i} style={{position: 'absolute', inset: 0, opacity: op, overflow: 'hidden'}}>
            <FocusMove asset={a} win={win} frame={frame - a0} dur={seg + 15} move={moves[i % 3]} />
          </div>
        );
      })}
    </>
  );
};

/** 캡션 줄: 왼쪽 = 라벨(주장, Jua) + 캡션(사실, Pretendard + 숫자 Playfair), 오른쪽 = 출처(22px) */
const CaptionRow: React.FC<{x: number; y: number; w: number; label?: string; caption?: string; credit?: string;
  frame: number; theme: Theme}> = ({x, y, w, label, caption, credit, frame, theme}) => (
  <div style={{position: 'absolute', left: x, top: y, width: w, height: CAP_H, display: 'flex', alignItems: 'center',
    gap: 22}}>
    {label ? (
      <RiseLine frame={frame} delay={8}>
        <div style={{fontFamily: FONT.serif, fontWeight: 700, fontSize: 42, color: NOTE.ink, whiteSpace: 'nowrap',
          borderBottom: `4px solid ${theme.accentTint}`, paddingBottom: 2}}>{label}</div>
      </RiseLine>
    ) : null}
    {caption ? (
      <RiseLine frame={frame} delay={11}>
        <div style={{fontFamily: FONT.sans, fontWeight: 500, fontSize: 28, color: NOTE.inkSoft, whiteSpace: 'nowrap'}}>
          <Numerals text={caption} />
        </div>
      </RiseLine>
    ) : null}
    <div style={{flex: 1}} />
    {credit ? (
      <div style={{fontFamily: FONT.sans, fontWeight: 500, fontSize: 22, color: NOTE.note, whiteSpace: 'nowrap',
        overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: w * 0.5, opacity: tween(frame, 10, DUR.normal)}}>
        {credit}
      </div>
    ) : null}
  </div>
);

/** DocHighlight(디자인 v3, 레퍼런스 2번) — 문서가 화면을 채우고 핵심 줄 뒤에 형광펜이 왼→오로 칠해진 뒤 그 줄 쪽으로
 *  아주 느리게 다가간다. 어둡게 덮지 않는다(문서가 주인공). 줄 좌표가 없으면 느린 푸시만. */
const DocHighlight: React.FC<{asset: EvidenceAsset; lines?: NBox[]; quote?: string; win: {w: number; h: number};
  frame: number; fps: number; dur: number; theme: Theme}> = ({asset, lines = [], win, frame, fps, dur, theme}) => {
  const k = Math.min(win.w / Math.max(1, asset.w), (win.h * 1.25) / Math.max(1, asset.h));
  const w = asset.w * k;
  const h = asset.h * k;
  const ox = (win.w - w) / 2;
  const oy = Math.min(0, (win.h - h) / 2);
  const f0 = Math.round(0.9 * fps);
  const first = lines[0];
  const fx = first ? (first[0] + first[2] / 2) * 100 : 50;
  const fy = first ? (first[1] + first[3] / 2) * 100 : 35;
  const push = interpolate(frame, [f0, Math.max(f0 + 1, dur)], [1, first ? 1.09 : 1.03],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: EASE.move});
  return (
    <div style={{position: 'absolute', inset: 0, overflow: 'hidden'}}>
      <div style={{position: 'absolute', left: ox, top: oy, width: w, height: h, scale: `${push}`,
        transformOrigin: `${fx}% ${fy}%`, boxShadow: paperShadow(2)}}>
        <Img src={staticFile(asset.src)} style={{position: 'absolute', inset: 0, width: '100%', height: '100%',
          filter: 'saturate(0.88) contrast(1.04)'}} />
        {lines.map(([x, y, lw, lh], i) => (
          <Highlighter key={i} x={x * w - 10} y={y * h - lh * h * 0.08} w={lw * w + 20} h={lh * h * 1.16} theme={theme}
            p={tween(frame, f0 + i * 6, 14, 'enter')} />
        ))}
      </div>
    </div>
  );
};

/** DocPage(디자인 v3, 레퍼런스 2번) — 종이 무대 위에 스캔한 문서 한 장이 크게(화면 너비 60%) 비스듬히 놓이고, 뒤에 한 장이
 *  더 겹친다. 핵심 줄이 화면 가운데쯤 오게 놓고 형광펜이 왼→오로 칠해진 뒤 그 줄 쪽으로 아주 느리게 다가간다(7%).
 *  긴 문서는 위아래가 화면 밖으로 잘린다 — 문서가 주인공이고 여백은 종이. */
const DocPage: React.FC<{asset: EvidenceAsset; lines?: NBox[]; title?: string; frame: number; fps: number; dur: number;
  theme: Theme; W: number; H: number; seed: number}> = ({asset, lines = [], title, frame, fps, dur, theme, W, H, seed}) => {
  const ar = Math.max(0.3, (asset.w || 3) / Math.max(1, asset.h || 4));
  const pw = Math.min(W * 0.6, H * 1.25 * ar);
  const ph = pw / ar;
  const first = lines[0];
  const ly = first ? (first[1] + first[3] / 2) * ph : ph * 0.32;
  const fit = ph < H * 0.8;
  const top = fit ? (H * 0.84 - ph) / 2 + H * 0.02 : Math.max(H * 0.82 - ph, Math.min(H * 0.08, H * 0.44 - ly));
  const left = (W - pw) / 2 + (seed % 2 ? 1 : -1) * W * 0.025;
  const rot = ((seed % 5) - 2) * 0.45;
  const pin = tween(frame, 0, 12, 'enter');
  const f0 = Math.round(0.8 * fps);
  const push = interpolate(frame, [f0, Math.max(f0 + 1, dur)], [1, first ? 1.07 : 1.03], {...clampX, easing: EASE.move});
  const ox = first ? ((first[0] + first[2] / 2) * pw + left) / W * 100 : 50;
  const oy = (top + ly) / H * 100;
  return (
    <div style={{position: 'absolute', inset: 0, overflow: 'hidden', scale: `${push}`, transformOrigin: `${ox}% ${oy}%`}}>
      <div style={{position: 'absolute', left: left + pw * 0.035, top: top + H * 0.02, width: pw, height: ph,
        background: '#E7E2D6', rotate: `${rot + 2.2}deg`, boxShadow: paperShadow(1), opacity: pin}} />
      <div style={{position: 'absolute', left, top, width: pw, height: ph, rotate: `${rot}deg`, boxShadow: paperShadow(2),
        opacity: Math.min(1, pin * 1.4), translate: `0 ${interpolate(pin, [0, 1], [28, 0])}px`}}>
        <Img src={staticFile(asset.src)} style={{position: 'absolute', inset: 0, width: '100%', height: '100%',
          filter: 'saturate(0.85) contrast(1.05) sepia(0.08)'}} />
        {lines.map(([x, y, lw, lh], i) => (
          <Highlighter key={i} x={x * pw - 10} y={y * ph - lh * ph * 0.08} w={lw * pw + 20} h={lh * ph * 1.16} theme={theme}
            p={tween(frame, f0 + i * 6, 14, 'enter')} />
        ))}
      </div>
      {title ? (
        <div style={{position: 'absolute', left: W * 0.07, top: H * 0.1}}>
          <NameChip text={title} theme={theme} frame={frame} delay={10} size={40 * (W / 1920)} />
        </div>
      ) : null}
    </div>
  );
};
const clampX = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

/** BrowserFrame — 도식 틀(점 셋 + 도메인) 안의 화면 캡처, 0.8초 멈춘 뒤 천천히 스크롤(초당 창 높이 35% 이하) */
const BrowserFrame: React.FC<{asset: EvidenceAsset; url?: string; win: {w: number; h: number}; frame: number;
  dur: number; fps: number}> = ({asset, url, win, frame, dur, fps}) => {
  const bar = 56;
  const vw = win.w;
  const vh = win.h - bar;
  const k = vw / Math.max(1, asset.w);
  const maxY = Math.max(0, asset.h * k - vh);
  const hold = Math.round(0.8 * fps);
  const span = Math.max(1, dur - 2 * hold);
  const limit = (0.35 * vh * span) / fps;              // 스크롤 속도 상한
  const y = interpolate(frame, [hold, hold + span], [0, -Math.min(maxY * 0.6, limit)],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: EASE.inOutCubic});
  const domain = (url || '').replace(/^https?:\/\/(www\.)?/, '').split('/')[0];
  return (
    <div style={{position: 'absolute', inset: 0, borderRadius: 14, overflow: 'hidden', background: MODERN.card,
      boxShadow: paperShadow(2)}}>
      <div style={{height: bar, background: MODERN.bg, display: 'flex', alignItems: 'center', gap: 10,
        padding: '0 20px'}}>
        {[0, 1, 2].map((i) => <i key={i} style={{width: 12, height: 12, borderRadius: 6, background: NOTE.rule}} />)}
        <span style={{marginLeft: 16, fontFamily: FONT.sans, fontSize: 24, color: NOTE.inkSoft}}>{domain}</span>
      </div>
      <div style={{position: 'relative', height: vh, overflow: 'hidden'}}>
        <Img src={staticFile(asset.src)} style={{position: 'absolute', left: 0, top: y, width: vw, height: asset.h * k}} />
      </div>
    </div>
  );
};

/** 여러 장 격자(4~9장): 칸마다 5f 스태거로 깔린다 */
const ImageGrid: React.FC<{assets: EvidenceAsset[]; win: {w: number; h: number}; frame: number}> = ({assets, win,
  frame}) => {
  const n = assets.length;
  const cols = n <= 4 ? 2 : 3;
  const rows = Math.ceil(n / cols);
  const gap = 14;
  const cw = (win.w - gap * (cols - 1)) / cols;
  const ch = (win.h - gap * (rows - 1)) / rows;
  return (
    <>
      {assets.map((a, i) => {
        const p = tween(frame, i * STAGGER.item, DUR.slow, 'outCubic');
        return (
          <div key={a.src + i} style={{position: 'absolute', left: (i % cols) * (cw + gap), top: Math.floor(i / cols) * (ch + gap),
            width: cw, height: ch, overflow: 'hidden', opacity: p, translate: `0 ${interpolate(p, [0, 1], [14, 0])}px`,
            background: MODERN.bg}}>
            <Img src={staticFile(a.src)} style={{width: '100%', height: '100%', objectFit: fitFor(a, {w: cw, h: ch})}} />
          </div>
        );
      })}
    </>
  );
};

/** 나란히(A 대 B) — B 가 10프레임 늦게, 가운데 괘선 */
const ComparePair: React.FC<{a: EvidenceAsset; b: EvidenceAsset; win: {w: number; h: number}; frame: number}> = ({a, b,
  win, frame}) => {
  const gap = 48;
  const w = (win.w - gap) / 2;
  const h = win.h - 56;
  return (
    <>
      {[a, b].map((x, i) => {
        const p = tween(frame, i * 10, DUR.slow);
        return (
          <div key={i} style={{position: 'absolute', left: i * (w + gap), top: 0, width: w, height: h, overflow: 'hidden',
            opacity: p, translate: `0 ${interpolate(p, [0, 1], [18, 0])}px`, background: MODERN.bg}}>
            <Img src={staticFile(x.src)} style={{width: '100%', height: '100%', objectFit: 'contain'}} />
          </div>
        );
      })}
      <div style={{position: 'absolute', left: w + gap / 2 - 1, top: 0, width: 2, height: h * tween(frame, 8, LONG.rule),
        background: NOTE.rule}} />
      {[a, b].map((x, i) => (x.meta?.title ? (
        <div key={`l${i}`} style={{position: 'absolute', left: i * (w + gap), top: h + 10, width: w, textAlign: 'center',
          fontFamily: FONT.round, fontSize: 34, color: NOTE.ink, opacity: tween(frame, 14 + i * 6, DUR.normal),
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis'}}>{x.meta.title}</div>
      ) : null))}
    </>
  );
};

/** ArchiveCard — 자료 카드(사진 + 사실) · 출처 카드(논문·책: 제목·저자·저널·연도·DOI) · 타이포 자료 카드(글자만) */
const ArchiveCard: React.FC<{data: GraphicData; frame: number; dur: number; W: number; H: number; theme: Theme;
  seed: number; id: string}> = ({data, frame, dur, W, H, theme, seed, id}) => {
  const arc = data.archive ?? {variant: 'type' as const, title: data.title ?? '', rows: []};
  const rows = arc.rows ?? [];
  const asset = (data.assets ?? [])[0];
  const photo = arc.variant === 'photo' && asset;
  const k = sx(W);
  const w = Math.round((photo ? 1180 : 1240) * k);
  // 글자 카드는 내용만큼(라벨 · 제목 · 괘선 · 줄마다 52px) — 빈 종이가 남지 않게
  const h = Math.round((photo ? 780 : 330 + 52 * (arc.rows ?? []).length + (arc.title.length > 34 ? 70 : 0)) * k);
  const x = Math.round((W - w) / 2);
  const y = Math.round(photo ? 70 * k : (H - h) / 2 - 60 * k);
  const pad = 44 * k;
  const innerW = w - pad * 2;
  const label = arc.label || data.title || '';
  return (
    <div style={{position: 'absolute', inset: 0, background: MODERN.bg}}>
      <Halftone opacity={0.3} />
      <PaperNote x={x} y={y} w={w} h={h} frame={frame} dur={dur} from="right" theme={theme} seed={seed} pad={pad} id={`ac${id}`}>
        {photo ? (
          <div style={{position: 'relative', width: innerW, height: h * 0.56, overflow: 'hidden', background: MODERN.bg}}>
            <FocusMove asset={asset} win={{w: innerW, h: h * 0.56}} frame={frame} dur={dur} amount={0.04} />
          </div>
        ) : label && label !== arc.title ? (
          <RiseLine frame={frame} delay={4}>
            <div style={{display: 'inline-block', fontFamily: FONT.round, fontSize: 34 * k, color: NOTE.ink,
              borderBottom: `4px solid ${theme.accent}`, marginBottom: 18 * k}}>{label}</div>
          </RiseLine>
        ) : null}
        <RiseLine frame={frame} delay={6} style={{marginTop: photo ? 22 * k : 6 * k}}>
          <div style={{fontFamily: arc.variant === 'source' ? FONT.serif : FONT.display,
            fontWeight: arc.variant === 'source' ? 600 : 900, fontSize: (photo ? 44 : arc.variant === 'source' ? 58 : 72) * k,
            lineHeight: 1.18, color: NOTE.ink, letterSpacing: '-0.02em'}}>
            {arc.variant === 'source' ? <Numerals text={arc.title} /> : arc.title}
          </div>
        </RiseLine>
        <div style={{margin: `${18 * k}px 0 ${16 * k}px`}}>
          <Rule frame={frame} delay={10} color={NOTE.rule} thick={2} />
        </div>
        {rows.map((r, i) => (
          <RiseLine key={i} frame={frame} delay={12 + i * STAGGER.line}>
            <div style={{display: 'flex', gap: 18 * k, fontFamily: FONT.sans, fontSize: 30 * k, lineHeight: 1.5,
              color: NOTE.inkSoft}}>
              <span style={{width: 110 * k, flex: 'none', fontWeight: 700, letterSpacing: '0.04em', color: NOTE.note}}>{r.k}</span>
              <span style={{fontStyle: r.k === '저널' ? 'italic' : 'normal'}}><Numerals text={r.v} /></span>
            </div>
          </RiseLine>
        ))}
      </PaperNote>
      {data.credit ? <CornerCredit text={data.credit} onPaper opacity={tween(frame, 10, DUR.normal)} /> : null}
      <div style={{position: 'absolute', inset: 0, pointerEvents: 'none'}}>
        <PaperFiber id={`acg${id}`} opacity={0.08} />
      </div>
    </div>
  );
};

/** 증거 템플릿 — treatment 로 모양을 가른다(전면 전용: 파이프라인이 pip 는 자료 사진 경로로 보낸다) */
export const EvidenceCard: React.FC<TemplateProps> = ({id, data, frame, dur, fps, theme, box}) => {
  const W = box.w;
  const H = box.h;
  const k = sx(W);
  const assets = data.assets ?? [];
  const t = data.treatment ?? (assets.length ? 'hero' : 'archive_card');
  const seed = hashSeed(id);
  const out = tweenOut(frame, dur, LONG.out);
  const pIn = tween(frame, 0, LONG.plateIn, 'outQuint');
  if (t === 'collage') {
    return <CollageScene id={id} data={data} frame={frame} dur={dur} theme={theme} W={W} H={H} />;
  }
  if (t === 'doc_highlight' && assets[0]?.kind === 'document') {
    return (
      <div style={{position: 'absolute', inset: 0, opacity: out, overflow: 'hidden'}}>
        <PaperStage theme={theme} frame={frame} />
        <DocPage asset={assets[0]} lines={data.lines} title={data.title} frame={frame} fps={fps} dur={dur} theme={theme}
          W={W} H={H} seed={seed} />
        <CornerCredit text={data.credit || ''} onPaper opacity={tween(frame, 10, DUR.normal)} />
      </div>
    );
  }
  if (t === 'archive_card' || !assets.length) {
    return <div style={{position: 'absolute', inset: 0, opacity: out}}>
      <ArchiveCard data={data} frame={frame} dur={dur} W={W} H={H} theme={theme} seed={seed} id={id} /></div>;
  }
  if (t === 'full') {
    return (
      <div style={{position: 'absolute', inset: 0, opacity: out, overflow: 'hidden', background: '#0B0B0B'}}>
        <div style={{position: 'absolute', inset: 0, opacity: tween(frame, 0, DUR.normal),
          filter: data.quote ? GRADE_QUOTE : undefined}}>
          <AssetSequence assets={assets} win={{w: W, h: H}} frame={frame} dur={dur} bleed />
        </div>
        {data.quote ? <QuoteOverlay text={data.quote} frame={frame} W={W} H={H} /> : null}
        <div style={{position: 'absolute', inset: 0, background:
          'linear-gradient(180deg, rgba(0,0,0,0.35) 0%, rgba(0,0,0,0) 24%, rgba(0,0,0,0) 62%, rgba(0,0,0,0.5) 100%)'}} />
        {data.title && !data.quote ? (
          <div style={{position: 'absolute', left: 72 * k, top: 58 * k}}>
            <NameChip text={data.title} theme={theme} frame={frame} delay={6} size={40 * k} />
            {data.caption ? (
              <RiseLine frame={frame} delay={10}>
                <div style={{marginTop: 10, fontFamily: FONT.sans, fontWeight: 500, fontSize: 26 * k,
                  color: 'rgba(255,255,255,0.88)', textShadow: '0 2px 10px rgba(0,0,0,0.4)'}}><Numerals text={data.caption} /></div>
              </RiseLine>
            ) : null}
          </div>
        ) : null}
        <FilmLook frame={frame} id={id} strength={0.7} />
        <CornerCredit text={data.credit || ''} opacity={tween(frame, 10, DUR.normal)} />
      </div>
    );
  }
  // hero · browser_frame · doc_highlight · grid · compare_pair: 크림 종이 위 이미지 창 + 캡션 줄
  const win = {x: HERO.x * k, y: HERO.y * k, w: HERO.w * k, h: HERO.h * k};
  const first = assets[0];
  let inner: React.ReactNode;
  if (t === 'browser_frame' && first.kind === 'screen') {
    inner = <BrowserFrame asset={first} url={first.meta?.ref} win={win} frame={frame} dur={dur} fps={fps} />;
  } else if (t === 'doc_highlight' && first.kind === 'document') {
    inner = <DocHighlight asset={first} lines={data.lines} quote={data.archive?.quote || data.caption} win={win}
      frame={frame} fps={fps} dur={dur} theme={theme} />;
  } else if (t === 'grid' && assets.length >= 4) {
    inner = <ImageGrid assets={assets.slice(0, 9)} win={win} frame={frame} />;
  } else if (t === 'compare_pair' && assets.length >= 2) {
    inner = <ComparePair a={assets[0]} b={assets[1]} win={win} frame={frame} />;
  } else {
    inner = <AssetSequence assets={assets} win={win} frame={frame} dur={dur} />;
  }
  const framed = t === 'hero' || t === 'grid' || t === 'compare_pair';
  // 디자인 v3: 크림 종이 무대 위 — 사진 창은 종이 테두리 프린트(테두리 14px · 높이 2 그림자 · 시드 각도)
  const print = t === 'hero';
  return (
    <div style={{position: 'absolute', inset: 0, opacity: out}}>
      <PaperStage theme={theme} frame={frame} />
      <div style={{position: 'absolute', left: win.x, top: win.y, width: win.w, height: win.h,
        overflow: framed ? 'hidden' : 'visible', background: framed && print ? pressColors(theme).paperLight : undefined,
        opacity: pIn, translate: `0 ${interpolate(pIn, [0, 1], [18, 0])}px`,
        border: print ? `14px solid ${pressColors(theme).paperLight}` : undefined, boxSizing: 'border-box',
        rotate: print ? `${((seed % 7) - 3) * 0.12}deg` : undefined,
        boxShadow: print || t === 'doc_highlight' ? paperShadow(2) : undefined}}>
        {inner}
      </div>
      <CaptionRow x={win.x} y={win.y + win.h + 6 * k} w={win.w} label={data.title} caption={data.caption}
        credit={data.credit} frame={frame} theme={theme} />
    </div>
  );
};

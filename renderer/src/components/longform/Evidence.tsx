import React from 'react';
import {Img, OffthreadVideo, interpolate, staticFile} from 'remotion';
import {DUR, EASE, LONG, STAGGER, tween, tweenOut} from '../../design/motion';
import {FONT, NOTE, paperShadow} from '../../design/tokens';
import type {Theme} from '../../design/tokens';
import type {EvidenceAsset, GraphicData, NBox} from '../../lib/types';
import type {TemplateProps} from '../graphics/common';
import {hashSeed} from '../paper/Paper';
import {CornerCredit, FilmLook, Halftone, PaperFiber, PaperNote} from './Note';
import {Numerals, RiseLine, Rule} from './Stage';

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

/** 크림 종이 바탕(책상 위 한 장) — 망점 + 섬유 */
const PaperGround: React.FC<{id: string}> = ({id}) => (
  <div style={{position: 'absolute', inset: 0, background: NOTE.paper}}>
    <Halftone opacity={0.35} />
    <PaperFiber id={id} />
  </div>
);

/** 캡션 줄: 왼쪽 = 라벨(주장, Jua) + 캡션(사실, Pretendard + 숫자 Playfair), 오른쪽 = 출처(22px) */
const CaptionRow: React.FC<{x: number; y: number; w: number; label?: string; caption?: string; credit?: string;
  frame: number; theme: Theme}> = ({x, y, w, label, caption, credit, frame, theme}) => (
  <div style={{position: 'absolute', left: x, top: y, width: w, height: CAP_H, display: 'flex', alignItems: 'center',
    gap: 22}}>
    {label ? (
      <RiseLine frame={frame} delay={8}>
        <div style={{fontFamily: FONT.round, fontSize: 42, color: NOTE.ink, whiteSpace: 'nowrap',
          borderBottom: `4px solid ${theme.accent}`, paddingBottom: 2}}>{label}</div>
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

/** DocHighlight — 문서 전체 → 어두워지며 한 줄만 남고 밑줄(줄 좌표가 있을 때) → 오른쪽 종이 메모에 풀이 */
const DocHighlight: React.FC<{asset: EvidenceAsset; lines?: NBox[]; quote?: string; win: {w: number; h: number};
  frame: number; fps: number; theme: Theme}> = ({asset, lines = [], quote, win, frame, fps, theme}) => {
  const docW = quote ? win.w * 0.6 : win.w;
  const k = Math.min(docW / Math.max(1, asset.w), win.h / Math.max(1, asset.h));
  const w = asset.w * k;
  const h = asset.h * k;
  const ox = (docW - w) / 2;
  const oy = (win.h - h) / 2;
  const f0 = Math.round(1.2 * fps);
  const dim = lines.length ? tween(frame, f0, DUR.normal, 'outCubic') : 0;
  return (
    <div style={{position: 'absolute', inset: 0}}>
      <Img src={staticFile(asset.src)} style={{position: 'absolute', left: ox, top: oy, width: w, height: h,
        boxShadow: paperShadow(1), rotate: '-0.6deg'}} />
      <div style={{position: 'absolute', left: ox, top: oy, width: w, height: h, background: 'rgba(38,33,30,0.55)',
        opacity: dim}} />
      {lines.map(([x, y, lw, lh], i) => {
        const p = tween(frame, f0 + 4 + i * STAGGER.line, LONG.underline, 'outQuint');
        const L = ox + x * w;
        const T = oy + y * h;
        return (
          <React.Fragment key={i}>
            <div style={{position: 'absolute', left: L, top: T, width: lw * w, height: lh * h, overflow: 'hidden',
              opacity: dim}}>
              <Img src={staticFile(asset.src)} style={{position: 'absolute', left: ox - L, top: oy - T, width: w, height: h}} />
            </div>
            <div style={{position: 'absolute', left: L, top: T + lh * h + 2, width: lw * w * p, height: 5,
              background: theme.accent}} />
          </React.Fragment>
        );
      })}
      {quote ? (
        <div style={{position: 'absolute', left: docW + 48, top: win.h * 0.2, width: win.w - docW - 48,
          opacity: tween(frame, f0 + 10, DUR.slow), translate: `0 ${interpolate(tween(frame, f0 + 10, DUR.slow), [0, 1], [16, 0])}px`}}>
          <Rule frame={frame} delay={f0 + 8} color={theme.accent} thick={4} width={80} />
          <div style={{marginTop: 22, fontFamily: FONT.serif, fontWeight: 600, fontSize: 46, lineHeight: 1.35,
            color: NOTE.ink}}>{quote}</div>
        </div>
      ) : null}
    </div>
  );
};

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
    <div style={{position: 'absolute', inset: 0, borderRadius: 14, overflow: 'hidden', background: NOTE.paper,
      boxShadow: paperShadow(2)}}>
      <div style={{height: bar, background: NOTE.paperDeep, display: 'flex', alignItems: 'center', gap: 10,
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
            background: NOTE.paperDeep}}>
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
            opacity: p, translate: `0 ${interpolate(p, [0, 1], [18, 0])}px`, background: NOTE.paperDeep}}>
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
    <div style={{position: 'absolute', inset: 0, background: NOTE.paperDeep}}>
      <Halftone opacity={0.3} />
      <PaperNote x={x} y={y} w={w} h={h} frame={frame} dur={dur} from="right" theme={theme} seed={seed} pad={pad} id={`ac${id}`}>
        {photo ? (
          <div style={{position: 'relative', width: innerW, height: h * 0.56, overflow: 'hidden', background: NOTE.paperDeep}}>
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
  if (t === 'archive_card' || !assets.length) {
    return <div style={{position: 'absolute', inset: 0, opacity: out}}>
      <ArchiveCard data={data} frame={frame} dur={dur} W={W} H={H} theme={theme} seed={seed} id={id} /></div>;
  }
  if (t === 'full') {
    return (
      <div style={{position: 'absolute', inset: 0, opacity: out, overflow: 'hidden', background: '#0B0B0B'}}>
        <div style={{position: 'absolute', inset: 0, opacity: tween(frame, 0, DUR.normal)}}>
          <AssetSequence assets={assets} win={{w: W, h: H}} frame={frame} dur={dur} bleed />
        </div>
        <div style={{position: 'absolute', inset: 0, background:
          'linear-gradient(180deg, rgba(0,0,0,0.35) 0%, rgba(0,0,0,0) 24%, rgba(0,0,0,0) 62%, rgba(0,0,0,0.5) 100%)'}} />
        {data.title ? (
          <div style={{position: 'absolute', left: 72 * k, top: 58 * k}}>
            <RiseLine frame={frame} delay={6}>
              <div style={{fontFamily: FONT.round, fontSize: 46 * k, color: '#fff', textShadow: '0 2px 14px rgba(0,0,0,0.45)',
                borderBottom: `4px solid ${theme.accent}`}}>{data.title}</div>
            </RiseLine>
            {data.caption ? (
              <RiseLine frame={frame} delay={10}>
                <div style={{marginTop: 8, fontFamily: FONT.sans, fontWeight: 500, fontSize: 26 * k,
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
      frame={frame} fps={fps} theme={theme} />;
  } else if (t === 'grid' && assets.length >= 4) {
    inner = <ImageGrid assets={assets.slice(0, 9)} win={win} frame={frame} />;
  } else if (t === 'compare_pair' && assets.length >= 2) {
    inner = <ComparePair a={assets[0]} b={assets[1]} win={win} frame={frame} />;
  } else {
    inner = <AssetSequence assets={assets} win={win} frame={frame} dur={dur} />;
  }
  const framed = t === 'hero' || t === 'grid' || t === 'compare_pair';
  return (
    <div style={{position: 'absolute', inset: 0, opacity: out}}>
      <PaperGround id={`eg${id}`} />
      <div style={{position: 'absolute', left: win.x, top: win.y, width: win.w, height: win.h,
        overflow: framed ? 'hidden' : 'visible', background: framed && t === 'hero' ? NOTE.paperDeep : undefined,
        opacity: pIn, translate: `0 ${interpolate(pIn, [0, 1], [18, 0])}px`,
        boxShadow: t === 'hero' ? paperShadow(2) : undefined}}>
        {inner}
      </div>
      <CaptionRow x={win.x} y={win.y + win.h + 6 * k} w={win.w} label={data.title} caption={data.caption}
        credit={data.credit} frame={frame} theme={theme} />
    </div>
  );
};

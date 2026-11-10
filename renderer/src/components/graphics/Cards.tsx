import React from 'react';
import {Img, staticFile} from 'remotion';
import {enter, exit} from '../../lib/anim';
import {balanceLines, estWidth, fitBlock, fitSize} from '../../lib/fit';
import {overlayStyle, paperSettle, stampIn} from '../../design/motion';
import {FONT, MAT, SLOT_TYPE} from '../../design/tokens';
import type {TemplateProps} from './common';
import {Collage} from '../material/Collage';
import {CutoutStack} from '../material/Cutout';
import {Attach, Stamp} from '../material/Marks';
import {Sheet} from '../material/Sheet';
import {ChapterBadge, CenterWord, CornerCredit, DefinitionSlot, QuoteSlot, Super, TopicMemo, WordRise} from '../modern/Modern';
import {hashSeed} from '../paper/Paper';

// 디자인 v5.1 슬롯(docs/디자인_v5_토크쇼.md): 템플릿은 자기 자리에 정해진 모양으로만 그린다.

const TALL_WORD_Y = 1210 / 1920;     // 숏폼 얹힌 글자의 고정 띠(y 1120~1300) 가운데

/** 챕터 카드(split·창 안에서 쓰일 때) — 전면 챕터는 ModernChapter, 화자 위는 좌상단 배지 */
export const ChapterCard: React.FC<TemplateProps> = ({data, surface, box}) => {
  const {size, lines} = fitBlock(data.title || '', box.w * 0.9, box.h * 0.5, 96, 44, 1.16, 3, -0.02);
  return (
    <div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center'}}>
      <div style={{fontFamily: FONT.sans, fontWeight: 900, fontSize: 120, lineHeight: 1, letterSpacing: '-0.02em', color: MAT.forest, marginBottom: 20, fontVariantNumeric: 'tabular-nums'}}>{data.number || '01'}</div>
      {lines.map((l, i) => (
        <div key={i} style={{fontFamily: FONT.sans, fontWeight: 800, fontSize: size, lineHeight: 1.16, letterSpacing: '-0.02em',
          color: surface.fg}}>{l}</div>
      ))}
    </div>
  );
};

/** 핵심어: 화자 위에서는 가슴 높이의 흰 고딕, 전면에서는 책상 위에 찢어 낸 인쇄물 한 조각 */
export const KeywordCard: React.FC<TemplateProps> = ({data, frame, dur, surface, box, layout, id}) => {
  const title = (data.title || '').replace(/\*/g, '');
  const onHost = layout === 'overlay' || layout === 'pip';
  if (onHost) {
    return <CenterWord text={title} sub={data.subtitle} W={box.w} H={box.h} frame={frame} dur={dur} y={box.h > box.w ? TALL_WORD_Y : 0.66} />;
  }
  const size = fitSize(title, box.w * 0.8, 190, 64, -0.02);
  const w = Math.min(box.w, title.length * size * 0.96 + 260);
  const h = size * 2.05;
  const seed = hashSeed(id);
  const x = (box.w - w) / 2 - 30;
  const y = box.h * 0.34;
  return (
    <div style={{position: 'absolute', inset: 0}}>
      <Sheet x={x} y={y} w={w} h={h} tex="memo" seed={seed} m={paperSettle(frame, -1.4, 12, 18, 2.6)} torn={{left: true, right: true}} amp={18}>
        <div style={{position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: FONT.sans, fontWeight: 900, fontSize: size, lineHeight: 1, letterSpacing: '-0.02em', color: MAT.ink, whiteSpace: 'nowrap'}}><div><WordRise lines={[title]} frame={frame - 5} /></div></div>
        <Attach w={w} seed={seed} />
      </Sheet>
      {data.subtitle ? (
        <Sheet x={x + w * 0.1} y={y + h - 8} w={estWidth(data.subtitle, 58, 0) * 0.82 + 110} h={108} tex="kraft" seed={seed + 3} m={paperSettle(frame - 5, 1.6, 10)} torn={{right: true, bottom: true}} amp={9}>
          <div style={{position: 'absolute', left: 44, top: 0, height: 104, display: 'flex', alignItems: 'center', fontFamily: FONT.pen, fontSize: 58, lineHeight: 1, color: MAT.ink, whiteSpace: 'nowrap'}}>{data.subtitle}</div>
        </Sheet>
      ) : null}
    </div>
  );
};

/** 용어 정의: 좌하단 숲색 머리표 + 어둡게 흐린 본문 */
export const DefinitionCard: React.FC<TemplateProps> = ({data, frame, dur, box}) => (
  <DefinitionSlot title={data.title || ''} en={data.subtitle} body={data.body} frame={frame} dur={dur} box={box} />
);

/** 인용: 뒤를 흐리고 어둡게 + 큰 따옴표 + 명조 + 원전 */
export const QuoteCard: React.FC<TemplateProps> = ({data, frame, dur, box}) => (
  <QuoteSlot text={data.body || data.title || ''} who={[data.author, data.source].filter(Boolean).join(', ')} W={box.w} H={box.h} frame={frame} dur={dur} />
);

/** 괘선 인덱스 카드의 줄: 글줄이 있는 곳에만 rows 줄 — 큰 숫자 뒤를 지나면 숫자를 가른다 */
const Rules: React.FC<{top: number; gap: number; rows: number}> = ({top, gap, rows}) => (
  <div style={{position: 'absolute', left: 0, right: 0, top, height: rows * gap, backgroundImage: `repeating-linear-gradient(180deg, rgba(70,120,160,0) 0 ${gap - 1.5}px, rgba(70,120,160,0.26) ${gap - 1.5}px ${gap}px)`}} />
);

/** 숫자 뒤 단위 앞을 0.08em 띄운다 — 붙이면 마지막 숫자와 단위가 겹친다 */
const NumUnit: React.FC<{text: string}> = ({text}) => {
  const m = text.match(/^(.*\d)(\D+)$/);
  return m ? <>{m[1]}<span style={{marginLeft: '0.08em'}}>{m[2]}</span></> : <>{text}</>;
};

/** 숫자 태그: 인덱스 카드에 큰 숫자, 비교 대상(title_b · items_b[0])과 함께. 화자 위에서는 얼굴 반대편, 전면에서는 큰 숫자 + 겹친 카드 */
export const StatCard: React.FC<TemplateProps> = ({data, frame, dur, surface, box, layout, faceX = 0.5, id}) => {
  const onHost = layout === 'overlay' || layout === 'pip';
  const num = data.title || '';
  const seed = hashSeed(id);
  const body = data.body || '';
  if (onHost && box.h > box.w) return <CenterWord text={num} sub={body} W={box.w} H={box.h} frame={frame} dur={dur} y={TALL_WORD_Y} />;     // 숏폼: 카드를 얼굴 아래 칸에 넣을 수 없다
  if (onHost) {
    const cw = 590;
    const numSize = fitSize(num, cw - 110, 150, 72, -0.02);
    const lines = balanceLines(body, 36, cw - 110, 3, -0.015);
    const cmpH = data.title_b ? 106 : 0;
    const subH = data.subtitle ? 58 : 0;
    const bodyTop = 50 + numSize * 1.08 + 12;
    const ch = bodyTop + lines.length * 46 + cmpH + subH + 40;
    const right = faceX <= 0.5;
    const rest = right ? 1.5 : -1.5;
    const st = overlayStyle(Math.max(frame, 20), dur);
    return (
      <div style={{position: 'absolute', [right ? 'right' : 'left']: 66, top: box.h * 0.13, width: cw, height: ch, opacity: st.opacity, filter: st.filter}}>
        <Sheet w={cw} h={ch} tex="memo" seed={seed} m={paperSettle(frame, rest)} style={{wordBreak: 'keep-all'}}>
          <div style={{position: 'absolute', left: 0, right: 0, top: 34, height: 3, background: MAT.orange, opacity: 0.75}} />
          <Rules top={bodyTop + 41 - 46 + 0.75} gap={46} rows={lines.length} />{/* 46px 글줄의 기준선 밑 */}
          <div style={{position: 'absolute', left: 54, top: 50, fontFamily: FONT.sans, fontWeight: 900, fontSize: numSize, lineHeight: 1.08, letterSpacing: '-0.02em', color: MAT.forest, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap'}}><NumUnit text={num} /></div>
          <div style={{position: 'absolute', left: 54, right: 40, top: bodyTop}}>
            {lines.map((l, i) => <div key={i} style={{fontFamily: FONT.sans, fontWeight: 600, fontSize: 36, lineHeight: '46px', letterSpacing: '-0.02em', color: MAT.ink, whiteSpace: 'nowrap'}}>{l}</div>)}
            {data.title_b ? (
              <div style={{display: 'flex', alignItems: 'baseline', gap: 16, marginTop: 20, whiteSpace: 'nowrap'}}>
                <span style={{fontFamily: FONT.sans, fontWeight: 900, fontSize: 64, lineHeight: 1, letterSpacing: '-0.02em', color: MAT.orange, fontVariantNumeric: 'tabular-nums'}}><NumUnit text={data.title_b} /></span>
                {data.items_b?.[0] ? <span style={{fontFamily: FONT.sans, fontWeight: 600, fontSize: 38, color: MAT.ink}}>{data.items_b[0]}</span> : null}
              </div>
            ) : null}
            {data.subtitle ? <div style={{marginTop: 16, fontFamily: FONT.sans, fontWeight: 500, fontSize: SLOT_TYPE.statSub, color: MAT.inkSoft}}>{data.subtitle}</div> : null}
          </div>
          <Attach w={cw} seed={seed} />
        </Sheet>
      </div>
    );
  }
  const numSize = fitSize(num, data.title_b ? Math.min(906, box.w - 730) : box.w * 0.8, 400, 120, -0.02);     // 비교 카드가 옆에 있으면: estWidth 는 숫자 900 을 약 8% 작게 잰다 — 실제 폭 980 안, 카드와 56px 이상
  const lines = balanceLines(body, 64, data.title_b ? box.w - 700 : box.w * 0.78, 3, -0.025);
  return (
    <div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center', paddingBottom: 30}}>
      <div style={{fontFamily: FONT.sans, fontWeight: 900, fontSize: numSize, lineHeight: 1, letterSpacing: '-0.02em', color: MAT.forest, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap', ...overlayStyle(frame)}}><NumUnit text={num} /></div>
      <div style={{marginTop: 34, ...overlayStyle(frame - 6)}}>
        {lines.map((l, i) => <div key={i} style={{fontFamily: FONT.sans, fontWeight: 700, fontSize: 64, lineHeight: 1.26, letterSpacing: '-0.02em', color: surface.fg, whiteSpace: 'nowrap'}}>{l}</div>)}
        {data.subtitle ? <div style={{marginTop: 18, fontFamily: FONT.sans, fontWeight: 500, fontSize: 36, color: surface.dim}}>{data.subtitle}</div> : null}
      </div>
      {data.title_b ? (
        <Sheet x={box.w - 610} y={box.h * 0.17} w={590} h={410} tex="memo" seed={seed} m={paperSettle(frame - 10, 2.2)} on="board">
          <div style={{position: 'absolute', left: 0, right: 0, top: 36, height: 3, background: MAT.orange, opacity: 0.75}} />
          <Rules top={83} gap={50} rows={1} />
          <div style={{position: 'absolute', left: 56, top: 74, fontFamily: FONT.pen, fontSize: 54, lineHeight: 1, color: MAT.graphite}}>비교하면</div>
          <div style={{position: 'absolute', left: 54, top: 150, fontFamily: FONT.sans, fontWeight: 900, fontSize: 124, lineHeight: 1.05, letterSpacing: '-0.02em', color: MAT.orange, fontVariantNumeric: 'tabular-nums'}}><NumUnit text={data.title_b} /></div>
          {data.items_b?.[0] ? <Rules top={323} gap={50} rows={1} /> : null}
          {data.items_b?.[0] ? <div style={{position: 'absolute', left: 56, bottom: 44, fontFamily: FONT.sans, fontWeight: 700, fontSize: 40, letterSpacing: '-0.02em', color: MAT.ink, whiteSpace: 'nowrap'}}>{data.items_b[0]}</div> : null}
          <Attach w={590} seed={seed + 1} />
        </Sheet>
      ) : null}
    </div>
  );
};

/** 도장: 자료 위 대각선, 잉크가 번진 도장(영상당 3개 이하). 책상 위 세로 인쇄물의 가운데 쪽에 찍혀 종이 밖으로 나가지 않는다. title = 글자, subtitle = 아랫줄 */
export const StampCard: React.FC<TemplateProps> = ({data, frame, box, id}) => (
  <Stamp text={data.title || ''} sub={data.subtitle} size={92} m={stampIn(frame)} seed={hashSeed(id) % 97} onPaper style={{position: 'absolute', left: box.w * 0.54, top: box.h * 0.3, translate: '-50% -50%'}} />
);

/** 오림 스택: data.cutouts 를 오른쪽 위에서 아래로 하나씩(얼굴이 오른쪽이면 왼쪽으로) */
export const CutoutStackCard: React.FC<TemplateProps> = ({data, frame, dur, fps, box, faceX = 0.5}) => (
  <>
    <CutoutStack items={data.cutouts ?? []} frame={frame} dur={dur} fps={fps} box={box} side={faceX > 0.62 ? 'left' : 'right'} />
    <CornerCredit text={data.credit || ''} tall={box.h > box.w} />
  </>
);

/** 콜라주: data.cutouts 2~5장, data.disc, data.name */
export const CollageCard: React.FC<TemplateProps> = ({data, frame, fps, box, id}) => (
  <>
    <Collage items={data.cutouts ?? []} W={box.w} H={box.h} frame={frame} fps={fps} seed={hashSeed(id)} disc={data.disc} name={data.name} sub={data.name_sub} />
    <CornerCredit text={data.credit || ''} tall={box.h > box.w} />
  </>
);

/** 컷 사이 0.7~1.5초: 낱말에 맞춘 시각은 쓰되 너무 붙으면 민다. 시각이 없으면 고르게 */
const montageCuts = (at: (number | undefined)[], dur: number, fps: number): number[] => {
  const n = at.length;
  const even = Math.min(1.5 * fps, Math.max(0.7 * fps, dur / n));
  const out: number[] = [];
  at.forEach((a, i) => {
    const t = i === 0 ? 0 : Math.round(a !== undefined ? a * fps : out[i - 1] + even);
    out.push(i ? Math.max(t, out[i - 1] + Math.round(0.7 * fps)) : t);
  });
  return out;
};

/** 핵심어 몽타주: 큰 흰 고딕 낱말은 가운데 그대로, 뒤의 사진만 말에 맞춰 하드 컷으로 바뀐다 */
export const KeywordMontageCard: React.FC<TemplateProps> = ({data, frame, dur, fps, box}) => {
  const items = (data.cutouts ?? []).slice(0, 5);
  if (!items.length) return null;
  const cuts = montageCuts(items.map((c) => c.at), dur, fps);
  const i = cuts.reduce((acc, t, k) => (frame >= t ? k : acc), 0);
  const it = items[i];
  return (
    <div style={{position: 'absolute', inset: 0, overflow: 'hidden', background: '#0B0B0B'}}>
      <Img src={staticFile(it.image)} style={{position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', objectPosition: it.focus || '50% 38%'}} />{/* 어둡기·흐림은 파일에 구웠다(cutout.montage_still) */}
      <CenterWord text={(data.title || '').replace(/\*/g, '')} sub={data.subtitle} W={box.w} H={box.h} frame={frame} dur={dur} y={box.h > box.w ? 0.46 : 0.47} scale={2.05} veil={false} />
      <CornerCredit text={it.credit || data.credit || ''} tall={box.h > box.w} />
    </div>
  );
};

// ---------------------------------------------------------------------------
// 오프닝 타이틀 — 리포트 표지(빨간 바탕 + 짙은 거대 타이포 + 가장자리 작은 글자).
// 화자 영상은 LongForm 이 중앙 작은 프레임으로 이 위에 얹는다.
// ---------------------------------------------------------------------------
export const TitleCard: React.FC<TemplateProps> = ({data, frame, dur, surface, box, brand, episode}) => {
  const title = data.title || episode.title;
  const {size, lines} = fitBlock(title, box.w * 0.9, box.h * 0.8, 230, 110, 0.98, 3, -0.02);
  const out = exit(frame, dur, 10);
  const edgeStyle: React.CSSProperties = {position: 'absolute', fontFamily: FONT.sans, fontWeight: 600, fontSize: 22,
    color: surface.fg, textAlign: 'center', lineHeight: 1.2, opacity: enter(frame, 8, 14)};
  const year = brand.year || '2026';
  return (
    <div style={{position: 'absolute', inset: 0, opacity: out}}>
      <div style={{...edgeStyle, top: 30, left: 0, right: 0, fontWeight: 500, fontSize: 18}}>
        {brand.name} {episode.series ? `· ${episode.series}` : ''}
      </div>
      <div style={{...edgeStyle, bottom: 30, left: 0, right: 0, fontWeight: 500, fontSize: 18}}>
        {episode.subtitle || 'design theory, explained'}
      </div>
      <div style={{...edgeStyle, left: 40, top: box.h * 0.46, width: 220}}>{episode.number ? `EP. ${episode.number}` : brand.shortName}</div>
      <div style={{...edgeStyle, right: 40, top: box.h * 0.46, width: 220}}>{brand.presenter}</div>
      <div style={{...edgeStyle, left: 40, top: box.h * 0.3, width: 220, fontFamily: FONT.latin, fontSize: 26}}>{year.slice(0, 2)}</div>
      <div style={{...edgeStyle, right: 40, top: box.h * 0.3, width: 220, fontFamily: FONT.latin, fontSize: 26}}>{year.slice(0, 2)}</div>
      <div style={{...edgeStyle, left: 40, top: box.h * 0.66, width: 220, fontFamily: FONT.latin, fontSize: 26}}>{year.slice(2)}</div>
      <div style={{...edgeStyle, right: 40, top: box.h * 0.66, width: 220, fontFamily: FONT.latin, fontSize: 26}}>{year.slice(2)}</div>
      <div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center',
        justifyContent: 'center'}}>
        <div style={{fontFamily: FONT.display, fontWeight: 900, fontSize: size, lineHeight: 0.98, letterSpacing: '-0.02em', color: surface.fg, textAlign: 'center'}}><WordRise lines={lines} frame={frame} /></div>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// 로어서드 — 좌하단 슈퍼(왼쪽 세로선 + 이름 + 소속). data.title 이 있으면 우상단 '오늘의 주제' 메모, slot badge 면 챕터 배지
// ---------------------------------------------------------------------------
export const LowerThird: React.FC<TemplateProps> = ({frame, dur, brand, theme, data, box}) => {
  const topic = String(data?.title || '').trim();
  if (data?.slot === 'badge') return <ChapterBadge title={topic} frame={frame} dur={dur} />;
  if (data?.slot === 'super') return <Super name={topic} sub={data.subtitle} theme={theme} box={box} frame={frame} dur={dur} />;
  return (
    <>
      {topic ? <TopicMemo title={topic} frame={frame} dur={dur} /> : null}
      <Super name={brand.presenter} sub={brand.presenterTitle} theme={theme} box={box} frame={frame} dur={dur} />
    </>
  );
};

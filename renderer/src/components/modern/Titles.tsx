import React from 'react';
import {collageStep, paperSettle, tween} from '../../design/motion';
import {FONT, MAT} from '../../design/tokens';
import type {Theme} from '../../design/tokens';
import {balanceLines, estWidth, fitBlock} from '../../lib/fit';
import type {Brand, Episode, GraphicData} from '../../lib/types';
import {PaperRip} from '../fx/Transitions';
import {Attach, PencilStroke, ringPts, Tape} from '../material/Marks';
import {Sheet} from '../material/Sheet';
import type {Edges} from '../material/Sheet';
import {Collage, NEWS_COPY} from '../material/Collage';
import {CutoutFrame} from '../material/Cutout';
import {GrainLayer, TexBackdrop, texFill, useMaterials} from '../material/Texture';
import type {TexName} from '../material/Texture';
import {hashSeed, seeded} from '../paper/Paper';
import {GLYPH_K} from '../graphics/Lists';
import {CornerCredit, WordRise} from './Modern';

/** 디자인 v5.1 길잡이: 아이덴트(스톱모션 콜라주) · 챕터 카드(종이 콜라주) · 엔드카드 — 건축 저널을 오려 붙인 책상 */

/** 8fps 로 놓이는 종이 조각: 첫 칸은 어긋나게, 둘째 칸에서 거의 제자리, 그다음부터는 칸마다 아주 조금 흔들린다 */
const Scrap: React.FC<{step: number; at: number; seed: number; x: number; y: number; w: number; h: number; tex: TexName; rot: number; torn?: Edges; level?: number; amp?: number;
  children?: React.ReactNode}> = ({step, at, seed, x, y, w, h, tex, rot, torn, level = 2, amp, children}) => {
  if (step < at) return null;
  const k = step - at;
  const r = seeded(seed + 0.1);
  const dx = (r() - 0.5) * 90;
  const dy = (r() - 0.5) * 60;
  const dr = (r() - 0.5) * 8;
  const land = k === 0 ? 1 : k === 1 ? 0.28 : 0;
  const b = seeded(seed * 3 + (step % 3) + 0.4);
  const j = k >= 2 ? [(b() - 0.5) * 1.8, (b() - 0.5) * 1.8, (b() - 0.5) * 0.3] : [0, 0, 0];
  return <Sheet x={x + dx * land + j[0]} y={y + dy * land + j[1]} w={w} h={h} tex={tex} seed={seed} rotate={rot + dr * land + j[2]} liftLevel={k === 0 ? 3 : level} torn={torn} amp={amp}>{children}</Sheet>;
};

/** 아이덴트: 책상 위로 신문·도면·모눈·크라프트 조각이 8fps 로 놓이고, 숲색 종이에 이번 회 제목(2~4초). 앞뒤는 종이 찢기 전환 */
export const ModernTitle: React.FC<{data: GraphicData; theme: Theme; W: number; H: number; brand: Brand; episode: Episode; frame?: number; dur?: number; fps?: number}> = ({data, W, H, brand, episode,
  frame = 40, dur, fps = 30}) => {
  useMaterials();
  const k = W / 1920;
  const step = frame < 8 ? -1 : Math.floor(collageStep(frame - 8, fps));     // 찢기 전환이 지나간 뒤에 놓이기 시작한다 — 전환 선에 조각 모서리가 걸리면 쐐기처럼 보인다
  const title = (data.title || episode.title).replace(/\*/g, '');
  const {size} = fitBlock(title, 1090, 396, 172, 72, 1.14, 2, -0.02);
  const lines = balanceLines(title, size, 1090, 2, -0.02);
  const sheetW = Math.min(1300, Math.max(860, Math.max(...lines.map((l) => estWidth(l, size, -0.02))) + 230));
  const issue = [episode.number ? `EP.${episode.number}` : '', episode.series].filter(Boolean).join(' · ');   // 제호는 신문 조각에만
  const settled = 8 + Math.ceil((5 * fps) / 8);     // 숲색 종이(다섯째 칸)가 거의 제자리에 온 뒤 제목이 오른다
  // 그 영상의 실제 사람·건물을 오린 조각이 있으면 그것이 아이덴트다 — 없을 때만 빈 신문·도면 조각으로
  const scene = (data.cutouts?.length ?? 0) >= 2 ? <Collage items={data.cutouts ?? []} W={W} H={H} frame={frame - 6} fps={fps} seed={hashSeed(title)} disc={data.disc} name={title} sub={issue} from={0} labelW={0.66} /> : (
    <div style={{position: 'absolute', left: 0, top: (H - 1080 * k) / 2, width: 1920, height: 1080, scale: `${k}`, transformOrigin: '0 0', overflow: 'hidden', ...texFill('desk')}}>
      <GrainLayer opacity={0.1} />
      <Scrap step={step} at={0} seed={11} x={840} y={-60} w={1160} h={720} tex="blueprint" rot={-2.2} torn={{left: true, bottom: true}} amp={16} />
      <Scrap step={step} at={1} seed={23} x={-50} y={-50} w={960} h={920} tex="newsprint" rot={1.5} torn={{right: true, bottom: true}} amp={15}>
        <div style={{position: 'absolute', left: 104, top: 96, width: 720, color: '#23211C'}}>
          <div style={{fontFamily: FONT.quote, fontWeight: 700, fontSize: 66, lineHeight: 1.05, letterSpacing: '-0.02em', whiteSpace: 'nowrap'}}>{brand.name}</div>
          <div style={{height: 3, background: '#23211C', margin: '16px 0 4px'}} />
          <div style={{height: 1, background: '#23211C', marginBottom: 18}} />
          <div style={{columnCount: 3, columnGap: 22, fontFamily: FONT.quote, fontSize: 17, lineHeight: 1.62, textAlign: 'justify', wordBreak: 'break-all', height: 620, overflow: 'hidden', color: 'rgba(35,33,28,0.86)'}}>{NEWS_COPY.repeat(5)}</div>
        </div>
      </Scrap>
      <Scrap step={step} at={2} seed={37} x={1180} y={570} w={820} h={570} tex="graph" rot={3} torn={{left: true, top: true}} amp={13}>
        {episode.subtitle ? (
          <>
            <svg width={820} height={570} style={{position: 'absolute', inset: 0}}>
              <PencilStroke pts={ringPts(505, 250, 214, 128)} seed={3} width={4} color={MAT.orange} />
            </svg>
            <div style={{position: 'absolute', left: 245, width: 520, top: 218, textAlign: 'center', fontFamily: FONT.pen, fontSize: 60, lineHeight: 1, color: MAT.graphite, whiteSpace: 'nowrap', rotate: '-3deg'}}>{episode.subtitle}</div>
          </>
        ) : null}
      </Scrap>
      <Scrap step={step} at={3} seed={49} x={-40} y={800} w={1320} h={320} tex="kraft" rot={-1.8} torn={{top: true, right: true}} amp={15}>
        {brand.presenter ? <div style={{position: 'absolute', left: 104, top: 96, fontFamily: FONT.pen, fontSize: 92, lineHeight: 1, color: '#3A2C1A', whiteSpace: 'nowrap'}}>{brand.presenter}</div> : null}
      </Scrap>
      <Scrap step={step} at={4} seed={61} x={190} y={232} w={sheetW} h={622} tex="forest" rot={-1.2} torn={{right: true, bottom: true}} amp={15}>
        {issue ? <div style={{position: 'absolute', left: 78, top: 58, fontFamily: FONT.sans, fontWeight: 600, fontSize: 38, lineHeight: 1, color: MAT.mint, whiteSpace: 'nowrap'}}>{issue}</div> : null}
        <div style={{position: 'absolute', left: 78, right: 70, bottom: 60, fontFamily: FONT.sans, fontWeight: 900, fontSize: size, lineHeight: 1.14, letterSpacing: '-0.02em', color: '#FFFFFF'}}>
          <WordRise lines={lines} frame={frame - settled} />
        </div>
        {step >= 5 ? <Tape x={-120} y={44} w={180} h={50} rotate={-38} seed={3} onDark /> : null}
      </Scrap>
    </div>
  );
  // 출처도 찢긴 선 안쪽 — 전환 중 화자 위에 뜨지 않게
  return <PaperRip frame={frame} dur={dur ?? Math.round(3.4 * fps)} W={W} H={H}>{scene}<CornerCredit text={data.credit || ''} tall={H > W} /></PaperRip>;
};

/** 챕터 카드: 양피지 위 크라프트 판에 큰 번호와 그 챕터의 실제 자료 조각(data.scraps — 없으면 조각도 없다, 내용 없는 장식 금지), 옆에 왼쪽 정렬 큰 제목(2.2~3초, 목차 없음) */
export const ModernChapter: React.FC<{data: GraphicData; theme: Theme; W: number; H: number; frame?: number}> = ({data, W, H, frame = 30}) => {
  useMaterials();
  const k = W / 1920;
  const title = (data.title || '').replace(/\*/g, '');
  const scraps = (data.scraps ?? []).slice(0, 2);
  const has = scraps.length > 0;
  const body = has ? 1040 : 760;
  const room = has ? 800 : 1040;
  const {size} = fitBlock(title, room, 480, 124, 66, 1.16, 3, -0.02);
  const lines = balanceLines(title, size, room, 3, -0.02);
  const num = (data.number || '01').padStart(2, '0');
  const seed = parseInt(num, 10) || 1;
  const m1 = paperSettle(frame, 1.3, 12);
  const line = Math.max(...lines.map((l) => estWidth(l, size, -0.02)));
  const under = tween(frame, 10, 12, 'enter');
  const place = [{x: 90, y: 60, w: 600, h: 440, rot: -2.2}, {x: 500, y: 300, w: 440, h: 330, rot: 2.8}];
  if ((data.cutouts?.length ?? 0) >= 2) {
    const size2 = fitBlock(title, 620, 480, 124, 66, 1.16, 3, -0.02).size;
    const lines2 = balanceLines(title, size2, 620, 3, -0.02);
    return (
      <div style={{position: 'absolute', left: 0, top: (H - 1080 * k) / 2, width: 1920, height: 1080, scale: `${k}`, transformOrigin: '0 0', overflow: 'hidden'}}>
        <Collage items={data.cutouts ?? []} W={1920} H={1080} narrow={1220} frame={frame} fps={30} seed={seed} disc={data.disc} from={0} />
        <Sheet x={1140} y={-60} w={860} h={1210} tex="memo" seed={seed + 5} m={paperSettle(frame - 10, 0.9, 11)} torn={{left: true}} amp={22} on="board" style={{zIndex: 10}}>
          <div style={{position: 'absolute', left: 104, top: 170, fontFamily: FONT.sans, fontWeight: 900, fontSize: 210, lineHeight: 0.9, letterSpacing: '-0.02em', color: MAT.forest, fontVariantNumeric: 'tabular-nums'}}>{num}</div>
          <div style={{position: 'absolute', left: 104, top: 430, fontFamily: FONT.sans, fontWeight: 900, fontSize: size2, lineHeight: 1.16, letterSpacing: '-0.02em', color: MAT.ink}}>
            <WordRise lines={lines2} frame={frame - 15} />
          </div>
        </Sheet>
      </div>
    );
  }
  return (
    <div style={{position: 'absolute', left: 0, top: (H - 1080 * k) / 2, width: 1920, height: 1080, scale: `${k}`, transformOrigin: '0 0', overflow: 'hidden'}}>
      <TexBackdrop name="parchment" seed={seed} />
      <GrainLayer opacity={0.06} />
      <Sheet x={-70} y={-60} w={has ? 1060 : 720} h={1210} tex="kraft" seed={seed + 3} m={m1} torn={{right: true}} amp={20} on="board">
        <div style={{position: 'absolute', left: 118, top: has ? 700 : 136, fontFamily: FONT.sans, fontWeight: 900, fontSize: has ? 300 : 430, lineHeight: 0.9, letterSpacing: '-0.02em', color: MAT.forest, fontVariantNumeric: 'tabular-nums', mixBlendMode: 'multiply'}}>{num}</div>
      </Sheet>
      {scraps.map((s, i) => {
        const p = place[i];
        const a = s.w && s.h ? s.w / s.h : 1.35;
        const w = Math.min(p.w, p.h * a);
        const h = w / a;
        const m = paperSettle(frame - 3 - i * 3, p.rot, 11);
        return (
          <div key={s.image} style={{position: 'absolute', left: p.x, top: p.y, opacity: m.opacity, translate: `0 ${m.y}px`, scale: `${m.scale}`}}>
            <CutoutFrame src={s.image} w={w} h={h} seed={seed + i * 7} rotate={m.rotate} level={m.elev} />
            {i === 0 ? <Attach w={w} seed={seed + 11} /> : null}
          </div>
        );
      })}
      <div style={{position: 'absolute', left: body, top: 330, fontFamily: FONT.sans, fontWeight: 900, fontSize: size, lineHeight: 1.16, letterSpacing: '-0.02em', color: MAT.ink}}>
        <WordRise lines={lines} frame={frame - 6} />
        <svg width={line + 40} height={34} style={{position: 'absolute', left: -6, top: lines.length * size * 1.16 + 8, overflow: 'visible'}}>
          <PencilStroke pts={[[0, 18], [line * 0.44, 12], [line * GLYPH_K, 20]]} p={under} width={9} color={MAT.orange} seed={seed} wobble={1.2} />
        </svg>
      </div>
    </div>
  );
};

/** 엔드카드: 책상 위 메모 한 장 + 유튜브 최종 화면 요소가 놓일 자리(오려 붙인 액자 — 요소가 곧게 앉도록 기울이지 않는다) */
export const ModernEndCard: React.FC<{brand: Brand; W: number; H: number}> = ({brand, W, H}) => {
  useMaterials();
  const k = W / 1920;
  const slot = (x: number, y: number, w: number, h: number, label: string) => (
    <div style={{position: 'absolute', left: x, top: y, width: w, height: h, background: 'rgba(14,14,13,0.82)', border: `12px solid ${MAT.memo}`, boxSizing: 'border-box',
      boxShadow: '2px 3px 4px rgba(0,0,0,0.5), 10px 16px 30px rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: FONT.sans, fontWeight: 500, fontSize: 30, color: 'rgba(244,243,238,0.5)'}}>
      {label}
    </div>
  );
  return (
    <div style={{position: 'absolute', left: 0, top: (H - 1080 * k) / 2, width: 1920, height: 1080, scale: `${k}`, transformOrigin: '0 0', overflow: 'hidden', ...texFill('desk')}}>
      <GrainLayer opacity={0.1} />
      <Sheet x={110} y={170} w={760} h={640} tex="memo" seed={5} rotate={-1.5} liftLevel={2.6} torn={{bottom: true}} amp={15}>
        <div style={{position: 'absolute', left: 70, top: 76, fontFamily: FONT.quote, fontWeight: 700, fontSize: 42, letterSpacing: '-0.02em', color: MAT.forest, whiteSpace: 'nowrap'}}>{brand.name}</div>
        <div style={{position: 'absolute', left: 70, top: 170, fontFamily: FONT.sans, fontWeight: 900, fontSize: 104, lineHeight: 1.16, letterSpacing: '-0.02em', color: MAT.ink}}>
          <div>다음 이야기에서</div>
          <div>만나요</div>
        </div>
        <div style={{position: 'absolute', left: 74, bottom: 86, fontFamily: FONT.pen, fontSize: 60, lineHeight: 1, color: MAT.graphite, rotate: '-1.5deg'}}>구독해 두면 놓치지 않아요</div>
        <Attach w={760} seed={4} always tw={210} th={52} />
      </Sheet>
      {slot(1010, 140, 790, 444, '다음 영상')}
      {slot(1010, 640, 380, 280, '구독')}
      {slot(1420, 640, 380, 280, '재생목록')}
    </div>
  );
};

import React from 'react';
import {interpolate} from 'remotion';
import {EASE_OUT, enter, exit} from '../../lib/anim';
import {estWidth, fitBlock, fitSize} from '../../lib/fit';
import {FONT} from '../../design/tokens';
import {useFontForText} from '../../design/fonts';
import {DrawRule, MaskLine, ParenLabel} from '../layout/Editorial';
import type {TemplateProps} from './common';

// ---------------------------------------------------------------------------
// 챕터 카드 — Ink 표면. 거대한 번호(Anton) + 챕터 제목 + 주장(명조 기울임) + 목차(전체 챕터, 지금 챕터 강조).
// 롱폼 무대의 오리엔테이션 장치: 시청자가 '지금 어디쯤, 무슨 주장인지'를 챕터마다 다시 잡는다.
// data.items = 전체 챕터 제목, data.highlight = 지금 챕터 인덱스(studio/render/props.py chapter_maps).
// ---------------------------------------------------------------------------
export const ChapterCard: React.FC<TemplateProps> = ({data, frame, surface, box, theme}) => {
  const num = data.number || '01';
  const title = data.title || '';
  const map = (data.items || []).slice(0, 8);
  const cur = typeof data.highlight === 'number' ? data.highlight : -1;
  const {size, lines} = fitBlock(title, box.w * 0.52, box.h * (map.length ? 0.4 : 0.55), 124, 60, 1.08, 3, -0.04);
  const numSize = Math.min(box.h * 0.78, 520);
  const mapSize = 24;
  return (
    <div style={{position: 'absolute', inset: 0}}>
      <div
        style={{
          position: 'absolute',
          left: -numSize * 0.04,
          bottom: -numSize * 0.12,
          fontFamily: FONT.latin,
          fontSize: numSize,
          lineHeight: 1,
          color: surface.accent,
          translate: `0 ${interpolate(enter(frame, 0, 20), [0, 1], [18, 0])}%`,
          opacity: enter(frame, 0, 10),
        }}
      >
        {num}
      </div>
      <div style={{position: 'absolute', right: 0, top: box.h * 0.08, width: box.w * 0.55}}>
        <ParenLabel text={`chapter ${num}`} surface={surface} frame={frame} delay={4} size={24} />
        <div style={{height: 24}} />
        <DrawRule frame={frame} delay={6} color={surface.rule} />
        <div style={{height: 32}} />
        {lines.map((l, i) => (
          <MaskLine key={i} frame={frame} delay={8 + i * 4}>
            <div style={{fontFamily: FONT.heavy, fontWeight: 400, fontSize: size, lineHeight: 1.1,
              letterSpacing: '-0.01em', color: surface.fg}}>{l}</div>
          </MaskLine>
        ))}
        {data.subtitle ? (
          <MaskLine frame={frame} delay={16}>
            <div style={{marginTop: 26, fontFamily: FONT.serif, fontStyle: 'italic', fontWeight: 500, fontSize: 34,
              lineHeight: 1.4, color: 'rgba(255,255,255,0.78)', letterSpacing: '-0.01em'}}>
              {data.subtitle}
            </div>
          </MaskLine>
        ) : null}
        {map.length > 1 ? (
          <div style={{marginTop: 44, display: 'flex', flexDirection: 'column', gap: 10}}>
            {map.map((m, i) => {
              const on = i === cur;
              const p = enter(frame, 20 + i * 3, 12);
              return (
                <div key={i} style={{display: 'flex', alignItems: 'center', gap: 14, opacity: p * (on ? 1 : 0.42),
                  translate: `${interpolate(p, [0, 1], [12, 0])}px 0`}}>
                  <span style={{width: 8, height: 8, borderRadius: 4, background: on ? theme.accent : surface.dim,
                    flexShrink: 0}} />
                  <span style={{fontFamily: FONT.latin, fontSize: mapSize * 0.95, color: on ? theme.accentLight : surface.dim,
                    width: mapSize * 1.5, letterSpacing: '0.02em'}}>{String(i + 1).padStart(2, '0')}</span>
                  <span style={{fontFamily: FONT.sans, fontWeight: on ? 700 : 500, fontSize: mapSize,
                    color: surface.fg, letterSpacing: '-0.01em', whiteSpace: 'nowrap', overflow: 'hidden',
                    textOverflow: 'ellipsis'}}>{m}</span>
                </div>
              );
            })}
          </div>
        ) : null}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// 키워드 슬램 — 리포트 p.8 "NOSTALGIA IS GOLD" 레이아웃.
// ---------------------------------------------------------------------------
export const KeywordCard: React.FC<TemplateProps> = ({data, frame, dur, surface, box, brand, layout}) => {
  const title = data.title || '';
  const onBoard = surface.name === 'board';
  const maxSize = onBoard ? 150 : 250;
  const size = fitSize(title, box.w * (onBoard ? 0.92 : 0.94), maxSize, 60, -0.045);
  const p = enter(frame, 0, 16);
  const out = exit(frame, dur, 10);
  const year = brand.year || '2026';
  const small = data.subtitle || '';
  const edge = (txt: string, side: 'left' | 'right', top: number) => (
    <div style={{position: 'absolute', [side]: 0, top, fontFamily: FONT.sans, fontSize: 20, fontWeight: 500,
      color: surface.dim, opacity: enter(frame, 6, 12)}}>{txt}</div>
  );
  return (
    <div style={{position: 'absolute', inset: 0, opacity: out}}>
      {!onBoard && layout !== 'split' ? (
        <>
          {edge(year.slice(0, 2), 'left', box.h * 0.36)}
          {edge(year.slice(2), 'right', box.h * 0.36)}
          {small ? (
            <>
              <div style={{position: 'absolute', left: box.w * 0.12, top: box.h * 0.33, fontFamily: FONT.sans,
                fontSize: 30, fontWeight: 500, color: surface.fg, opacity: enter(frame, 8, 12), maxWidth: box.w * 0.34}}>
                {small}
              </div>
              <div style={{position: 'absolute', right: box.w * 0.12, top: box.h * 0.33, fontFamily: FONT.sans,
                fontSize: 30, fontWeight: 500, color: surface.fg, opacity: enter(frame, 10, 12), maxWidth: box.w * 0.34,
                textAlign: 'right'}}>
                {small}
              </div>
            </>
          ) : null}
        </>
      ) : null}
      <div
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          top: onBoard ? box.h * 0.3 : box.h * 0.46,
          display: 'flex',
          flexDirection: 'column',
          alignItems: onBoard ? 'flex-start' : 'center',
        }}
      >
        <div style={{overflow: 'hidden'}}>
          <div
            style={{
              fontFamily: FONT.heavy,
              fontWeight: 400,
              fontSize: size,
              lineHeight: 1.04,
              letterSpacing: '-0.01em',
              color: surface.name === 'signal' ? surface.fg : surface.name === 'overlay' ? '#fff' : surface.fg,
              translate: `0 ${interpolate(p, [0, 1], [100, 0])}%`,
              whiteSpace: 'nowrap',
            }}
          >
            {title}
          </div>
        </div>
        {onBoard ? (
          <>
            <svg width={Math.min(box.w, estWidth(title, size, -0.045))} height={30} style={{marginTop: 8, overflow: 'visible'}}>
              <path
                d={`M 4 18 Q ${box.w * 0.2} 6 ${Math.min(box.w, estWidth(title, size, -0.045)) - 6} 14`}
                stroke={surface.accent}
                strokeWidth={7}
                fill="none"
                strokeLinecap="round"
                pathLength={1}
                strokeDasharray={1}
                strokeDashoffset={1 - enter(frame, 10, 14)}
              />
            </svg>
            {small ? (
              <MaskLine frame={frame} delay={12} style={{marginTop: 26}}>
                <div style={{fontFamily: FONT.sans, fontSize: 38, fontWeight: 500, color: surface.dim}}>{small}</div>
              </MaskLine>
            ) : null}
          </>
        ) : null}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// 용어 정의 — 사전 항목처럼.
// ---------------------------------------------------------------------------
export const DefinitionCard: React.FC<TemplateProps> = ({data, frame, surface, box}) => {
  const term = data.title || '';
  const termSize = fitSize(term, box.w * 0.9, 150, 70, -0.04);
  const body = fitBlock(data.body || '', box.w * 0.86, box.h * 0.36, 50, 32, 1.45, 4);
  return (
    <div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center'}}>
      <ParenLabel text="정의 · definition" surface={surface} frame={frame} size={24} />
      <div style={{height: 22}} />
      <MaskLine frame={frame} delay={2} dur={18}>
        <div style={{fontFamily: FONT.display, fontWeight: 900, fontSize: termSize, lineHeight: 1.05,
          letterSpacing: '-0.04em', color: surface.fg}}>{term}</div>
      </MaskLine>
      {data.subtitle ? (
        <MaskLine frame={frame} delay={7}>
          <div style={{marginTop: 14, fontFamily: FONT.numeral, fontStyle: 'italic', fontWeight: 700, fontSize: 40,
            color: surface.accent, letterSpacing: '0'}}>{data.subtitle}</div>
        </MaskLine>
      ) : null}
      <div style={{height: 40}} />
      <DrawRule frame={frame} delay={9} color={surface.rule} />
      <div style={{height: 36}} />
      {body.lines.map((l, i) => (
        <MaskLine key={i} frame={frame} delay={13 + i * 3}>
          <div style={{fontFamily: FONT.sans, fontWeight: 500, fontSize: body.size, lineHeight: 1.45, color: surface.fg}}>
            {l}
          </div>
        </MaskLine>
      ))}
    </div>
  );
};

// ---------------------------------------------------------------------------
// 인용 카드 — Paper 표면 + 명조.
// ---------------------------------------------------------------------------
export const QuoteCard: React.FC<TemplateProps> = ({data, frame, surface, box}) => {
  const text = data.body || '';
  useFontForText('500 60px "Noto Serif KR"', text);
  const {size, lines} = fitBlock(text, box.w * 0.8, box.h * 0.6, 72, 40, 1.5, 5);
  const who = [data.author, data.source].filter(Boolean).join(' — ');
  return (
    <div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center',
      paddingLeft: box.w * 0.08}}>
      <div style={{position: 'absolute', left: 0, top: box.h * 0.02, fontFamily: FONT.latin, fontSize: 300,
        lineHeight: 1, color: surface.accent, opacity: enter(frame, 0, 12)}}>“</div>
      {lines.map((l, i) => (
        <MaskLine key={i} frame={frame} delay={4 + i * 4} dur={20}>
          <div style={{fontFamily: FONT.serif, fontWeight: 500, fontSize: size, lineHeight: 1.5, color: surface.fg,
            letterSpacing: '-0.01em'}}>{l}</div>
        </MaskLine>
      ))}
      <div style={{height: 44}} />
      <div style={{display: 'flex', alignItems: 'center', gap: 20, opacity: enter(frame, 14 + lines.length * 4, 14)}}>
        <div style={{width: 64, height: 2, background: surface.fg}} />
        <div style={{fontFamily: FONT.sans, fontSize: 32, fontWeight: 600, color: surface.fg}}>{who}</div>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// 숫자 강조
// ---------------------------------------------------------------------------
export const StatCard: React.FC<TemplateProps> = ({data, frame, surface, box}) => {
  const num = data.title || '';
  const numSize = fitSize(num, box.w * 0.55, 360, 120);
  const p = enter(frame, 0, 18);
  const body = fitBlock(data.body || '', box.w * 0.36, box.h * 0.5, 54, 30, 1.35, 4);
  return (
    <div style={{position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', gap: box.w * 0.05}}>
      <div style={{overflow: 'hidden'}}>
        <div style={{fontFamily: FONT.latin, fontSize: numSize, lineHeight: 1, color: surface.name === 'overlay' ?
          surface.accent : surface.fg, translate: `0 ${interpolate(p, [0, 1], [100, 0])}%`}}>{num}</div>
      </div>
      <div style={{display: 'flex', flexDirection: 'column', gap: 18}}>
        {body.lines.map((l, i) => (
          <MaskLine key={i} frame={frame} delay={8 + i * 3}>
            <div style={{fontFamily: FONT.sans, fontWeight: 700, fontSize: body.size, lineHeight: 1.35,
              color: surface.name === 'signal' ? '#111' : surface.fg}}>{l}</div>
          </MaskLine>
        ))}
        {data.subtitle ? (
          <div style={{fontFamily: FONT.sans, fontSize: 22, color: surface.dim, opacity: enter(frame, 16, 12)}}>
            {data.subtitle}
          </div>
        ) : null}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// 오프닝 타이틀 — 리포트 표지(빨간 바탕 + 짙은 거대 타이포 + 가장자리 작은 글자).
// 화자 영상은 LongForm 이 중앙 작은 프레임으로 이 위에 얹는다.
// ---------------------------------------------------------------------------
export const TitleCard: React.FC<TemplateProps> = ({data, frame, dur, surface, box, brand, episode}) => {
  const title = data.title || episode.title;
  const {size, lines} = fitBlock(title, box.w * 0.9, box.h * 0.8, 230, 110, 0.98, 3, -0.05);
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
        {lines.map((l, i) => (
          <div key={i} style={{overflow: 'hidden'}}>
            <div style={{fontFamily: FONT.display, fontWeight: 900, fontSize: size, lineHeight: 0.98,
              letterSpacing: '-0.05em', color: surface.fg, textAlign: 'center', whiteSpace: 'nowrap',
              translate: `0 ${interpolate(enter(frame, i * 3, 18, EASE_OUT), [0, 1], [100, 0])}%`}}>{l}</div>
          </div>
        ))}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// 로어서드 — 화자 소개
// ---------------------------------------------------------------------------
export const LowerThird: React.FC<TemplateProps> = ({frame, dur, brand, theme, data}) => {
  const out = exit(frame, dur, 12);
  // '오늘의 주제' 태그(셜록현준 레퍼런스: 타이틀 뒤 5~6초 동안 이 영상의 질문을 한 줄로) — 파이프라인이 data.title 을 줄 때만
  const topic = String(data?.title || '').trim();
  const topicSize = topic ? fitSize(topic, 980, 54, 34, -0.01) : 0;
  return (
    <div style={{position: 'absolute', left: 96, bottom: 190, opacity: out}}>
      {topic ? (
        <div style={{marginBottom: 34}}>
          <MaskLine frame={frame} delay={0}>
            <span style={{display: 'inline-block', fontFamily: FONT.sans, fontWeight: 700, fontSize: 22, lineHeight: 1.2,
              color: '#111111', background: theme.accent, borderRadius: 5, padding: '4px 11px 5px'}}>
              {String(data?.subtitle || '오늘의 주제')}
            </span>
          </MaskLine>
          <MaskLine frame={frame} delay={5}>
            <div style={{marginTop: 12, maxWidth: 980, fontFamily: FONT.round, fontSize: topicSize, lineHeight: 1.18,
              letterSpacing: '-0.01em', color: '#fff', whiteSpace: 'nowrap',
              textShadow: '0 2px 14px rgba(0,0,0,0.55)'}}>{topic}</div>
          </MaskLine>
        </div>
      ) : null}
      <div style={{width: 360}}>
        <DrawRule frame={frame} delay={topic ? 10 : 0} color="rgba(255,255,255,0.7)" />
      </div>
      <div style={{height: 16}} />
      <MaskLine frame={frame} delay={topic ? 14 : 4}>
        <div style={{display: 'flex', alignItems: 'center', gap: 14}}>
          <span style={{width: 14, height: 14, background: theme.accent, display: 'inline-block'}} />
          <span style={{fontFamily: FONT.sans, fontWeight: 800, fontSize: 40, color: '#fff',
            textShadow: '0 2px 12px rgba(0,0,0,0.45)'}}>{brand.presenter}</span>
        </div>
      </MaskLine>
      <MaskLine frame={frame} delay={topic ? 18 : 8}>
        <div style={{marginTop: 8, fontFamily: FONT.sans, fontWeight: 500, fontSize: 24, color: 'rgba(255,255,255,0.86)',
          textShadow: '0 2px 10px rgba(0,0,0,0.5)'}}>{brand.presenterTitle}</div>
      </MaskLine>
    </div>
  );
};

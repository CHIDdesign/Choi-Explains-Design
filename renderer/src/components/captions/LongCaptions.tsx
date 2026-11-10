import React from 'react';
import {FONT, SLOT_TYPE} from '../../design/tokens';
import {fitSize} from '../../lib/fit';
import {lastIndexAtOrBefore} from '../../lib/time';
import type {CaptionCue} from '../../lib/types';

/** 자막(디자인 v5): 하단 중앙 한 줄, 흰 Pretendard 500, 검정 75% 상자, 반경 3px, 색 강조 없음(강조는 콜아웃 몫). 등장·퇴장 없이 바뀐다 */
export const BoxedCaption: React.FC<{cue: CaptionCue; left?: number; width: number; bottom: number; size?: number; minSize?: number}> = ({cue, left = 0,
  width, bottom, size: maxSize = SLOT_TYPE.caption, minSize}) => {
  const text = cue.lines.flat().map((w) => w.text).join(' ');
  const size = minSize ? fitSize(text, width * 0.86 - maxSize, maxSize, minSize, -0.012) : maxSize;
  return (
    <div style={{position: 'absolute', left, width, bottom, display: 'flex', justifyContent: 'center'}}>
      <div style={{background: 'rgba(0,0,0,0.75)', padding: `${size * 0.14}px ${size * 0.5}px ${size * 0.18}px`, borderRadius: 3, maxWidth: width * 0.86,
        fontFamily: FONT.sans, fontWeight: 500, fontSize: size, lineHeight: 1.3, letterSpacing: '-0.012em', color: '#FFFFFF',
        textAlign: 'center', wordBreak: 'keep-all'}}>
        {text}
      </div>
    </div>
  );
};

export const LongCaptions: React.FC<{cues: CaptionCue[]; t: number; left?: number; frameW?: number; bottom?: number; size?: number; minSize?: number}> = ({cues, t, left,
  frameW = 1920, bottom = 56, size, minSize}) => {
  const i = lastIndexAtOrBefore(cues, t, (c) => c.start);
  if (i < 0 || t >= cues[i].end || cues[i].hidden) return null;
  return <BoxedCaption cue={cues[i]} left={left} width={frameW} bottom={bottom} size={size} minSize={minSize} />;
};

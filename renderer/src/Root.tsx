import React from 'react';
import {Composition, Still} from 'remotion';
import type {CalculateMetadataFunction} from 'remotion';
import {LongForm} from './compositions/LongForm';
import {Short} from './compositions/Short';
import {Thumbnail} from './compositions/Thumbnail';
import type {LongFormProps, ShortProps} from './lib/types';
import {SAMPLE_LONG, SAMPLE_SHORT, SAMPLE_THUMB} from './samples';

// props 에 들어 있는 길이·fps 로 컴포지션 메타데이터를 정한다(Python 이 계산).
const longMeta: CalculateMetadataFunction<LongFormProps> = ({props}) => ({
  durationInFrames: Math.max(1, Math.ceil(props.duration * props.fps)),
  fps: props.fps,
  width: props.width,
  height: props.height,
});

const shortMeta: CalculateMetadataFunction<ShortProps> = ({props}) => ({
  durationInFrames: Math.max(1, Math.ceil(props.duration * props.fps)),
  fps: props.fps,
  width: props.width,
  height: props.height,
});

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="LongForm"
        component={LongForm}
        durationInFrames={1920}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={SAMPLE_LONG}
        calculateMetadata={longMeta}
      />
      <Composition
        id="Short"
        component={Short}
        durationInFrames={600}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={SAMPLE_SHORT}
        calculateMetadata={shortMeta}
      />
      <Still id="Thumbnail" component={Thumbnail} width={1280} height={720} defaultProps={SAMPLE_THUMB} />
    </>
  );
};

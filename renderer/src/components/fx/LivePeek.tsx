import React from 'react';
import {Artifact, useCurrentFrame} from 'remotion';

/**
 * 렌더 중 진행 화면용 미리보기: every 프레임마다 지금 렌더된 프레임 이미지를 artifact 로 내보낸다.
 * Remotion 이 이미 찍은 프레임 버퍼를 그대로 넘기므로 영상 결과·속도에 영향이 없다(스튜디오 미리보기에서는 아무것도 안 함).
 */
export const LivePeek: React.FC<{every?: number}> = ({every}) => {
  const frame = useCurrentFrame();
  if (!every || every <= 0 || frame % every !== 0) {
    return null;
  }
  return <Artifact filename={`peek-${frame}.jpg`} content={Artifact.Thumbnail} />;
};

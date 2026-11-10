import type {Surface} from '../../design/surfaces';
import type {Theme} from '../../design/tokens';
import type {Brand, Episode, GraphicData, Layout} from '../../lib/types';

export type TemplateProps = {
  id: string;
  data: GraphicData;
  frame: number; // 시퀀스 내부 프레임
  dur: number; // 전체 프레임 수
  fps: number;
  theme: Theme;
  surface: Surface;
  box: {w: number; h: number};
  layout: Layout;
  brand: Brand;
  episode: Episode;
  faceX?: number; // 화자 위 슬롯이 얼굴 반대편을 고를 때
  compact?: boolean; // classic 숏폼의 창·패널(window 창 / full·framed 도식 패널)
};
